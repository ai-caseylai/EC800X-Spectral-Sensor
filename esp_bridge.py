"""
ESP32 UART Bridge for QuecPython (EC800X).
Communication with ESP32 via UART2 using JSON protocol.

Protocol:
  Each message is a JSON line terminated by newline (\n).
  EC800X → ESP32: sensor data + status reports
  ESP32 → EC800X: control commands

  Outgoing example:
    {"t":"sensor","ph":6.8,"ec":1.2,"temp":25.3,"pressure":0.5}\n
    {"t":"status","valve":"OPEN","pump_a":"forward@80","pump_b":"STOPPED"}\n

  Incoming commands:
    {"cmd":"valve","action":"open"}\n
    {"cmd":"pump","id":"a","speed":80,"dir":"forward"}\n
    {"cmd":"relay","id":"water_pump","action":"on"}\n
    {"cmd":"relay","id":"grow_light","action":"on"}\n
    {"cmd":"pump","id":"b","speed":0}\n

UART2 Wiring:
  EC800X TX → ESP32 RX
  EC800X RX ← ESP32 TX
  EC800X GND ←→ ESP32 GND
"""

import ujson
from machine import UART
import utime


class ESPBridge:
    """UART bridge between EC800X and ESP32."""

    def __init__(self, uart_port=UART.UART2, baud=115200):
        """
        Args:
            uart_port: UART port (default UART.UART2).
            baud: Baud rate (default 115200).
        """
        self._uart = None
        self._uart_port = uart_port
        self._baud = baud
        self._rx_buf = ""
        self._connected = False

    def init(self):
        """Initialize UART2. Returns True on success."""
        try:
            self._uart = UART(self._uart_port, self._baud, 8, 0, 1, 0)
            self._connected = True
            return True
        except Exception as e:
            print("ESPBridge: UART init failed -", e)
            return False

    def deinit(self):
        """Close UART."""
        if self._uart:
            try:
                self._uart.close()
            except Exception:
                pass
            self._uart = None
            self._connected = False

    # --- Sending ---

    def send(self, data):
        """Send a dict as JSON line.

        Args:
            data: dict to send.
        Returns:
            True on success.
        """
        if not self._uart:
            return False
        try:
            msg = ujson.dumps(data) + "\n"
            self._uart.write(msg.encode("utf-8"))
            return True
        except Exception as e:
            print("ESPBridge: send failed -", e)
            return False

    def send_sensor_data(self, **kwargs):
        """Send sensor readings to ESP32.

        Args:
            kwargs: Sensor key-value pairs.
        """
        data = {"t": "sensor"}
        data.update(kwargs)
        self.send(data)

    def send_status(self, **kwargs):
        """Send device status to ESP32.

        Args:
            kwargs: Status key-value pairs.
        """
        data = {"t": "status"}
        data.update(kwargs)
        self.send(data)

    def send_ack(self, cmd_id, success=True, msg=""):
        """Send command acknowledgment.

        Args:
            cmd_id: Command ID from incoming message.
            success: Whether command succeeded.
            msg: Optional message.
        """
        self.send({"t": "ack", "id": cmd_id, "ok": success, "msg": msg})

    # --- Receiving ---

    def _read_available(self):
        """Read available UART data into buffer."""
        if not self._uart:
            return
        try:
            while True:
                b = self._uart.read(1)
                if b is None or len(b) == 0:
                    break
                self._rx_buf += b.decode("utf-8", "ignore")
        except Exception:
            pass

    def recv(self):
        """Try to receive a complete JSON message.

        Returns:
            dict if a complete message was received, None otherwise.
        """
        self._read_available()

        while "\n" in self._rx_buf:
            line, self._rx_buf = self._rx_buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                return ujson.loads(line)
            except Exception:
                print("ESPBridge: invalid JSON -", line[:60])

        return None

    # --- Command Dispatch ---

    def process_commands(self, valve=None, pump_a=None, pump_b=None,
                         water_pump_relay=None, grow_light_relay=None):
        """Read and execute commands from ESP32.

        Args:
            valve: WaterValve instance.
            pump_a: PeristalticPump instance.
            pump_b: PeristalticPump instance.
            water_pump_relay: Relay instance for main water pump.
            grow_light_relay: Relay instance for grow light.

        Returns:
            List of received command dicts.
        """
        commands = []
        while True:
            msg = self.recv()
            if msg is None:
                break
            commands.append(msg)
            cmd = msg.get("cmd", "")
            cmd_id = msg.get("id", "")

            if cmd == "valve" and valve:
                action = msg.get("action", "")
                if action == "open":
                    valve.open()
                    self.send_ack(cmd_id, True, "valve opened")
                elif action == "close":
                    valve.close()
                    self.send_ack(cmd_id, True, "valve closed")
                elif action == "toggle":
                    valve.toggle()
                    self.send_ack(cmd_id, True, "valve toggled")
                else:
                    self.send_ack(cmd_id, False, "unknown action: %s" % action)

            elif cmd == "pump":
                pump_id = msg.get("id", "")
                pump = None
                if pump_id == "a" and pump_a:
                    pump = pump_a
                elif pump_id == "b" and pump_b:
                    pump = pump_b

                if pump:
                    speed = msg.get("speed")
                    direction = msg.get("dir")
                    action = msg.get("action", "")

                    if action == "stop" or speed == 0:
                        pump.stop()
                        self.send_ack(cmd_id, True, "pump %s stopped" % pump_id)
                    else:
                        if speed is not None:
                            pump.start(speed=speed, direction=direction)
                            self.send_ack(cmd_id, True,
                                          "pump %s: %s@%d%%" %
                                          (pump_id, direction or "forward", speed))
                        else:
                            self.send_ack(cmd_id, False, "missing speed")
                else:
                    self.send_ack(cmd_id, False, "unknown pump: %s" % pump_id)

            elif cmd == "relay":
                rid = msg.get("id", "")
                relay = None
                if rid == "water_pump" and water_pump_relay:
                    relay = water_pump_relay
                elif rid == "grow_light" and grow_light_relay:
                    relay = grow_light_relay

                if relay:
                    action = msg.get("action", "")
                    if action == "on":
                        relay.on()
                        self.send_ack(cmd_id, True, "%s on" % rid)
                    elif action == "off":
                        relay.off()
                        self.send_ack(cmd_id, True, "%s off" % rid)
                    elif action == "toggle":
                        relay.toggle()
                        self.send_ack(cmd_id, True, "%s toggled" % rid)
                    else:
                        self.send_ack(cmd_id, False, "unknown action: %s" % action)
                else:
                    self.send_ack(cmd_id, False, "unknown relay: %s" % rid)

            else:
                self.send_ack(cmd_id, False, "unknown cmd: %s" % cmd)

        return commands

    @property
    def connected(self):
        """True if UART is initialized."""
        return self._connected
