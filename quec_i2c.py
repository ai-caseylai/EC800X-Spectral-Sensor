"""
QuecPython I2C adapter layer for EC800X QuecDuino.
Provides QuecI2C (low-level) and I2CDevice (Adafruit-compatible) classes.
Wraps QuecPython's unique I2C.read()/I2C.write() API.
"""

from machine import I2C


class QuecI2C:
    """Low-level QuecPython I2C wrapper."""

    def __init__(self, i2c_bus=I2C.I2C0, freq=I2C.FAST_MODE):
        self._i2c = I2C(i2c_bus, freq)

    def write_reg(self, addr, reg, value):
        """Write a single register byte. Returns True on success."""
        ret = self._i2c.write(addr, bytearray([reg]), 1,
                              bytearray([value]), 1)
        return ret == 0

    def read_reg(self, addr, reg, length=1):
        """Read register(s). Returns bytearray or None on failure."""
        buf = bytearray(length)
        ret = self._i2c.read(addr, bytearray([reg]), 1, buf, length, 0)
        return buf if ret == 0 else None

    def read_reg_byte(self, addr, reg):
        """Read a single register byte. Returns int or None."""
        buf = self.read_reg(addr, reg, 1)
        return buf[0] if buf else None

    def write_reg_bytes(self, addr, reg, data):
        """Write register address + multiple data bytes."""
        if isinstance(data, int):
            data = bytearray([data])
        elif not isinstance(data, (bytes, bytearray)):
            data = bytearray(data)
        ret = self._i2c.write(addr, bytearray([reg]), 1,
                              data, len(data))
        return ret == 0

    def scan(self):
        """Scan for I2C devices. Returns list of addresses."""
        return self._i2c.scan()


class I2CDevice:
    """Adafruit I2CDevice-compatible interface for QuecPython."""

    def __init__(self, i2c, addr):
        self._i2c = i2c   # QuecI2C instance
        self._addr = addr

    def write(self, buf, *, start=0, end=None):
        """Write: buf[0] = register, buf[1:] = data."""
        end = end or len(buf)
        reg = buf[start]
        data = buf[start + 1:end]
        if len(data) == 0:
            return
        self._i2c.write_reg_bytes(self._addr, reg, data)

    def write_then_readinto(self, out_buf, in_buf, *,
                            out_start=0, out_end=None,
                            in_start=0, in_end=None):
        """Write register address, then read data back."""
        out_end = out_end or len(out_buf)
        in_end = in_end or len(in_buf)
        reg = out_buf[out_start]
        length = in_end - in_start
        result = self._i2c.read_reg(self._addr, reg, length)
        if result:
            in_buf[in_start:in_end] = result
