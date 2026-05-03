"""
PH4502C pH Sensor Driver for QuecPython (EC800X).
Analog pH probe module — reads pH via ADC.

Module pin connections:
  V+  -> 5V
  G   -> GND (both analog and digital GND)
  Po  -> ADC input pin (via voltage divider!)
  Do  -> Digital threshold output (optional)
  To  -> Temperature analog output (optional, often unreliable)

IMPORTANT: PH4502C outputs 0-5V, but EC800X ADC accepts 0-1.3V max.
You MUST use a voltage divider on the Po pin:
  Example: R1=33K, R2=10K → V_adc = V_po * 10/43 ≈ V_po * 0.233
  Set divider_ratio accordingly.

pH formula (from nthnn/PH4502C-Sensor library):
  pH = calibration + (V_mid - V_actual) / pH_step
  Default: calibration=14.8, V_mid=2.5V, pH_step=0.18V/pH

Calibration:
  1. Hardware: short BNC, adjust pot until Po reads 2.5V
  2. Software: measure known buffer solutions, adjust calibration/ph_step
"""

from machine import ADC
import utime

# Default calibration constants
DEFAULT_CALIBRATION = 14.8
DEFAULT_PH_STEP = 0.18
DEFAULT_MID_VOLTAGE = 2.5

# ADC settings
DEFAULT_READING_COUNT = 10
DEFAULT_READING_INTERVAL_US = 100

# EC800X ADC reference: 0-1.3V, 12-bit (0-4095)
# Check your module's actual VREF — some are 0-3.3V
EC800X_ADC_VREF = 1.3
EC800X_ADC_RESOLUTION = 4096.0


class PH4502C:
    """PH4502C analog pH sensor driver for QuecPython EC800X."""

    def __init__(self, adc_channel, divider_ratio=1.0,
                 vref=EC800X_ADC_VREF,
                 adc_resolution=EC800X_ADC_RESOLUTION,
                 calibration=DEFAULT_CALIBRATION,
                 ph_step=DEFAULT_PH_STEP,
                 mid_voltage=DEFAULT_MID_VOLTAGE):
        """
        Args:
            adc_channel: ADC channel (e.g., ADC.ADC0, ADC.ADC1).
            divider_ratio: Voltage divider ratio V_adc/V_actual.
                           E.g., R1=33K, R2=10K → ratio = 10/43 = 0.233
                           Set to 1.0 if no divider (direct connection, vref>=5V).
            vref: ADC reference voltage (default 1.3V for EC800X).
            adc_resolution: ADC resolution (default 4096 for 12-bit).
            calibration: Y-intercept calibration offset (default 14.8).
            ph_step: Volts per pH unit (default 0.18).
            mid_voltage: Voltage at pH 7.0 (default 2.5V).
        """
        self._adc_channel = adc_channel
        self._divider_ratio = divider_ratio
        self._vref = vref
        self._adc_resolution = adc_resolution
        self._calibration = calibration
        self._ph_step = ph_step
        self._mid_voltage = mid_voltage
        self._adc = None
        self._reading_count = DEFAULT_READING_COUNT
        self._reading_interval = DEFAULT_READING_INTERVAL_US

    def init(self):
        """Initialize ADC. Returns True on success."""
        try:
            self._adc = ADC()
            self._adc.open()
            return True
        except Exception as e:
            print("PH4502C: ADC init failed -", e)
            return False

    def deinit(self):
        """Close ADC."""
        if self._adc:
            self._adc.close()
            self._adc = None

    def _read_adc_raw(self):
        """Read raw ADC value once. Returns int or None."""
        if not self._adc:
            return None
        try:
            val = self._adc.read(self._adc_channel)
            return val
        except Exception:
            return None

    def _read_voltage(self):
        """Read averaged ADC voltage (actual, after divider compensation).

        Takes multiple readings, averages them, converts to actual voltage.

        Returns:
            Float voltage at the Po pin, or None on failure.
        """
        total = 0
        count = 0
        for _ in range(self._reading_count):
            raw = self._read_adc_raw()
            if raw is not None:
                total += raw
                count += 1
            utime.sleep_us(self._reading_interval)

        if count == 0:
            return None

        avg_raw = total / count

        # ADC raw → voltage at ADC pin
        v_adc = avg_raw * (self._vref / self._adc_resolution)

        # Compensate for voltage divider
        if self._divider_ratio > 0:
            v_actual = v_adc / self._divider_ratio
        else:
            v_actual = v_adc

        return v_actual

    def read_ph(self):
        """Read pH value.

        Returns:
            Float pH value (0-14), or None on failure.
        """
        voltage = self._read_voltage()
        if voltage is None:
            return None

        # Clamp voltage to reasonable range
        if voltage < 0:
            voltage = 0

        ph = self._calibration + (self._mid_voltage - voltage) / self._ph_step

        # Clamp to 0-14
        if ph < 0:
            ph = 0.0
        elif ph > 14:
            ph = 14.0

        return ph

    def read_ph_voltage(self):
        """Read raw voltage at the Po pin.

        Returns:
            Float voltage, or None on failure.
        """
        return self._read_voltage()

    def calibrate(self, known_ph, measured_voltage=None):
        """Adjust calibration offset for a known pH value.

        Call this after placing the probe in a buffer solution of known pH.
        If measured_voltage is None, a new reading is taken automatically.

        Args:
            known_ph: The known pH value of the buffer solution.
            measured_voltage: The voltage reading at that pH (None to auto-read).
        """
        if measured_voltage is None:
            measured_voltage = self._read_voltage()
            if measured_voltage is None:
                print("PH4502C: calibration failed — cannot read voltage")
                return False

        # Rearranged formula: calibration = known_ph - (V_mid - V) / ph_step
        self._calibration = known_ph - (self._mid_voltage - measured_voltage) / self._ph_step
        return True

    def calibrate_two_point(self, ph1, v1, ph2, v2):
        """Two-point calibration: adjust both ph_step and calibration.

        Args:
            ph1, v1: Known pH and measured voltage for calibration point 1.
            ph2, v2: Known pH and measured voltage for calibration point 2.
        """
        if abs(v1 - v2) < 0.001:
            print("PH4502C: two-point calibration failed — voltages too close")
            return False

        # slope (V/pH) from two points
        self._ph_step = (v1 - v2) / (ph1 - ph2)
        # y-intercept
        self._calibration = ph1 - (self._mid_voltage - v1) / self._ph_step
        return True

    @property
    def calibration(self):
        """Current calibration offset."""
        return self._calibration

    @calibration.setter
    def calibration(self, value):
        self._calibration = value

    @property
    def ph_step(self):
        """Current pH step (V/pH)."""
        return self._ph_step

    @ph_step.setter
    def ph_step(self, value):
        self._ph_step = value


def demo():
    """Demo: read pH every 3 seconds."""
    sensor = PH4502C(
        adc_channel=ADC.ADC0,
        divider_ratio=0.233,  # R1=33K, R2=10K
    )

    if not sensor.init():
        print("PH4502C: initialization failed")
        return

    print("PH4502C: initialized, reading pH...")

    while True:
        try:
            ph = sensor.read_ph()
            voltage = sensor.read_ph_voltage()
            if ph is not None:
                print("PH4502C: pH=%.2f (voltage=%.3fV)" % (ph, voltage or 0))
            else:
                print("PH4502C: read failed")
        except Exception as e:
            print("PH4502C: error -", e)

        utime.sleep(3)


if __name__ == "__main__":
    demo()
