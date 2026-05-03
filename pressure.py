"""
Water Pressure Sensor Driver for QuecPython (EC800X).
Reads pressure via ADC from common analog pressure transducers.

Typical pressure sensor specs (e.g., XDB401, USP10, 0.5-4.5V output):
  Output voltage: 0.5V (0 pressure) to 4.5V (max rated pressure)
  Supply: 5V DC

Wiring:
  Sensor VCC -> 5V
  Sensor GND -> GND
  Sensor Signal -> ADC input (via voltage divider if needed)

IMPORTANT: If sensor outputs 0-5V and EC800X ADC accepts max 1.3V,
use a voltage divider. Same as PH4502C setup.

Pressure formula:
  V_out = V_min + (V_max - V_min) * (pressure / max_pressure)
  pressure = (V_actual - V_min) / (V_max - V_min) * max_pressure
"""

from machine import ADC
import utime

# EC800X ADC defaults
EC800X_ADC_VREF = 1.3
EC800X_ADC_RESOLUTION = 4096.0

# Default averaging
DEFAULT_READING_COUNT = 10
DEFAULT_READING_INTERVAL_US = 100


class PressureSensor:
    """Analog water pressure sensor driver for QuecPython EC800X."""

    def __init__(self, adc_channel, max_pressure=1.2,
                 v_min=0.5, v_max=4.5,
                 divider_ratio=1.0,
                 vref=EC800X_ADC_VREF,
                 adc_resolution=EC800X_ADC_RESOLUTION,
                 unit="MPa"):
        """
        Args:
            adc_channel: ADC channel (e.g., ADC.ADC0, ADC.ADC1).
            max_pressure: Maximum rated pressure of the sensor.
                          Common values: 0.8, 1.2, 2.0 MPa.
            v_min: Output voltage at 0 pressure (default 0.5V).
            v_max: Output voltage at max pressure (default 4.5V).
            divider_ratio: Voltage divider ratio V_adc/V_actual.
                           R1=33K, R2=10K → ratio = 10/43 ≈ 0.233
            vref: ADC reference voltage (default 1.3V for EC800X).
            adc_resolution: ADC resolution (default 4096 for 12-bit).
            unit: Pressure unit string (default "MPa").
        """
        self._adc_channel = adc_channel
        self._max_pressure = max_pressure
        self._v_min = v_min
        self._v_max = v_max
        self._divider_ratio = divider_ratio
        self._vref = vref
        self._adc_resolution = adc_resolution
        self._unit = unit
        self._adc = None

    def init(self):
        """Initialize ADC. Returns True on success."""
        try:
            self._adc = ADC()
            self._adc.open()
            return True
        except Exception as e:
            print("PressureSensor: ADC init failed -", e)
            return False

    def deinit(self):
        """Close ADC."""
        if self._adc:
            self._adc.close()
            self._adc = None

    def _read_voltage(self):
        """Read averaged voltage (actual, after divider compensation).

        Returns:
            Float voltage at sensor output, or None on failure.
        """
        if not self._adc:
            return None

        total = 0
        count = 0
        for _ in range(DEFAULT_READING_COUNT):
            try:
                raw = self._adc.read(self._adc_channel)
                total += raw
                count += 1
            except Exception:
                pass
            utime.sleep_us(DEFAULT_READING_INTERVAL_US)

        if count == 0:
            return None

        avg_raw = total / count
        v_adc = avg_raw * (self._vref / self._adc_resolution)

        if self._divider_ratio > 0:
            return v_adc / self._divider_ratio
        return v_adc

    def read_pressure(self):
        """Read water pressure.

        Returns:
            Tuple (pressure: float, voltage: float) or (None, None) on failure.
        """
        voltage = self._read_voltage()
        if voltage is None:
            return None, None

        v_range = self._v_max - self._v_min
        if v_range <= 0:
            return None, voltage

        pressure = (voltage - self._v_min) / v_range * self._max_pressure

        if pressure < 0:
            pressure = 0.0

        return pressure, voltage

    @property
    def max_pressure(self):
        """Maximum rated pressure."""
        return self._max_pressure

    @property
    def unit(self):
        """Pressure unit string."""
        return self._unit


def demo():
    """Demo: read pressure every 2 seconds."""
    sensor = PressureSensor(
        adc_channel=ADC.ADC1,
        max_pressure=1.2,
        divider_ratio=0.233,
    )

    if not sensor.init():
        print("PressureSensor: initialization failed")
        return

    print("PressureSensor: initialized, max=%.1f %s" %
          (sensor.max_pressure, sensor.unit))

    while True:
        try:
            pressure, voltage = sensor.read_pressure()
            if pressure is not None:
                print("Pressure: %.3f %s (%.3fV)" %
                      (pressure, sensor.unit, voltage))
            else:
                print("Pressure: read failed")
        except Exception as e:
            print("Pressure: error -", e)

        utime.sleep(2)


if __name__ == "__main__":
    demo()
