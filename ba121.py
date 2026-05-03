"""
BA121 Conductivity & Temperature Sensor Driver for QuecPython (EC800X).
Based on AtomBit BA121 datasheet V1.0 and libdriver/ba121 protocol.

Communication: UART 9600 bps, 8N1
Frame format: Command(1B) + Data(4B) + Checksum(1B) = 6 bytes
Checksum: sum of first 5 bytes, masked to 0xFF

SOP8 Pin connections:
  Pin 1 (VDD)       - 3.3V supply (ripple < 20mV)
  Pin 2 (DDL1-ACT1) - Probe drive signal, connect to probe 1
  Pin 3 (DDL1-ACT2) - Probe drive signal, via 1% resistor to probe 2
  Pin 4 (UART-RXD)  - Connect to MCU TX pin
  Pin 5 (UART-TXD)  - Connect to MCU RX pin
  Pin 6 (DDL1-AD)   - Analog input, connect to probe 2
  Pin 7 (DDL1-NTC)  - Analog input, temperature signal
  Pin 8 (GND)       - Ground

Wiring for EC800X:
  BA121 Pin 4 (RXD) -> EC800X UART TX
  BA121 Pin 5 (TXD) -> EC800X UART RX
  BA121 Pin 1 (VDD) -> 3.3V
  BA121 Pin 8 (GND) -> GND

Measurement range:
  Conductivity: 0-6000 uS/cm, error < 2% F.S.
  Temperature:  0-100 degC, +/- 0.5 degC
"""

import utime
from machine import UART

# Command bytes
CMD_READ = 0xA0
CMD_BASELINE_CALIBRATION = 0xA6
CMD_SET_NTC_RESISTANCE = 0xA3
CMD_SET_NTC_B_VALUE = 0xA5

# Response headers
HEADER_DATA = 0xAA
HEADER_STATUS = 0xAC

# Status codes
STATUS_OK = 0x00
STATUS_FRAME_ERROR = 0x01
STATUS_BUSY = 0x02
STATUS_CALIBRATION_FAILED = 0x03
STATUS_TEMPERATURE_OUT_OF_RANGE = 0x04

# Timing
READ_DELAY_MS = 800
CMD_DELAY_MS = 500
RX_TIMEOUT_MS = 1000

# Default NTC parameters
DEFAULT_NTC_RESISTANCE = 10000  # 10K ohm
DEFAULT_NTC_B_VALUE = 3435

# Frame size
FRAME_SIZE = 6


def _make_frame(command, data=0):
    """Build a 6-byte frame: command(1) + data(4, big-endian) + checksum(1)."""
    buf = bytearray(FRAME_SIZE)
    buf[0] = command
    buf[1] = (data >> 24) & 0xFF
    buf[2] = (data >> 16) & 0xFF
    buf[3] = (data >> 8) & 0xFF
    buf[4] = data & 0xFF
    buf[5] = sum(buf[0:5]) & 0xFF
    return buf


def _parse_response(buf, expect_data=True):
    """Parse a 6-byte response frame.

    Args:
        buf: 6-byte bytearray received from the sensor.
        expect_data: True if expecting a data response (0xAA header),
                     False if expecting a status response (0xAC header).

    Returns:
        Tuple (success: bool, data: int, status_code: int).
        For data responses, data contains conductivity/temp packed value.
        For status responses, data contains the status detail.
    """
    if len(buf) != FRAME_SIZE:
        return False, 0, STATUS_FRAME_ERROR

    # Verify checksum
    if sum(buf[0:5]) & 0xFF != buf[5]:
        return False, 0, STATUS_FRAME_ERROR

    # Verify header
    expected_header = HEADER_DATA if expect_data else HEADER_STATUS
    if buf[0] != expected_header:
        return False, 0, STATUS_FRAME_ERROR

    # Extract 4-byte data payload (big-endian)
    data = (buf[1] << 24) | (buf[2] << 16) | (buf[3] << 8) | buf[4]
    return True, data, STATUS_OK


