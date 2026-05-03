"""
Spectral + Water Quality Sensor Example for EC800X QuecDuino (QuecPython).

Sensors:
  AS7263 (0x49) — NIR 610-860nm, I2C
  AS7341 (0x39) — VIS+NIR 390-890nm, I2C
  BA121        — Conductivity + Temperature, UART 9600bps
  PH4502C      — pH, Analog ADC

Wiring:
  I2C0:  SCL=GPIO67 (Pin 17), SDA=GPIO66 (Pin 16)
  UART1: TX=GPIO, RX=GPIO (to BA121 pin4/5)
  ADC0:  via voltage divider from PH4502C Po pin
"""

from machine import I2C, UART, ADC
import utime

from quec_i2c import QuecI2C, I2CDevice
from as7341 import AS7341
from as7263 import AS7263
from ba121 import BA121
from ph4502c import PH4502C


def init_spectral(i2c, devices):
    """Initialize AS7263 and AS7341 spectral sensors."""
    nir = None
    vis = None

    # AS7263 (NIR sensor, addr 0x49)
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

    # AS7341 (VIS+NIR sensor, addr 0x39)
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
    # Adjust UART port and pins to your wiring
    # BA121 pin4 (RXD) -> MCU TX, BA121 pin5 (TXD) -> MCU RX
    sensor = BA121(UART.UART1, 0, 0)
    if sensor.init():
        print("BA121: found")
        return sensor
    print("BA121: init failed")
    return None


def init_ph4502c():
    """Initialize PH4502C pH sensor via ADC."""
    # Adjust divider_ratio to match your voltage divider
    # Example: R1=33K, R2=10K → ratio = 10/43 ≈ 0.233
    # If connecting directly to a 5V-tolerant ADC, set ratio=1.0
    sensor = PH4502C(
        adc_channel=ADC.ADC0,
        divider_ratio=0.233,
    )
    if sensor.init():
        print("PH4502C: found")
        return sensor
    print("PH4502C: init failed")
    return None


def main():
    # Initialize I2C bus 0 at 400KHz
    i2c = QuecI2C(I2C.I2C0, I2C.FAST_MODE)

    # Scan for I2C devices
    devices = i2c.scan()
    print("I2C devices found:", [hex(d) for d in devices])

    # Initialize all sensors
    nir, vis = init_spectral(i2c, devices)
    ba121 = init_ba121()
    ph_sensor = init_ph4502c()

    print("")
    print("=== All sensors initialized, starting main loop ===")
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
                # Convert uS/cm to mS/cm for display
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

        print("---")
        utime.sleep(2)


if __name__ == "__main__":
    main()
