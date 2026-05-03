"""
Water Flow Sensor Driver for QuecPython (EC800X).
Hall effect flow meter — counts pulses via GPIO interrupt.

Calibration: 4980 pulses = 1 liter
Flow rate = (pulses per second) / 4980 * 60 = liters per minute

Wiring:
  Sensor VCC (Red)   -> 5V
  Sensor GND (Black)  -> GND
  Sensor Signal (Yellow) -> GPIO pin (pull-up enabled)

Common flow meters: YF-S201, YF-S402, OF10ZAT
The pulse rate varies by model — adjust PULSES_PER_LITER if needed.
"""

from machine import Pin
import utime

PULSES_PER_LITER = 4980


class FlowSensor:
    """Hall effect water flow sensor driver using GPIO interrupt."""

    def __init__(self, gpio_pin, pulses_per_liter=PULSES_PER_LITER):
        """
        Args:
            gpio_pin: GPIO pin number connected to sensor signal wire.
            pulses_per_liter: Pulse count per liter (default 4980).
        """
        self._pulses_per_liter = pulses_per_liter
        self._pulse_count = 0
        self._last_time = 0
        self._last_rate_lpm = 0.0
        self._total_liters = 0.0

        self._pin = Pin(gpio_pin, Pin.IN, Pin.PULL_UP)
        self._pin.irq(lambda pin: self._on_pulse(), Pin.IRQ_FALLING)

    def _on_pulse(self):
        """Interrupt handler — called on each falling edge."""
        self._pulse_count += 1

    def read(self):
        """Read current flow rate and accumulate total volume.

        Call this at regular intervals (e.g., every 1 second).

        Returns:
            Tuple (flow_rate_lpm: float, total_liters: float).
            flow_rate_lpm: Liters per minute.
            total_liters: Total volume since startup.
        """
        now = utime.ticks_ms()
        elapsed_ms = utime.ticks_diff(now, self._last_time)
        if elapsed_ms <= 0:
            return self._last_rate_lpm, self._total_liters

        count = self._pulse_count
        self._pulse_count = 0
        self._last_time = now

        elapsed_sec = elapsed_ms / 1000.0

        # Flow rate in liters per minute
        self._last_rate_lpm = (count / self._pulses_per_liter) / (elapsed_sec / 60.0)

        # Accumulate total volume
        self._total_liters += count / self._pulses_per_liter

        return self._last_rate_lpm, self._total_liters

    @property
    def flow_rate(self):
        """Last measured flow rate (liters per minute)."""
        return self._last_rate_lpm

    @property
    def total_liters(self):
        """Total water volume since startup (liters)."""
        return self._total_liters

    def reset_total(self):
        """Reset total volume counter to zero."""
        self._total_liters = 0.0
