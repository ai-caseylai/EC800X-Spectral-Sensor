"""
AS7263 NIR Spectral Sensor Driver for QuecPython (EC800X QuecDuino).
Ported from SparkFun Qwiic AS726X Python Library.
I2C address: 0x49, Virtual Register Protocol.
6 channels: R(610nm) S(680nm) T(730nm) U(760nm) V(810nm) W(860nm).
"""

import utime

# I2C address
AS7263_ADDR = 0x49

# Physical registers for virtual register protocol
_STATUS_REG = 0x00
_WRITE_REG = 0x01
_READ_REG = 0x02

# Status bits
_TX_VALID = 0x02
_RX_VALID = 0x01

# Virtual registers
_REG_HW_VERSION = 0x01
_REG_CONFIG = 0x04
_REG_INT_T = 0x05
_REG_DEVICE_TEMP = 0x06
_REG_LED_CONFIG = 0x07

# AS7263 channel registers
_CH_R = 0x08
_CH_S = 0x0A
_CH_T = 0x0C
_CH_U = 0x0E
_CH_V = 0x10
_CH_W = 0x12

# Sensor type
_SENSOR_TYPE_AS7263 = 0x3F

# Gain constants
GAIN_X1 = 0x00
GAIN_X3_7 = 0x01
GAIN_X16 = 0x02
GAIN_X64 = 0x03

# Measurement mode constants
MODE_4CHAN = 0x00
MODE_4CHAN2 = 0x01
MODE_6CHAN_CONTINUOUS = 0x02
MODE_6CHAN_ONE_SHOT = 0x03

# LED/bulb current
BULB_CURRENT_12_5MA = 0x00
BULB_CURRENT_25MA = 0x01
BULB_CURRENT_50MA = 0x02
BULB_CURRENT_100MA = 0x03

# Indicator current
INDICATOR_CURRENT_1MA = 0x00
INDICATOR_CURRENT_2MA = 0x01
INDICATOR_CURRENT_4MA = 0x02
INDICATOR_CURRENT_8MA = 0x03

# Config register bit masks
_CONFIG_SRST_MASK = 0x01 << 7
_CONFIG_INT_MASK = 0x01 << 6
_CONFIG_GAIN_MASK = 0x03 << 4
_CONFIG_MODE_MASK = 0x03 << 2
_CONFIG_DATA_READY_MASK = 0x01 << 1

# LED config register bit masks
_LED_DRV_MASK = 0x03 << 4
_LED_ENABLE_MASK = 0x01 << 3
_LED_IND_CURRENT_MASK = 0x03 << 1
_LED_IND_ENABLE_MASK = 0x01 << 0

_POLLING_DELAY_MS = 5
_MAX_RETRIES = 100
_TIMEOUT_MS = 3000


