"""
Peristaltic Pump Driver for QuecPython (EC800X).
Controls direction via GPIO, speed via PWM.

Wiring:
  DIR pin  -> Motor driver DIR (e.g., TB6612, L298N)
  PWM pin  -> Motor driver PWM (speed control)
  Motor driver OUT -> Peristaltic pump motor

Two common motor driver setups:
  1. TB6612FNG: DIR=IN1/IN2, PWM=PWM pin
  2. L298N: DIR=IN1/IN2, PWM=ENA/ENB pin
"""

from machine import Pin
from misc import PWM_V2


class PeristalticPump:
    """Peristaltic pump with direction (GPIO) and speed (PWM) control."""

    FORWARD = "forward"
    REVERSE = "reverse"

    def __init__(self, dir_gpio, pwm_channel, freq=1000.0, name="Pump"):
        """
        Args:
            dir_gpio: GPIO pin number for direction control.
            pwm_channel: PWM channel (e.g., PWM_V2.PWM0, PWM_V2.PWM1).
            freq: PWM frequency in Hz (default 1000).
            name: Pump name for logging.
        """
        self._name = name
        self._freq = freq
        self._speed = 0
        self._direction = self.FORWARD
        self._is_running = False

        self._dir_pin = Pin(dir_gpio, Pin.OUT)
        self._dir_pin.value(0)

        self._pwm = PWM_V2(pwm_channel, freq, 0)

    def init(self):
        """Initialize and start PWM. Returns True on success."""
        try:
            self._pwm.open()
            return True
        except Exception as e:
            print("%s: PWM init failed -" % self._name, e)
            return False

    def start(self, speed=100, direction=None):
        """Start the pump.

        Args:
            speed: Speed percentage 0-100 (default 100).
            direction: 'forward' or 'reverse' (default: keep current).
        """
        if direction is not None:
            self.set_direction(direction)
        self.set_speed(speed)
        self._is_running = True

    def stop(self):
        """Stop the pump."""
        self._pwm.set_duty(0)
        self._speed = 0
        self._is_running = False

    def set_speed(self, speed):
        """Set pump speed.

        Args:
            speed: Percentage 0-100.
        """
        speed = max(0, min(100, int(speed)))
        self._speed = speed
        self._pwm.set_duty(speed)

    def set_direction(self, direction):
        """Set pump direction.

        Args:
            direction: 'forward' or 'reverse'.
        """
        self._direction = direction
        self._dir_pin.value(0 if direction == self.FORWARD else 1)

    def deinit(self):
        """Stop and close PWM."""
        self.stop()
        try:
            self._pwm.close()
        except Exception:
            pass

    @property
    def is_running(self):
        """True if pump is currently running."""
        return self._is_running

    @property
    def speed(self):
        """Current speed percentage (0-100)."""
        return self._speed

    @property
    def direction(self):
        """Current direction string."""
        return self._direction

    @property
    def name(self):
        """Pump name."""
        return self._name

    def status(self):
        """Return status string for logging."""
        if not self._is_running:
            return "%s: STOPPED" % self._name
        return "%s: %s @ %d%%" % (self._name, self._direction, self._speed)
