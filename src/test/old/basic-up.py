# Minimal ST7789v3 (240x280) init
# ESP32-S3 SuperMini / Waveshare ESP32-S3-Zero
# Wiring: SCK=IO8, MOSI=IO9, CS=IO12, DC=IO11, RST=IO10, BLK=IO13

import time
import board, busio, displayio, digitalio
from fourwire import FourWire
from adafruit_st7789 import ST7789

displayio.release_displays()

# Backlight on (IO13)
bl = digitalio.DigitalInOut(board.IO13)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# SPI (IO8 = SCK, IO9 = MOSI)
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)

# 4-wire bus
bus = FourWire(
    spi,
    command=board.IO11,      # D/C
    chip_select=board.IO12,  # CS
    reset=board.IO10,        # RST
    baudrate=24_000_000      # adjust if wiring is long/noisy
)

# Display (rotation=270; this panel wants 40 skipped rows)
display = ST7789(
    bus,
    width=280,
    height=240,
    rotation=270,
    colstart=20,
    rowstart=0
)

# do nothing; leave display initialized
while True:
    time.sleep(1)
