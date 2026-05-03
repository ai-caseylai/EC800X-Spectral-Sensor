"""
MQTT Client for QuecPython (EC800X).
Direct MQTT connectivity with sensor data publishing and remote command control.

Features:
  - NTP time sync for accurate timestamps
  - Publish sensor data to configurable topic
  - Subscribe to command topics for remote control
  - Remote configuration update (MQTT server, topics, etc.)
  - Automatic reconnection

MQTT Topics:
  Publish:
    {base_topic}/sensors   — sensor data with timestamp
    {base_topic}/status    — device status
    {base_topic}/ack       — command acknowledgment
    {base_topic}/config    — current configuration (on request)

  Subscribe:
    {base_topic}/cmd/#     — all command subtopics
    {base_topic}/cmd/valve
    {base_topic}/cmd/pump
    {base_topic}/cmd/relay
    {base_topic}/cmd/config
"""

import ujson
import utime
from umqtt import MQTTClient

try:
    import ntptime
    _NTP_AVAILABLE = True
except ImportError:
    _NTP_AVAILABLE = False


class HydroMQTT:
    """MQTT client for hydroponic sensor + control system."""

    def __init__(self, client_id="ec800x_hydro", server="", port=1883,
                 user=None, password=None, base_topic="hydroponic",
                 timezone=8):
        """
        Args:
            client_id: MQTT client ID.
            server: MQTT broker address.
            port: MQTT broker port (default 1883, 8883 for SSL).
            user: MQTT username (optional).
            password: MQTT password (optional).
            base_topic: Base MQTT topic prefix.
            timezone: Timezone offset for NTP (default +8 Beijing).
        """
        self._client_id = client_id
        self._server = server
        self._port = port
        self._user = user
        self._password = password
        self._base_topic = base_topic
        self._timezone = timezone
        self._client = None
        self._connected = False
        self._ntp_synced = False

    def init(self):
        """Initialize MQTT client and sync NTP. Returns True on success."""
        self._sync_ntp()
        if not self._server:
            print("HydroMQTT: no server configured, skipping")
            return False
        return self._connect()

    def _sync_ntp(self):
        """Sync RTC via NTP."""
        if not _NTP_AVAILABLE:
            print("HydroMQTT: NTP module not available")
            return
        try:
            ntptime.sethost("ntp.aliyun.com")
            ntptime.settime(timezone=self._timezone)
            self._ntp_synced = True
            print("HydroMQTT: NTP synced (UTC+%d)" % self._timezone)
        except Exception as e:
            print("HydroMQTT: NTP sync failed -", e)

    def _connect(self):
        """Connect to MQTT broker."""
        try:
            self._client = MQTTClient(
                self._client_id,
                self._server,
                port=self._port,
                user=self._user,
                password=self._password,
                keepalive=60,
            )
            self._client.set_callback(self._on_message)
            self._client.connect()
            self._connected = True

            # Subscribe to command topics
            cmd_topic = b"%s/cmd/#" % self._base_topic.encode()
            self._client.subscribe(cmd_topic)

            print("HydroMQTT: connected to %s:%d" % (self._server, self._port))
            print("HydroMQTT: subscribed to %s/cmd/#" % self._base_topic)
            return True
        except Exception as e:
            print("HydroMQTT: connect failed -", e)
            self._connected = False
            return False

    def disconnect(self):
        """Disconnect from broker."""
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._connected = False

    def _reconnect(self):
        """Attempt reconnection."""
        self._connected = False
        print("HydroMQTT: reconnecting...")
        try:
            self._client.close()
        except Exception:
            pass
        utime.sleep(2)
        self._connect()

    # --- Timestamp ---

    def _timestamp(self):
        """Get ISO 8601 timestamp string."""
        try:
            t = utime.localtime()
            return "%04d-%02d-%02dT%02d:%02d:%02d+%.2d:00" % (
                t[0], t[1], t[2], t[3], t[4], t[5], self._timezone)
        except Exception:
            return ""

    # --- Publishing ---

    def publish(self, topic_suffix, data):
        """Publish dict as JSON to {base_topic}/{topic_suffix}.

        Args:
            topic_suffix: Topic suffix (e.g., "sensors").
            data: dict to publish.
        Returns:
            True on success.
        """
        if not self._connected or not self._client:
            return False
        try:
            topic = b"%s/%s" % (self._base_topic.encode(), topic_suffix.encode())
            payload = ujson.dumps(data).encode("utf-8")
            self._client.publish(topic, payload)
            return True
        except Exception as e:
            print("HydroMQTT: publish failed -", e)
            self._reconnect()
            return False

    def publish_sensor_data(self, **kwargs):
        """Publish sensor readings with timestamp.

        Args:
            kwargs: Sensor key-value pairs.
        """
        data = {"t": "sensor", "ts": self._timestamp()}
        data.update(kwargs)
        self.publish("sensors", data)

    def publish_status(self, **kwargs):
        """Publish device status with timestamp."""
        data = {"t": "status", "ts": self._timestamp()}
        data.update(kwargs)
        self.publish("status", data)

    def publish_ack(self, cmd_id, success=True, msg=""):
        """Publish command acknowledgment."""
        data = {"t": "ack", "id": cmd_id, "ok": success, "msg": msg,
                "ts": self._timestamp()}
        self.publish("ack", data)

    # --- Incoming Messages ---

    def _on_message(self, topic, msg):
        """MQTT message callback — stores for processing in main loop."""
        try:
            decoded = msg.decode("utf-8")
            self._last_msg_topic = topic.decode("utf-8")
            self._last_msg_payload = ujson.loads(decoded)
        except Exception as e:
            print("HydroMQTT: parse error -", e)

    def check_messages(self):
        """Non-blocking check for incoming MQTT messages.

        Returns:
            tuple(topic_suffix, payload_dict) or (None, None).
        """
        self._last_msg_topic = None
        self._last_msg_payload = None

        if not self._connected or not self._client:
            return None, None

        try:
            self._client.check_msg()
        except Exception:
            self._reconnect()
            return None, None

        if self._last_msg_payload:
            # Extract suffix: "hydroponic/cmd/valve" → "valve"
            prefix = "%s/cmd/" % self._base_topic
            if self._last_msg_topic.startswith(prefix):
                suffix = self._last_msg_topic[len(prefix):]
                return suffix, self._last_msg_payload
            return self._last_msg_topic, self._last_msg_payload

        return None, None

    def process_commands(self, valve=None, pump_a=None, pump_b=None,
                         water_pump_relay=None, grow_light_relay=None):
        """Check MQTT and process all pending commands.

        Args:
            valve: WaterValve instance.
            pump_a: PeristalticPump instance.
            pump_b: PeristalticPump instance.
            water_pump_relay: Relay instance.
            grow_light_relay: Relay instance.

        Returns:
            List of (cmd_type, payload) tuples processed.
        """
        commands = []
        for _ in range(10):  # Process up to 10 queued messages
            cmd_type, payload = self.check_messages()
            if cmd_type is None:
                break
            commands.append((cmd_type, payload))
            cmd_id = payload.get("id", "")
            cmd = payload.get("cmd", "")

            if cmd_type == "valve" and valve:
                self._exec_valve(valve, payload, cmd_id)
            elif cmd_type == "pump":
                self._exec_pump(pump_a, pump_b, payload, cmd_id)
            elif cmd_type == "relay":
                self._exec_relay(water_pump_relay, grow_light_relay,
                                 payload, cmd_id)
            elif cmd_type == "config":
                self._exec_config(payload, cmd_id)
            else:
                self.publish_ack(cmd_id, False,
                                 "unknown cmd: %s" % cmd_type)

        return commands

    # --- Command Execution ---

    def _exec_valve(self, valve, payload, cmd_id):
        action = payload.get("action", "")
        if action == "open":
            valve.open()
            self.publish_ack(cmd_id, True, "valve opened")
        elif action == "close":
            valve.close()
            self.publish_ack(cmd_id, True, "valve closed")
        elif action == "toggle":
            valve.toggle()
            self.publish_ack(cmd_id, True, "valve toggled")
        else:
            self.publish_ack(cmd_id, False, "unknown action: %s" % action)

    def _exec_pump(self, pump_a, pump_b, payload, cmd_id):
        pump_id = payload.get("id", "")
        pump = None
        if pump_id == "a" and pump_a:
            pump = pump_a
        elif pump_id == "b" and pump_b:
            pump = pump_b

        if not pump:
            self.publish_ack(cmd_id, False, "unknown pump: %s" % pump_id)
            return

        speed = payload.get("speed")
        direction = payload.get("dir")
        action = payload.get("action", "")

        if action == "stop" or speed == 0:
            pump.stop()
            self.publish_ack(cmd_id, True, "pump %s stopped" % pump_id)
        elif speed is not None:
            pump.start(speed=speed, direction=direction)
            self.publish_ack(cmd_id, True,
                             "pump %s: %s@%d%%" %
                             (pump_id, direction or "forward", speed))
        else:
            self.publish_ack(cmd_id, False, "missing speed")

    def _exec_relay(self, water_pump, grow_light, payload, cmd_id):
        rid = payload.get("id", "")
        relay = None
        if rid == "water_pump" and water_pump:
            relay = water_pump
        elif rid == "grow_light" and grow_light:
            relay = grow_light

        if not relay:
            self.publish_ack(cmd_id, False, "unknown relay: %s" % rid)
            return

        action = payload.get("action", "")
        if action == "on":
            relay.on()
            self.publish_ack(cmd_id, True, "%s on" % rid)
        elif action == "off":
            relay.off()
            self.publish_ack(cmd_id, True, "%s off" % rid)
        elif action == "toggle":
            relay.toggle()
            self.publish_ack(cmd_id, True, "%s toggled" % rid)
        else:
            self.publish_ack(cmd_id, False, "unknown action: %s" % action)

    def _exec_config(self, payload, cmd_id):
        """Handle remote configuration update commands."""
        action = payload.get("action", "")

        if action == "get":
            config = {
                "t": "config", "ts": self._timestamp(),
                "server": self._server, "port": self._port,
                "base_topic": self._base_topic,
                "client_id": self._client_id,
                "timezone": self._timezone,
            }
            self.publish("config", config)
            self.publish_ack(cmd_id, True, "config sent")

        elif action == "set":
            changed = []
            new_server = payload.get("server")
            new_port = payload.get("port")
            new_user = payload.get("user")
            new_password = payload.get("password")
            new_topic = payload.get("base_topic")
            new_tz = payload.get("timezone")

            if new_server and new_server != self._server:
                self._server = new_server
                changed.append("server=%s" % new_server)
            if new_port and new_port != self._port:
                self._port = new_port
                changed.append("port=%d" % new_port)
            if new_user:
                self._user = new_user
                changed.append("user updated")
            if new_password:
                self._password = new_password
                changed.append("password updated")
            if new_topic and new_topic != self._base_topic:
                self._base_topic = new_topic
                changed.append("base_topic=%s" % new_topic)
            if new_tz is not None and new_tz != self._timezone:
                self._timezone = new_tz
                changed.append("timezone=%d" % new_tz)

            if changed:
                self.disconnect()
                utime.sleep(1)
                self._connect()
                self.publish_ack(cmd_id, True, "config updated: %s" %
                                 ", ".join(changed))
            else:
                self.publish_ack(cmd_id, True, "no changes")

        elif action == "ntp_sync":
            self._sync_ntp()
            self.publish_ack(cmd_id, True,
                             "NTP synced: %s" % self._timestamp())

        elif action == "reconnect":
            self._reconnect()
            self.publish_ack(cmd_id, True, "reconnected")

        else:
            self.publish_ack(cmd_id, False, "unknown config action: %s" % action)

    # --- Properties ---

    @property
    def connected(self):
        return self._connected

    @property
    def server(self):
        return self._server

    @property
    def base_topic(self):
        return self._base_topic
