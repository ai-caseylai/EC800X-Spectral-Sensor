"""
AS7341 Spectral Sensor Driver for QuecPython (EC800X QuecDuino).
Ported from Adafruit CircuitPython AS7341 Library.
I2C address: 0x39, Direct Register Access.
10 channels: F1-F8 (415-680nm) + CLEAR + NIR.
"""

import utime

# I2C address
AS7341_ADDR = 0x39

# Register map
_REG_CONFIG = 0x70
_REG_GPIO = 0x73
_REG_LED = 0x74
_REG_ENABLE = 0x80
_REG_ATIME = 0x81
_REG_SP_LOW_TH_L = 0x84
_REG_SP_LOW_TH_H = 0x85
_REG_SP_HIGH_TH_L = 0x86
_REG_SP_HIGH_TH_H = 0x87
_REG_STATUS = 0x93
_REG_ASTATUS = 0x94
_REG_CH0_DATA_L = 0x95
_REG_STATUS2 = 0xA3
_REG_STATUS3 = 0xA4
_REG_CFG0 = 0xA9
_REG_CFG1 = 0xAA
_REG_CFG6 = 0xAF
_REG_CFG9 = 0xB2
_REG_CFG12 = 0xB5
_REG_PERS = 0xBD
_REG_GPIO2 = 0xBE
_REG_ASTEP_L = 0xCA
_REG_ASTEP_H = 0xCB
_REG_FD_CFG0 = 0xD7
_REG_FD_TIME1 = 0xD8
_REG_FD_TIME2 = 0xDA
_REG_FD_STATUS = 0xDB
_REG_INTENAB = 0xF9
_REG_CONTROL = 0xFA
_REG_WHOAMI = 0x92

# Expected chip ID
_DEVICE_ID = 0b001001  # bits 2-7 of WHOAMI register
_CHIP_ID = 0x09

# Gain constants
GAIN_0_5X = 0
GAIN_1X = 1
GAIN_2X = 2
GAIN_4X = 3
GAIN_8X = 4
GAIN_16X = 5
GAIN_32X = 6
GAIN_64X = 7
GAIN_128X = 8
GAIN_256X = 9
GAIN_512X = 10

# SMUX output selectors
SMUX_DISABLED = 0
SMUX_ADC0 = 1
SMUX_ADC1 = 2
SMUX_ADC2 = 3
SMUX_ADC3 = 4
SMUX_ADC4 = 5
SMUX_ADC5 = 6

# SMUX input indices
SMUX_IN_NC_F3L = 0
SMUX_IN_F1L_NC = 1
SMUX_IN_NC_NC0 = 2
SMUX_IN_NC_F8L = 3
SMUX_IN_F6L_NC = 4
SMUX_IN_F2L_F4L = 5
SMUX_IN_NC_F5L = 6
SMUX_IN_F7L_NC = 7
SMUX_IN_NC_CL = 8
SMUX_IN_NC_F5R = 9
SMUX_IN_F7R_NC = 10
SMUX_IN_NC_NC1 = 11
SMUX_IN_NC_F2R = 12
SMUX_IN_F4R_NC = 13
SMUX_IN_F8R_F6R = 14
SMUX_IN_NC_F3R = 15
SMUX_IN_F1R_EXT_GPIO = 16
SMUX_IN_EXT_INT_CR = 17
SMUX_IN_NC_DARK = 18
SMUX_IN_NIR_F = 19

_TIMEOUT_MS = 1000


