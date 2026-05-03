"""
Relay Control for QuecPython (EC800X).
Generic ON/OFF relay control via GPIO.

Wiring:
  GPIO pin -> Relay module IN
  Relay COM -> Load power supply
  Relay NO  -> Load positive terminal
  Load negative -> Power supply GND

Most relay modules are active-LOW (GPIO LOW = relay ON).
"""

from machine import Pin


class Relay:
    """Generic relay controller (ON/OFF)."""

    def __init__(self, gpio_pin, active_low=True, name="Relay"):
        """
        Args:
            gpio_pin: GPIO pin number connected to relay module.
            active_low: True if relay activates on LOW (most common).
            name: Device name for logging.
        """
        self._name = name
        self._active_low = active_low
        self._pin = Pin(gpio_pin, Pin.OUT)
        self._pin.value(1 if active_low else 0)
        self._is_on = False

    def on(self):
        """Turn relay ON (activate)."""
        self._pin.value(0 if self._active_low else 1)
        self._is_on = True

    def off(self):
        """Turn relay OFF (deactivate)."""
        self._pin.value(1 if self._active_low else 0)
        self._is_on = False

    def toggle(self):
        """Toggle relay state."""
        if self._is_on:
            self.off()
        else:
            self.on()

    @property
    def is_on(self):
        """True if relay is currently active."""
        return self._is_on

    @property
    def name(self):
        """Device name."""
        return self._name

    def status(self):
        """Return status string for logging."""
        return "%s: %s" % (self._name, "ON" if self._is_on else "OFF")
