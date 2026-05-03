"""
Hydroponic Sensor + Control System for EC800X QuecDuino (QuecPython).

Sensors:
  AS7263 (0x49) — NIR 610-860nm, I2C
  AS7341 (0x39) — VIS+NIR 390-890nm, I2C
  BA121        — Conductivity + Temperature, UART 9600bps
  PH4502C      — pH, Analog ADC0
  Pressure     — Water pressure, Analog ADC1
  Flow         — Hall effect flow meter, GPIO interrupt

Controls:
  Water Valve  — Electromagnetic valve via GPIO + relay

Wiring:
  I2C0:    SCL=GPIO67 (Pin 17), SDA=GPIO66 (Pin 16)
  UART1:   TX=GPIO, RX=GPIO (to BA121 pin4/5)
  UART2:   TX/RX (to ESP32)
  ADC0:    via voltage divider from PH4502C Po pin
  ADC1:    via voltage divider from pressure sensor signal
  GPIO:    valve relay control pin
  GPIO:    flow sensor signal pin
"""

from machine import I2C, UART, ADC
import utime

from quec_i2c import QuecI2C, I2CDevice
from as7341 import AS7341
from as7263 import AS7263
from ba121 import BA121
from ph4502c import PH4502C
from pressure import PressureSensor
from valve import WaterValve
from flow import FlowSensor
from pump import PeristalticPump
from relay import Relay
from esp_bridge import ESPBridge
from mqtt_client import HydroMQTT
from misc import PWM_V2

# --- Configuration ---
# Adjust these to match your hardware setup

VALVE_GPIO = 25          # GPIO pin for valve relay
VALVE_ACTIVE_LOW = True  # Most relay modules are active-low

FLOW_GPIO = 26           # GPIO pin for flow meter signal

PRESSURE_MAX = 1.2       # Max sensor rated pressure (MPa)
DIVIDER_RATIO = 0.233    # Voltage divider: R1=33K, R2=10K

PUMP_A_DIR_GPIO = 27     # Pump A direction pin
PUMP_A_PWM = PWM_V2.PWM0 # Pump A PWM channel
PUMP_B_DIR_GPIO = 28     # Pump B direction pin
PUMP_B_PWM = PWM_V2.PWM1 # Pump B PWM channel

WATER_PUMP_GPIO = 29     # Main water pump relay GPIO
GROW_LIGHT_GPIO = 30     # Grow light relay GPIO

ESP32_UART_BAUD = 115200  # ESP32 UART2 baud rate

# MQTT Configuration
MQTT_SERVER = ""          # MQTT broker address (empty = skip MQTT)
MQTT_PORT = 1883          # MQTT broker port
MQTT_USER = None          # MQTT username (None = no auth)
MQTT_PASSWORD = None      # MQTT password
MQTT_CLIENT_ID = "ec800x_hydro"
MQTT_BASE_TOPIC = "hydroponic"
MQTT_TIMEZONE = 8         # UTC+8


def init_spectral(i2c, devices):
    """Initialize AS7263 and AS7341 spectral sensors."""
    nir = None
    vis = None

    if 0x49 in devices:
        nir = AS7263(i2c, 0x49)
        if nir.begin():
            nir.set_gain(AS7263.GAIN_X64)
            nir.set_integration_time(50)
            print("AS7263: found, HW_VERSION=0x%02X" % nir.get_hw_version())
        else:
            print("AS7263: init failed")
            nir = None
    else:
        print("AS7263: not found at 0x49")

    if 0x39 in devices:
        try:
            dev = I2CDevice(i2c, 0x39)
            vis = AS7341(dev)
            vis.gain = AS7341.GAIN_256X
            print("AS7341: found")
        except RuntimeError as e:
            print("AS7341: init failed -", e)
            vis = None
    else:
        print("AS7341: not found at 0x39")

    return nir, vis


def init_ba121():
    """Initialize BA121 conductivity sensor via UART."""
    sensor = BA121(UART.UART1, 0, 0)
    if sensor.init():
        print("BA121: found")
        return sensor
    print("BA121: init failed")
    return None


def init_ph4502c():
    """Initialize PH4502C pH sensor via ADC0."""
    sensor = PH4502C(
        adc_channel=ADC.ADC0,
        divider_ratio=DIVIDER_RATIO,
    )
    if sensor.init():
        print("PH4502C: found")
        return sensor
    print("PH4502C: init failed")
    return None