class AS7263:
    """AS7263 NIR spectral sensor driver."""

    def __init__(self, i2c, addr=AS7263_ADDR):
        """
        Initialize AS7263 sensor.

        Args:
            i2c: QuecI2C instance
            addr: I2C address (default 0x49)
        """
        self._i2c = i2c
        self._addr = addr

    def begin(self, gain=GAIN_X64, mode=MODE_6CHAN_ONE_SHOT):
        """
        Initialize sensor with default settings.

        Returns:
            True if sensor found and configured, False otherwise.
        """
        hw_ver = self._virtual_read(_REG_HW_VERSION)
        if hw_ver is None or hw_ver < 0:
            return False
        if hw_ver != _SENSOR_TYPE_AS7263:
            print("AS7263: wrong sensor type, HW_VERSION=0x%02X" % hw_ver)
            return False

        self.set_bulb_current(BULB_CURRENT_12_5MA)
        self.disable_bulb()
        self.set_indicator_current(INDICATOR_CURRENT_8MA)
        self.disable_indicator()
        self.set_integration_time(50)
        self.set_gain(gain)
        self.set_measurement_mode(mode)
        return True

    # -- Virtual Register Protocol --

    def _virtual_read(self, virtual_addr):
        """Read a virtual register."""
        # Clear stale RX data
        status = self._i2c.read_reg_byte(self._addr, _STATUS_REG)
        if status is None:
            return None
        if status & _RX_VALID:
            self._i2c.read_reg_byte(self._addr, _READ_REG)

        # Wait for TX_VALID to clear
        for _ in range(_MAX_RETRIES):
            status = self._i2c.read_reg_byte(self._addr, _STATUS_REG)
            if status is None:
                return None
            if (status & _TX_VALID) == 0:
                break
            utime.sleep_ms(_POLLING_DELAY_MS)
        else:
            return None

        # Send virtual register address (bit 7 = 0 for read)
        self._i2c.write_reg(self._addr, _WRITE_REG, virtual_addr)

        # Wait for RX_VALID
        for _ in range(_MAX_RETRIES):
            status = self._i2c.read_reg_byte(self._addr, _STATUS_REG)
            if status is None:
                return None
            if status & _RX_VALID:
                break
            utime.sleep_ms(_POLLING_DELAY_MS)
        else:
            return None

        return self._i2c.read_reg_byte(self._addr, _READ_REG)

    def _virtual_write(self, virtual_addr, data):
        """Write a virtual register. Returns True on success."""
        # Wait for TX_VALID to clear
        for _ in range(_MAX_RETRIES):
            status = self._i2c.read_reg_byte(self._addr, _STATUS_REG)
            if status is None:
                return False
            if (status & _TX_VALID) == 0:
                break
            utime.sleep_ms(_POLLING_DELAY_MS)
        else:
            return False

        # Send virtual register address (bit 7 = 1 for write)
        self._i2c.write_reg(self._addr, _WRITE_REG, virtual_addr | 0x80)

        # Wait for TX_VALID to clear
        for _ in range(_MAX_RETRIES):
            status = self._i2c.read_reg_byte(self._addr, _STATUS_REG)
            if status is None:
                return False
            if (status & _TX_VALID) == 0:
                break
            utime.sleep_ms(_POLLING_DELAY_MS)
        else:
            return False

        # Send data
        self._i2c.write_reg(self._addr, _WRITE_REG, data)
        return True

    # -- Channel read (big-endian: high byte first) --

    def _read_channel(self, reg):
        """Read a 16-bit channel value (big-endian)."""
        hi = self._virtual_read(reg)
        if hi is None:
            return None
        lo = self._virtual_read(reg + 1)
        if lo is None:
            return None
        return (hi << 8) | lo

    # -- Configuration --

    def set_gain(self, gain):
        """Set gain (GAIN_X1, GAIN_X3_7, GAIN_X16, GAIN_X64)."""
        if gain > GAIN_X64:
            gain = GAIN_X64
        val = self._virtual_read(_REG_CONFIG)
        if val is None:
            return False
        val = (val & ~_CONFIG_GAIN_MASK) | (gain << 4)
        return self._virtual_write(_REG_CONFIG, val)

    def get_gain(self):
        """Get current gain value."""
        val = self._virtual_read(_REG_CONFIG)
        if val is None:
            return None
        return (val & _CONFIG_GAIN_MASK) >> 4

    def set_integration_time(self, value):
        """Set integration time (0-255, actual time = value * 2.8ms)."""
        return self._virtual_write(_REG_INT_T, value)

    def get_integration_time(self):
        """Get integration time."""
        return self._virtual_read(_REG_INT_T)

    def set_measurement_mode(self, mode):
        """Set measurement mode (MODE_4CHAN, MODE_4CHAN2, MODE_6CHAN_CONTINUOUS, MODE_6CHAN_ONE_SHOT)."""
        if mode > MODE_6CHAN_ONE_SHOT:
            mode = MODE_6CHAN_ONE_SHOT
        val = self._virtual_read(_REG_CONFIG)
        if val is None:
            return False
        val = (val & ~_CONFIG_MODE_MASK) | (mode << 2)
        return self._virtual_write(_REG_CONFIG, val)

    def get_measurement_mode(self):
        """Get measurement mode."""
        val = self._virtual_read(_REG_CONFIG)
        if val is None:
            return None
        return (val & _CONFIG_MODE_MASK) >> 2

    def data_available(self):
        """Check if data is ready."""
        val = self._virtual_read(_REG_CONFIG)
        if val is None:
            return False
        return (val & _CONFIG_DATA_READY_MASK) != 0

    def _clear_data_available(self):
        """Clear data ready flag."""
        val = self._virtual_read(_REG_CONFIG)
        if val is not None:
            self._virtual_write(_REG_CONFIG, val & ~_CONFIG_DATA_READY_MASK)

    # -- Measurement --

    def take_measurements(self):
        """
        Take one-shot measurement of all 6 channels.
        Returns True on success, False on timeout.
        """
        self._clear_data_available()
        self.set_measurement_mode(MODE_6CHAN_ONE_SHOT)

        deadline = utime.ticks_ms() + _TIMEOUT_MS
        while utime.ticks_ms() < deadline:
            if self.data_available():
                return True
            utime.sleep_ms(_POLLING_DELAY_MS)
        print("AS7263: measurement timeout")
        return False

    def read_channels(self):
        """
        Read all 6 NIR channel values.
        Returns dict {R, S, T, U, V, W} or None.
        """
        r = self._read_channel(_CH_R)
        s = self._read_channel(_CH_S)
        t = self._read_channel(_CH_T)
        u = self._read_channel(_CH_U)
        v = self._read_channel(_CH_V)
        w = self._read_channel(_CH_W)
        if r is None:
            return None
        return {"R": r, "S": s, "T": t, "U": u, "V": v, "W": w}

    def measure(self):
        """
        Take measurement and read all channels (convenience).
        Returns dict {R, S, T, U, V, W} or None.
        """
        if not self.take_measurements():
            return None
        return self.read_channels()

    # -- Bulb/LED control --

    def enable_bulb(self):
        """Enable onboard IR illumination bulb."""
        val = self._virtual_read(_REG_LED_CONFIG)
        if val is None:
            return False
        return self._virtual_write(_REG_LED_CONFIG, val | _LED_ENABLE_MASK)

    def disable_bulb(self):
        """Disable onboard bulb."""
        val = self._virtual_read(_REG_LED_CONFIG)
        if val is None:
            return False
        return self._virtual_write(_REG_LED_CONFIG, val & ~_LED_ENABLE_MASK)

    def set_bulb_current(self, current):
        """Set bulb current (BULB_CURRENT_12_5MA..BULB_CURRENT_100MA)."""
        if current > BULB_CURRENT_100MA:
            current = BULB_CURRENT_100MA
        val = self._virtual_read(_REG_LED_CONFIG)
        if val is None:
            return False
        val = (val & ~_LED_DRV_MASK) | (current << 4)
        return self._virtual_write(_REG_LED_CONFIG, val)

    def enable_indicator(self):
        """Enable indicator LED."""
        val = self._virtual_read(_REG_LED_CONFIG)
        if val is None:
            return False
        return self._virtual_write(_REG_LED_CONFIG, val | _LED_IND_ENABLE_MASK)

    def disable_indicator(self):
        """Disable indicator LED."""
        val = self._virtual_read(_REG_LED_CONFIG)
        if val is None:
            return False
        return self._virtual_write(_REG_LED_CONFIG, val & ~_LED_IND_ENABLE_MASK)

    def set_indicator_current(self, current):
        """Set indicator LED current."""
        if current > INDICATOR_CURRENT_8MA:
            current = INDICATOR_CURRENT_8MA
        val = self._virtual_read(_REG_LED_CONFIG)
        if val is None:
            return False
        val = (val & ~_LED_IND_CURRENT_MASK) | (current << 1)
        return self._virtual_write(_REG_LED_CONFIG, val)

    # -- Misc --

    def get_temperature(self):
        """Get raw temperature value."""
        return self._virtual_read(_REG_DEVICE_TEMP)

    def soft_reset(self):
        """Soft reset the sensor."""
        val = self._virtual_read(_REG_CONFIG)
        if val is None:
            return False
        return self._virtual_write(_REG_CONFIG, val | _CONFIG_SRST_MASK)

    def get_hw_version(self):
        """Get hardware version register."""
        return self._virtual_read(_REG_HW_VERSION)
