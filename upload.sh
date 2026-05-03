#!/bin/bash
# upload.sh — Upload QuecPython files to EC800X QuecDuino
# Usage: ./upload.sh [SERIAL_PORT] [BAUD_RATE]
#
# Methods:
#   1. ampy (adafruit-ampy) — recommended, install with: pip install adafruit-ampy
#   2. mpremote — alternative: pip install mpremote
#   3. QPYcom GUI — manual drag-and-drop
#
# Prerequisites:
#   - EC800X connected via USB (appears as /dev/tty.usbmodem* or /dev/ttyUSB*)
#   - QuecPython firmware already flashed (use QPYcom or qdl)

PORT="${1:-}"
BAUD="${2:-115200}"
FILES="quec_i2c.py as7341.py as7263.py ba121.py ph4502c.py pressure.py valve.py flow.py pump.py relay.py main.py"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Auto-detect serial port if not specified
if [ -z "$PORT" ]; then
    PORT=$(ls /dev/tty.usbmodem* /dev/tty.usbserial* /dev/ttyUSB* 2>/dev/null | head -1)
    if [ -z "$PORT" ]; then
        echo "Error: No serial port found. Connect EC800X and retry."
        echo "Usage: $0 /dev/tty.usbmodemXXXX [BAUD]"
        exit 1
    fi
fi

echo "Using port: $PORT at $BAUD baud"
echo "Files to upload: $FILES"
echo ""

# Try ampy first, fall back to mpremote
if command -v ampy &> /dev/null; then
    echo "Using ampy for upload..."
    for f in $FILES; do
        filepath="$SCRIPT_DIR/$f"
        if [ -f "$filepath" ]; then
            echo "  Uploading $f..."
            ampy -p "$PORT" -b "$BAUD" put "$filepath" "$f"
            if [ $? -eq 0 ]; then
                echo "  OK: $f"
            else
                echo "  FAILED: $f"
            fi
        else
            echo "  SKIP: $f not found"
        fi
    done

elif command -v mpremote &> /dev/null; then
    echo "Using mpremote for upload..."
    for f in $FILES; do
        filepath="$SCRIPT_DIR/$f"
        if [ -f "$filepath" ]; then
            echo "  Uploading $f..."
            mpremote connect "$PORT" cp "$filepath" :"$f"
            if [ $? -eq 0 ]; then
                echo "  OK: $f"
            else
                echo "  FAILED: $f"
            fi
        else
            echo "  SKIP: $f not found"
        fi
    done

else
    echo "Error: Neither ampy nor mpremote found."
    echo "Install one of:"
    echo "  pip install adafruit-ampy"
    echo "  pip install mpremote"
    echo ""
    echo "Alternatively, use QPYcom GUI to upload files manually."
    exit 1
fi

echo ""
echo "Upload complete. Reset module to auto-run main.py"
echo "Or run manually: ampy -p $PORT -b $BAUD run main.py"