def init_pressure():
    """Initialize water pressure sensor via ADC1."""
    sensor = PressureSensor(
        adc_channel=ADC.ADC1,
        max_pressure=PRESSURE_MAX,
        divider_ratio=DIVIDER_RATIO,
    )
    if sensor.init():
        print("Pressure: found, max=%.1f MPa" % PRESSURE_MAX)
        return sensor
    print("Pressure: init failed")
    return None


def init_valve():
    """Initialize water valve control."""
    valve = WaterValve(VALVE_GPIO, VALVE_ACTIVE_LOW)
    state = "OPEN" if valve.is_open else "CLOSED"
    print("Valve: initialized on GPIO%d [%s]" % (VALVE_GPIO, state))
    return valve


def init_flow():
    """Initialize Hall effect flow sensor."""
    flow = FlowSensor(FLOW_GPIO)
    print("Flow: initialized on GPIO%d (4980 pulses/L)" % FLOW_GPIO)
    return flow


def init_pumps():
    """Initialize two peristaltic pumps."""
    pump_a = PeristalticPump(PUMP_A_DIR_GPIO, PUMP_A_PWM, name="Pump-A")
    if pump_a.init():
        print("Pump-A: initialized (DIR=GPIO%d, PWM0)" % PUMP_A_DIR_GPIO)
    else:
        print("Pump-A: init failed")
        pump_a = None

    pump_b = PeristalticPump(PUMP_B_DIR_GPIO, PUMP_B_PWM, name="Pump-B")
    if pump_b.init():
        print("Pump-B: initialized (DIR=GPIO%d, PWM1)" % PUMP_B_DIR_GPIO)
    else:
        print("Pump-B: init failed")
        pump_b = None

    return pump_a, pump_b


def init_relays():
    """Initialize main water pump and grow light relays."""
    water_pump = Relay(WATER_PUMP_GPIO, name="WaterPump")
    print("WaterPump: initialized on GPIO%d [%s]" % (WATER_PUMP_GPIO, water_pump.status()))

    grow_light = Relay(GROW_LIGHT_GPIO, name="GrowLight")
    print("GrowLight: initialized on GPIO%d [%s]" % (GROW_LIGHT_GPIO, grow_light.status()))

    return water_pump, grow_light


def init_esp_bridge():
    """Initialize ESP32 UART bridge."""
    bridge = ESPBridge(UART.UART2, ESP32_UART_BAUD)
    if bridge.init():
        print("ESPBridge: initialized on UART2 @ %d bps" % ESP32_UART_BAUD)
    else:
        print("ESPBridge: init failed")
        bridge = None
    return bridge


def init_mqtt():
    """Initialize MQTT client."""
    mqtt = HydroMQTT(
        client_id=MQTT_CLIENT_ID,
        server=MQTT_SERVER,
        port=MQTT_PORT,
        user=MQTT_USER,
        password=MQTT_PASSWORD,
        base_topic=MQTT_BASE_TOPIC,
        timezone=MQTT_TIMEZONE,
    )
    if mqtt.init():
        print("MQTT: initialized (%s:%d, topic=%s)" %
              (MQTT_SERVER, MQTT_PORT, MQTT_BASE_TOPIC))
    else:
        print("MQTT: not connected")
        mqtt = None
    return mqtt