class BA121:
    """BA121 conductivity and temperature sensor driver.

    Usage:
        sensor = BA121(UART.UART1, UART_TXD, UART_RXD)
        sensor.init()
        conductivity, temperature = sensor.read()
        print("Conductivity: %.1f uS/cm, Temperature: %.1f C" %
              (conductivity, temperature))
    """

    def __init__(self, uart_port, tx_pin, rx_pin):
        """Initialize BA121 driver.

        Args:
            uart_port: UART port number (e.g., UART.UART0, UART.UART1).
            tx_pin: TX pin number for MCU (connects to BA121 pin 4 RXD).
            rx_pin: RX pin number for MCU (connects to BA121 pin 5 TXD).
        """
        self._uart_port = uart_port
        self._tx_pin = tx_pin
        self._rx_pin = rx_pin
        self._uart = None
        self._last_status = STATUS_OK

    def init(self):
        """Initialize UART communication with BA121.

        Returns:
            True on success, False on failure.
        """
        try:
            self._uart = UART(self._uart_port, 9600, 8, 0, 1, self._tx_pin,
                              self._rx_pin, 0)
            return True
        except Exception as e:
            print("BA121: UART init failed -", e)
            return False

    def deinit(self):
        """Deinitialize UART."""
        if self._uart:
            self._uart.close()
            self._uart = None

    def _uart_flush(self):
        """Flush any pending data in the UART RX buffer."""
        if self._uart:
            while self._uart.any():
                self._uart.read(self._uart.any())

    def _uart_write(self, data):
        """Write data to UART."""
        if self._uart:
            self._uart.write(data)

    def _uart_read(self, length, timeout_ms=RX_TIMEOUT_MS):
        """Read exactly `length` bytes from UART with timeout.

        Returns:
            bytearray of received data, or None on timeout.
        """
        if not self._uart:
            return None
        buf = bytearray(length)
        received = 0
        deadline = utime.ticks_ms() + timeout_ms
        while received < length:
            remaining = utime.ticks_diff(deadline, utime.ticks_ms())
            if remaining <= 0:
                break
            chunk = self._uart.read(length - received)
            if chunk:
                n = len(chunk)
                buf[received:received + n] = chunk
                received += n
            else:
                utime.sleep_ms(10)
        if received < length:
            return None
        return buf

    def _send_and_receive(self, command, data=0, delay_ms=READ_DELAY_MS,
                          expect_data=True):
        """Send a command frame and wait for the response.

        Args:
            command: Command byte (e.g., CMD_READ).
            data: 4-byte data payload (big-endian).
            delay_ms: Milliseconds to wait before reading response.
            expect_data: True for data response (0xAA), False for status (0xAC).

        Returns:
            Tuple (success: bool, data: int).
        """
        self._uart_flush()

        frame = _make_frame(command, data)
        self._uart_write(frame)

        utime.sleep_ms(delay_ms)

        response = self._uart_read(FRAME_SIZE)
        if response is None:
            self._last_status = STATUS_FRAME_ERROR
            return False, 0

        success, resp_data, status = _parse_response(response, expect_data)
        self._last_status = status
        return success, resp_data

    def read(self):
        """Read conductivity and temperature from the sensor.

        Sends the read command (0xA0) and waits 800ms for the response.

        Returns:
            Tuple (conductivity_uS_cm: float, temperature_degC: float),
            or (None, None) on failure.

        Example response: AA 00 64 0A 96 40
            conductivity_raw = 0x0064 = 100 -> 100 uS/cm
            temperature_raw  = 0x0A96 = 2710 -> 27.10 degC
        """
        success, data = self._send_and_receive(CMD_READ, 0, READ_DELAY_MS,
                                               expect_data=True)
        if not success:
            return None, None

        # Upper 16 bits: conductivity value in uS/cm
        conductivity_raw = (data >> 16) & 0xFFFF
        conductivity = float(conductivity_raw)

        # Lower 16 bits: temperature raw, divide by 100 for degC
        temperature_raw = data & 0xFFFF
        temperature = temperature_raw / 100.0

        return conductivity, temperature

    def baseline_calibration(self):
        """Perform baseline calibration.

        IMPORTANT: The probe must be placed in pure water at 25 +/- 5 degC
        before calling this function.

        Returns:
            True on success, False on failure.
        """
        success, data = self._send_and_receive(CMD_BASELINE_CALIBRATION, 0,
                                               CMD_DELAY_MS, expect_data=False)
        if success:
            # Status byte is in bits 24-31 of data
            status = (data >> 24) & 0xFF
            self._last_status = status
            return status == STATUS_OK
        return False

    def set_ntc_resistance(self, ohms):
        """Set NTC thermistor nominal resistance at 25 degC.

        Args:
            ohms: NTC resistance in ohms (e.g., 10000 for 10K).

        Returns:
            True on success, False on failure.
        """
        if ohms < 0 or ohms > 0xFFFFFFFF:
            raise ValueError("NTC resistance out of range")
        success, data = self._send_and_receive(CMD_SET_NTC_RESISTANCE, ohms,
                                               CMD_DELAY_MS, expect_data=False)
        if success:
            status = (data >> 24) & 0xFF
            self._last_status = status
            return status == STATUS_OK
        return False

    def set_ntc_b_value(self, b_value):
        """Set NTC thermistor B-value.

        Args:
            b_value: NTC B-value (e.g., 3435). Only lower 16 bits are sent.

        Returns:
            True on success, False on failure.
        """
        if b_value < 0 or b_value > 0xFFFF:
            raise ValueError("NTC B-value out of range (0-65535)")
        # B-value is encoded in the upper 16 bits of the data field
        encoded = b_value << 16
        success, data = self._send_and_receive(CMD_SET_NTC_B_VALUE, encoded,
                                               CMD_DELAY_MS, expect_data=False)
        if success:
            status = (data >> 24) & 0xFF
            self._last_status = status
            return status == STATUS_OK
        return False

    @property
    def last_status(self):
        """Return the status code from the last command.

        Status codes:
            0x00 - OK
            0x01 - Frame error
            0x02 - Busy
            0x03 - Calibration failed
            0x04 - Temperature out of range
        """
        return self._last_status

    def status_string(self, code=None):
        """Return a human-readable status string.

        Args:
            code: Status code (defaults to last_status if None).
        """
        if code is None:
            code = self._last_status
        status_names = {
            STATUS_OK: "OK",
            STATUS_FRAME_ERROR: "Frame error",
            STATUS_BUSY: "Busy",
            STATUS_CALIBRATION_FAILED: "Calibration failed",
            STATUS_TEMPERATURE_OUT_OF_RANGE: "Temperature out of range",
        }
        return status_names.get(code, "Unknown (0x%02X)" % code)


def demo():
    """Demo: read conductivity and temperature every 3 seconds."""
    from machine import UART

    # Adjust UART port and pins to your hardware setup
    sensor = BA121(UART.UART1, 0, 0)  # TX pin, RX pin -- set to your pins

    if not sensor.init():
        print("BA121: initialization failed")
        return

    print("BA121: initialized, reading sensor...")

    # Optionally configure NTC parameters (defaults: 10K ohm, B=3435)
    # sensor.set_ntc_resistance(10000)
    # sensor.set_ntc_b_value(3435)

    while True:
        try:
            conductivity, temperature = sensor.read()
            if conductivity is not None:
                print("BA121: conductivity=%.1f uS/cm, temperature=%.2f C" %
                      (conductivity, temperature))
            else:
                print("BA121: read failed, status=%s" %
                      sensor.status_string())
        except Exception as e:
            print("BA121: error -", e)

        utime.sleep(3)


if __name__ == "__main__":
    demo()
