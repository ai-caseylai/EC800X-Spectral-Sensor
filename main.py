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

    print("")
    print("=== System ready, starting main loop ===")
    print("")

    # Main loop
    while True:
        # --- AS7263 NIR ---
        if nir:
            data = nir.measure()
            if data:
                print("AS7263: R=%d S=%d T=%d U=%d V=%d W=%d" %
                      (data["R"], data["S"], data["T"],
                       data["U"], data["V"], data["W"]))

        # --- AS7341 VIS+NIR ---
        if vis:
            data = vis.all_channels
            if data:
                print("AS7341: F1=%d F2=%d F3=%d F4=%d F5=%d F6=%d F7=%d F8=%d CLR=%d NIR=%d" %
                      (data["F1"], data["F2"], data["F3"], data["F4"],
                       data["F5"], data["F6"], data["F7"], data["F8"],
                       data["CLEAR"], data["NIR"]))

            vis.configure_flicker_detection()
            utime.sleep_ms(100)
            flicker = vis.flicker_detected
            if flicker:
                print("AS7341: Flicker detected: %d Hz" % flicker)
            vis.initialize()

        # --- BA121 Conductivity + Temperature ---
        if ba121:
            conductivity, temperature = ba121.read()
            if conductivity is not None:
                ec_ms = conductivity / 1000.0
                print("BA121: EC=%.3f mS/cm (%.1f uS/cm), Temp=%.2f C" %
                      (ec_ms, conductivity, temperature))
            else:
                print("BA121: read failed, status=%s" % ba121.status_string())

        # --- PH4502C pH ---
        if ph_sensor:
            ph = ph_sensor.read_ph()
            if ph is not None:
                print("PH4502C: pH=%.2f" % ph)
            else:
                print("PH4502C: read failed")

        # --- Water Pressure ---
        if pressure_sensor:
            pressure, voltage = pressure_sensor.read_pressure()
            if pressure is not None:
                print("Pressure: %.3f MPa (%.3fV)" % (pressure, voltage))
            else:
                print("Pressure: read failed")

        # --- Water Flow ---
        rate_lpm, total_liters = flow.read()
        print("Flow: %.2f L/min, Total: %.3f L" % (rate_lpm, total_liters))

        # --- Valve Status ---
        print("Valve: %s" % ("OPEN" if valve.is_open else "CLOSED"))

        # --- Pump Status ---
        if pump_a:
            print(pump_a.status())
        if pump_b:
            print(pump_b.status())

        # --- Relay Status ---
        print(water_pump.status())
        print(grow_light.status())

        print("---")
        utime.sleep(2)


if __name__ == "__main__":
    main()