def main():
    # Initialize I2C bus 0 at 400KHz
    i2c = QuecI2C(I2C.I2C0, I2C.FAST_MODE)

    # Scan for I2C devices
    devices = i2c.scan()
    print("I2C devices found:", [hex(d) for d in devices])

    # Initialize all sensors and controls
    nir, vis = init_spectral(i2c, devices)
    ba121 = init_ba121()
    ph_sensor = init_ph4502c()
    pressure_sensor = init_pressure()
    valve = init_valve()
    flow = init_flow()
    pump_a, pump_b = init_pumps()
    water_pump, grow_light = init_relays()
    bridge = init_esp_bridge()
    mqtt = init_mqtt()

    print("")
    print("=== System ready, starting main loop ===")
    print("")

    # Main loop
    while True:
        # Collect all data into a single dict
        sensor = {}
        status = {}

        # --- AS7263 NIR ---
        if nir:
            data = nir.measure()
            if data:
                sensor["nir_R"] = data["R"]
                sensor["nir_S"] = data["S"]
                sensor["nir_T"] = data["T"]
                sensor["nir_U"] = data["U"]
                sensor["nir_V"] = data["V"]
                sensor["nir_W"] = data["W"]
                print("AS7263: R=%d S=%d T=%d U=%d V=%d W=%d" %
                      (data["R"], data["S"], data["T"],
                       data["U"], data["V"], data["W"]))

        # --- AS7341 VIS+NIR ---
        if vis:
            data = vis.all_channels
            if data:
                sensor["vis_F1"] = data["F1"]
                sensor["vis_F2"] = data["F2"]
                sensor["vis_F3"] = data["F3"]
                sensor["vis_F4"] = data["F4"]
                sensor["vis_F5"] = data["F5"]
                sensor["vis_F6"] = data["F6"]
                sensor["vis_F7"] = data["F7"]
                sensor["vis_F8"] = data["F8"]
                sensor["vis_CLEAR"] = data["CLEAR"]
                sensor["vis_NIR"] = data["NIR"]
                print("AS7341: F1=%d F2=%d F3=%d F4=%d F5=%d F6=%d F7=%d F8=%d CLR=%d NIR=%d" %
                      (data["F1"], data["F2"], data["F3"], data["F4"],
                       data["F5"], data["F6"], data["F7"], data["F8"],
                       data["CLEAR"], data["NIR"]))

            vis.configure_flicker_detection()
            utime.sleep_ms(100)
            flicker = vis.flicker_detected
            if flicker:
                sensor["vis_flicker_hz"] = flicker
                print("AS7341: Flicker detected: %d Hz" % flicker)
            vis.initialize()

        # --- BA121 Conductivity + Temperature ---
        conductivity = None
        temperature = None
        if ba121:
            conductivity, temperature = ba121.read()
            if conductivity is not None:
                ec_ms = conductivity / 1000.0
                sensor["ec_us"] = conductivity
                sensor["ec_ms"] = ec_ms
                sensor["water_temp"] = temperature
                print("BA121: EC=%.3f mS/cm (%.1f uS/cm), Temp=%.2f C" %
                      (ec_ms, conductivity, temperature))
            else:
                print("BA121: read failed, status=%s" % ba121.status_string())

        # --- PH4502C pH ---
        ph = None
        if ph_sensor:
            ph = ph_sensor.read_ph()
            if ph is not None:
                sensor["ph"] = ph
                print("PH4502C: pH=%.2f" % ph)
            else:
                print("PH4502C: read failed")

        # --- Water Pressure ---
        pressure = None
        if pressure_sensor:
            pressure, voltage = pressure_sensor.read_pressure()
            if pressure is not None:
                sensor["pressure_mpa"] = pressure
                sensor["pressure_v"] = voltage
                print("Pressure: %.3f MPa (%.3fV)" % (pressure, voltage))
            else:
                print("Pressure: read failed")

        # --- Water Flow ---
        rate_lpm, total_liters = flow.read()
        sensor["flow_lpm"] = rate_lpm
        sensor["flow_total_l"] = total_liters
        print("Flow: %.2f L/min, Total: %.3f L" % (rate_lpm, total_liters))

        # --- Valve Status ---
        valve_state = "OPEN" if valve.is_open else "CLOSED"
        status["valve"] = valve_state
        print("Valve: %s" % valve_state)

        # --- Pump Status ---
        if pump_a:
            status["pump_a_dir"] = pump_a.direction
            status["pump_a_speed"] = pump_a.speed
            status["pump_a_running"] = pump_a.is_running
            print(pump_a.status())
        if pump_b:
            status["pump_b_dir"] = pump_b.direction
            status["pump_b_speed"] = pump_b.speed
            status["pump_b_running"] = pump_b.is_running
            print(pump_b.status())

        # --- Relay Status ---
        status["water_pump"] = "ON" if water_pump.is_on else "OFF"
        status["grow_light"] = "ON" if grow_light.is_on else "OFF"
        print(water_pump.status())
        print(grow_light.status())

        # Combine sensor + status for publishing
        all_data = {}
        all_data.update(sensor)
        all_data.update(status)

        # --- ESP32 Bridge ---
        if bridge:
            bridge.process_commands(
                valve=valve, pump_a=pump_a, pump_b=pump_b,
                water_pump_relay=water_pump, grow_light_relay=grow_light,
            )
            bridge.send_sensor_data(**all_data)

        # --- MQTT ---
        if mqtt:
            mqtt.process_commands(
                valve=valve, pump_a=pump_a, pump_b=pump_b,
                water_pump_relay=water_pump, grow_light_relay=grow_light,
            )
            mqtt.publish_sensor_data(**all_data)

        print("---")
        utime.sleep(2)


if __name__ == "__main__":
    main()
