"""
Water Valve Control for QuecPython (EC800X).
Controls an electromagnetic valve via GPIO + relay/MOSFET.

Wiring:
  GPIO pin -> Relay module IN (or MOSFET gate)
  Relay COM -> Valve power supply
  Relay NO  -> Valve positive terminal
  Valve negative -> Power supply GND

The relay module is typically active-LOW (set GPIO LOW to open valve).
Adjust active_low parameter to match your relay module.
"""

from machine import Pin


class WaterValve:
    """Electromagnetic water valve controller (ON/OFF)."""

    def __init__(self, gpio_pin, active_low=True):
        """
        Args:
            gpio_pin: GPIO pin number connected to relay/MOSFET.
            active_low: True if relay activates on LOW (most common relay modules).
                        False if relay activates on HIGH.
        """
        self._active_low = active_low
        self._pin = Pin(gpio_pin, Pin.OUT)
        # Start with valve closed
        self._pin.value(1 if active_low else 0)
        self._is_open = False

    def open(self):
        """Open the valve (turn on water flow)."""
        self._pin.value(0 if self._active_low else 1)
        self._is_open = True

    def close(self):
        """Close the valve (turn off water flow)."""
        self._pin.value(1 if self._active_low else 0)
        self._is_open = False

    @property
    def is_open(self):
        """True if valve is currently open."""
        return self._is_open

    def toggle(self):
        """Toggle valve state."""
        if self._is_open:
            self.close()
        else:
            self.open()