class AS7341:
    """AS7341 10-channel spectral sensor driver."""

    def __init__(self, i2c_device, addr=AS7341_ADDR):
        """
        Initialize AS7341 sensor.

        Args:
            i2c_device: I2CDevice instance from quec_i2c
            addr: I2C address (default 0x39)
        """
        self._dev = i2c_device
        self._addr = addr
        self._low_channels_configured = False
        self._high_channels_configured = False
        self._flicker_1k_configured = False

        # Verify chip ID
        chip_id = self._read_reg(_REG_WHOAMI)
        if chip_id is None:
            raise RuntimeError("AS7341: I2C communication failed")
        device_id = (chip_id >> 2) & 0x3F
        if device_id != _DEVICE_ID:
            raise RuntimeError("AS7341: chip ID mismatch (got 0x%02X)" % chip_id)

        self.initialize()

    # -- Low-level register access --

    def _read_reg(self, reg):
        """Read a single register byte."""
        out_buf = bytearray([reg])
        in_buf = bytearray(1)
        self._dev.write_then_readinto(out_buf, in_buf)
        return in_buf[0]

    def _read_reg_16(self, reg):
        """Read a 16-bit LE register."""
        out_buf = bytearray([reg])
        in_buf = bytearray(2)
        self._dev.write_then_readinto(out_buf, in_buf)
        return in_buf[0] | (in_buf[1] << 8)

    def _write_reg(self, reg, value):
        """Write a single register byte."""
        buf = bytearray([reg, value])
        self._dev.write(buf)

    # -- Register bit helpers --

    def _read_bit(self, reg, bit):
        """Read a single bit from a register."""
        val = self._read_reg(reg)
        return (val >> bit) & 1

    def _write_bit(self, reg, bit, value):
        """Write a single bit to a register."""
        val = self._read_reg(reg)
        if value:
            val |= (1 << bit)
        else:
            val &= ~(1 << bit)
        self._write_reg(reg, val)

    def _read_bits(self, reg, bit_start, num_bits):
        """Read multiple bits from a register."""
        val = self._read_reg(reg)
        mask = (1 << num_bits) - 1
        return (val >> bit_start) & mask

    def _write_bits(self, reg, bit_start, num_bits, value):
        """Write multiple bits to a register."""
        val = self._read_reg(reg)
        mask = (1 << num_bits) - 1
        val &= ~(mask << bit_start)
        val |= (value & mask) << bit_start
        self._write_reg(reg, val)

    # -- Properties using register bits --

    @property
    def _power_enabled(self):
        return self._read_bit(_REG_ENABLE, 0)

    @_power_enabled.setter
    def _power_enabled(self, val):
        self._write_bit(_REG_ENABLE, 0, val)

    @property
    def _color_meas_enabled(self):
        return self._read_bit(_REG_ENABLE, 1)

    @_color_meas_enabled.setter
    def _color_meas_enabled(self, val):
        self._write_bit(_REG_ENABLE, 1, val)

    @property
    def _smux_enable_bit(self):
        return self._read_bit(_REG_ENABLE, 4)

    @_smux_enable_bit.setter
    def _smux_enable_bit(self, val):
        self._write_bit(_REG_ENABLE, 4, val)

    @property
    def _smux_command(self):
        return self._read_bits(_REG_CFG6, 3, 2)

    @_smux_command.setter
    def _smux_command(self, val):
        self._write_bits(_REG_CFG6, 3, 2, val)

    @property
    def _low_bank_active(self):
        return self._read_bit(_REG_CFG0, 4)

    @_low_bank_active.setter
    def _low_bank_active(self, val):
        self._write_bit(_REG_CFG0, 4, val)

    @property
    def _led_control_enable_bit(self):
        return self._read_bit(_REG_CONFIG, 3)

    @_led_control_enable_bit.setter
    def _led_control_enable_bit(self, val):
        self._write_bit(_REG_CONFIG, 3, val)

    @property
    def _data_ready_bit(self):
        return self._read_bit(_REG_STATUS2, 6)

    # -- Channel data (little-endian) --

    @property
    def _channel_0_data(self):
        return self._read_reg_16(_REG_CH0_DATA_L)

    @property
    def _channel_1_data(self):
        return self._read_reg_16(_REG_CH0_DATA_L + 2)

    @property
    def _channel_2_data(self):
        return self._read_reg_16(_REG_CH0_DATA_L + 4)

    @property
    def _channel_3_data(self):
        return self._read_reg_16(_REG_CH0_DATA_L + 6)

    @property
    def _channel_4_data(self):
        return self._read_reg_16(_REG_CH0_DATA_L + 8)

    @property
    def _channel_5_data(self):
        return self._read_reg_16(_REG_CH0_DATA_L + 10)

    @property
    def _all_channels(self):
        """Read 6 ADC channels. Triggers measurement latch by reading ASTATUS first."""
        self._read_reg(_REG_ASTATUS)
        return (
            self._channel_0_data,
            self._channel_1_data,
            self._channel_2_data,
            self._channel_3_data,
            self._channel_4_data,
            self._channel_5_data,
        )

    # -- Initialization --

    def initialize(self):
        """Configure sensor with default settings."""
        self._power_enabled = True
        self._led_control_enable_bit = True
        self.atime = 100
        self.astep = 999
        self.gain = GAIN_128X

    # -- SMUX configuration --

    def _set_smux(self, addr, out1, out2):
        """Write SMUX routing byte: low nibble=out1, high nibble=out2."""
        byte_val = (out2 << 4) | out1
        self._write_reg(addr, byte_val)

    def _f1f4_clear_nir(self):
        """Configure SMUX for F1-F4 + Clear + NIR."""
        self._set_smux(SMUX_IN_NC_F3L, SMUX_DISABLED, SMUX_ADC2)
        self._set_smux(SMUX_IN_F1L_NC, SMUX_ADC0, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_NC0, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_F8L, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F6L_NC, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F2L_F4L, SMUX_ADC1, SMUX_ADC3)
        self._set_smux(SMUX_IN_NC_F5L, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F7L_NC, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_CL, SMUX_DISABLED, SMUX_ADC4)
        self._set_smux(SMUX_IN_NC_F5R, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F7R_NC, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_NC1, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_F2R, SMUX_DISABLED, SMUX_ADC1)
        self._set_smux(SMUX_IN_F4R_NC, SMUX_ADC3, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F8R_F6R, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_F3R, SMUX_DISABLED, SMUX_ADC2)
        self._set_smux(SMUX_IN_F1R_EXT_GPIO, SMUX_ADC0, SMUX_DISABLED)
        self._set_smux(SMUX_IN_EXT_INT_CR, SMUX_DISABLED, SMUX_ADC4)
        self._set_smux(SMUX_IN_NC_DARK, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NIR_F, SMUX_ADC5, SMUX_DISABLED)

    def _f5f8_clear_nir(self):
        """Configure SMUX for F5-F8 + Clear + NIR."""
        self._set_smux(SMUX_IN_NC_F3L, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F1L_NC, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_NC0, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_F8L, SMUX_DISABLED, SMUX_ADC3)
        self._set_smux(SMUX_IN_F6L_NC, SMUX_ADC1, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F2L_F4L, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_F5L, SMUX_DISABLED, SMUX_ADC0)
        self._set_smux(SMUX_IN_F7L_NC, SMUX_ADC2, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_CL, SMUX_DISABLED, SMUX_ADC4)
        self._set_smux(SMUX_IN_NC_F5R, SMUX_DISABLED, SMUX_ADC0)
        self._set_smux(SMUX_IN_F7R_NC, SMUX_ADC2, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_NC1, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NC_F2R, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F4R_NC, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F8R_F6R, SMUX_ADC3, SMUX_ADC1)
        self._set_smux(SMUX_IN_NC_F3R, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_F1R_EXT_GPIO, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_EXT_INT_CR, SMUX_DISABLED, SMUX_ADC4)
        self._set_smux(SMUX_IN_NC_DARK, SMUX_DISABLED, SMUX_DISABLED)
        self._set_smux(SMUX_IN_NIR_F, SMUX_ADC5, SMUX_DISABLED)

    def _wait_for_data(self, timeout_ms=_TIMEOUT_MS):
        """Wait for sensor data to be ready."""
        start = utime.ticks_ms()
        while not self._data_ready_bit:
            if utime.ticks_diff(utime.ticks_ms(), start) > timeout_ms:
                raise RuntimeError("AS7341: timeout waiting for data")

    @property
    def _smux_enabled(self):
        return self._smux_enable_bit

    @_smux_enabled.setter
    def _smux_enabled(self, enable):
        self._low_bank_active = False
        self._smux_enable_bit = enable
        if enable:
            while self._smux_enable_bit:
                utime.sleep_ms(1)

    def _configure_f1_f4(self):
        """Configure sensor to read F1-F4 + Clear + NIR."""
        if self._low_channels_configured:
            _ = self._all_channels
            return
        self._high_channels_configured = False
        self._flicker_1k_configured = False
        self._color_meas_enabled = False
        self._smux_command = 2
        self._f1f4_clear_nir()
        self._smux_enabled = True
        self._color_meas_enabled = True
        self._low_channels_configured = True
        self._wait_for_data()

    def _configure_f5_f8(self):
        """Configure sensor to read F5-F8 + Clear + NIR."""
        if self._high_channels_configured:
            _ = self._all_channels
            return
        self._low_channels_configured = False
        self._flicker_1k_configured = False
        self._color_meas_enabled = False
        self._smux_command = 2
        self._f5f8_clear_nir()
        self._smux_enabled = True
        self._color_meas_enabled = True
        self._high_channels_configured = True
        self._wait_for_data()

    # -- Public API --

    @property
    def all_channels(self):
        """
        Read all 10 spectral channels.
        Returns dict {F1..F8, CLEAR, NIR} or None.
        """
        self._configure_f1_f4()
        lo = self._all_channels

        self._configure_f5_f8()
        hi = self._all_channels

        return {
            "F1": lo[0],
            "F2": lo[1],
            "F3": lo[2],
            "F4": lo[3],
            "CLEAR": lo[4],
            "NIR": lo[5],
            "F5": hi[0],
            "F6": hi[1],
            "F7": hi[2],
            "F8": hi[3],
            "CLEAR2": hi[4],
            "NIR2": hi[5],
        }

    @property
    def channel_415nm(self):
        self._configure_f1_f4()
        return self._channel_0_data

    @property
    def channel_445nm(self):
        self._configure_f1_f4()
        return self._channel_1_data

    @property
    def channel_480nm(self):
        self._configure_f1_f4()
        return self._channel_2_data

    @property
    def channel_515nm(self):
        self._configure_f1_f4()
        return self._channel_3_data

    @property
    def channel_555nm(self):
        self._configure_f5_f8()
        return self._channel_0_data

    @property
    def channel_590nm(self):
        self._configure_f5_f8()
        return self._channel_1_data

    @property
    def channel_630nm(self):
        self._configure_f5_f8()
        return self._channel_2_data

    @property
    def channel_680nm(self):
        self._configure_f5_f8()
        return self._channel_3_data

    @property
    def channel_clear(self):
        _ = self._all_channels
        return self._channel_4_data

    @property
    def channel_nir(self):
        _ = self._all_channels
        return self._channel_5_data

    # -- Gain, ATIME, ASTEP --

    @property
    def gain(self):
        """Get ADC gain value."""
        return self._read_reg(_REG_CFG1)

    @gain.setter
    def gain(self, value):
        """Set ADC gain (GAIN_0_5X..GAIN_512X)."""
        self._write_reg(_REG_CFG1, value)

    @property
    def atime(self):
        """Get integration time step count."""
        return self._read_reg(_REG_ATIME)

    @atime.setter
    def atime(self, value):
        """Set integration time step count (0-255)."""
        self._write_reg(_REG_ATIME, value)

    @property
    def astep(self):
        """Get integration step size."""
        lo = self._read_reg(_REG_ASTEP_L)
        hi = self._read_reg(_REG_ASTEP_H)
        return lo | (hi << 8)

    @astep.setter
    def astep(self, value):
        """Set integration step size (0-65534)."""
        self._write_reg(_REG_ASTEP_L, value & 0xFF)
        self._write_reg(_REG_ASTEP_H, (value >> 8) & 0xFF)

    # -- LED control (requires low bank) --

    @property
    def led(self):
        """Get LED on/off state."""
        old_bank = self._low_bank_active
        self._low_bank_active = True
        val = self._read_reg(_REG_LED)
        self._low_bank_active = old_bank
        return (val & 0x80) != 0

    @led.setter
    def led(self, on):
        """Set LED on/off."""
        self._low_bank_active = True
        val = self._read_reg(_REG_LED)
        if on:
            val |= 0x80
        else:
            val &= ~0x80
        self._write_reg(_REG_LED, val)
        self._low_bank_active = False

    @property
    def led_current(self):
        """Get LED current in mA."""
        self._low_bank_active = True
        val = self._read_reg(_REG_LED)
        self._low_bank_active = False
        return ((val & 0x03) * 2) + 4

    @led_current.setter
    def led_current(self, current_ma):
        """Set LED current (4-258 mA, rounded to even)."""
        new_val = int((min(258, max(4, current_ma)) - 4) / 2)
        self._low_bank_active = True
        val = self._read_reg(_REG_LED)
        val = (val & ~0x03) | (new_val & 0x03)
        self._write_reg(_REG_LED, val)
        self._low_bank_active = False

    # -- Flicker detection (1000Hz/1200Hz) --

    def configure_flicker_detection(self):
        """Configure sensor for 1000Hz/1200Hz flicker detection."""
        self._low_channels_configured = False
        self._high_channels_configured = False

        # RAM bank 0
        self._write_reg(_REG_CFG0, 0x00)
        coeffs_bank0 = [
            (0x04, 0x9E), (0x05, 0x36), (0x0E, 0x2E), (0x0F, 0x1B),
            (0x18, 0x7D), (0x19, 0x36), (0x22, 0x09), (0x23, 0x1B),
            (0x2C, 0x5B), (0x2D, 0x36), (0x36, 0xE5), (0x37, 0x1A),
            (0x40, 0x3A), (0x41, 0x36), (0x4A, 0xC1), (0x4B, 0x1A),
            (0x54, 0x18), (0x55, 0x36), (0x5E, 0x9C), (0x5F, 0x1A),
            (0x68, 0xF6), (0x69, 0x35), (0x72, 0x78), (0x73, 0x1A),
            (0x7C, 0x4D), (0x7D, 0x35),
        ]
        for reg, val in coeffs_bank0:
            self._write_reg(reg, val)

        # RAM bank 1
        self._write_reg(_REG_CFG0, 0x01)
        coeffs_bank1 = [
            (0x06, 0x54), (0x07, 0x1A),
            (0x10, 0xB3), (0x11, 0x35),
            (0x1A, 0x2F), (0x1B, 0x1A),
        ]
        for reg, val in coeffs_bank1:
            self._write_reg(reg, val)

        self._write_reg(_REG_CFG0, 0x01)

        # FD configuration
        self._write_reg(_REG_FD_CFG0, 0x60)
        self._write_reg(_REG_FD_TIME1, 0x40)
        self._write_reg(0xD9, 0x25)
        self._write_reg(_REG_FD_TIME2, 0x48)
        self._write_reg(_REG_CFG9, 0x40)
        self._write_reg(_REG_ENABLE, 0x41)

        self._flicker_1k_configured = True

    @property
    def flicker_detected(self):
        """
        Get detected flicker frequency in Hz.
        Returns 1000, 1200, or None.
        Must call configure_flicker_detection() first.
        """
        if not self._flicker_1k_configured:
            return None
        fd_status = self._read_reg(_REG_FD_STATUS)
        if fd_status == 45:
            return 1000
        if fd_status == 46:
            return 1200
        return None

    # -- Convenience --

    def measure(self):
        """Read all channels as dict (convenience)."""
        return self.all_channels
