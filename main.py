"""
AS7341 + AS7263 Spectral Sensor Example for EC800X QuecDuino (QuecPython).
Wiring:
  I2C0 SCL = GPIO67 (Pin 17), SDA = GPIO66 (Pin 16)
  AS7263: addr 0x49 (NIR 610-860nm)
  AS7341: addr 0x39 (VIS+NIR 390-890nm)
"""

from machine import I2C
import utime

from quec_i2c import QuecI2C, I2CDevice
from as7341 import AS7341
from as7263 import AS7263


def main():
    # Initialize I2C bus 0 at 400KHz
    i2c = QuecI2C(I2C.I2C0, I2C.FAST_MODE)

    # Scan for devices
    devices = i2c.scan()
    print("I2C devices found:", [hex(d) for d in devices])

    # Initialize AS7263 (NIR sensor)
    nir = None
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

    # Initialize AS7341 (VIS+NIR sensor)
    vis = None
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

    # Main loop
    while True:
        if nir:
            data = nir.measure()
            if data:
                print("AS7263: R=%d S=%d T=%d U=%d V=%d W=%d" %
                      (data["R"], data["S"], data["T"],
                       data["U"], data["V"], data["W"]))

        if vis:
            data = vis.all_channels
            if data:
                print("AS7341: F1=%d F2=%d F3=%d F4=%d F5=%d F6=%d F7=%d F8=%d CLR=%d NIR=%d" %
                      (data["F1"], data["F2"], data["F3"], data["F4"],
                       data["F5"], data["F6"], data["F7"], data["F8"],
                       data["CLEAR"], data["NIR"]))

            # Flicker detection
            vis.configure_flicker_detection()
            utime.sleep_ms(100)
            flicker = vis.flicker_detected
            if flicker:
                print("AS7341: Flicker detected: %d Hz" % flicker)
            # Re-enable spectral measurement for next reading
            vis.initialize()

        utime.sleep(2)


if __name__ == "__main__":
    main()
