# st7789_280x240_simpletest.py
# ESP32-S3 SuperMini / Waveshare ESP32-S3-Zero
# Wiring: SCK=IO8, MOSI=IO9, CS=IO12, DC=IO11, RST=IO10, BLK=IO13

import time
import board, busio, displayio, digitalio
from fourwire import FourWire
from adafruit_st7789 import ST7789
from adafruit_display_text import label
import terminalio

displayio.release_displays()

# Backlight (optional, tie high if not used)
bl = digitalio.DigitalInOut(board.IO13)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True  # on

# SPI bus (your pins)
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)

# 4-wire display bus (DC, CS, RST per your pins)
display_bus = FourWire(
    spi,
    command=board.IO11,     # D/C
    chip_select=board.IO12, # CS
    reset=board.IO10,       # RST
    baudrate=32_000_000
)

# 280x240 ST7789: Adafruit example uses rotation=270, rowstart=20, colstart=0
display = ST7789(
    display_bus,
    width=280,
    height=240,
    rotation=270,
    rowstart=20,
    colstart=0
)

# Simple scene (solid color + centered text), like the example style
root = displayio.Group()
display.root_group = root

# Solid background (teal)
bg = displayio.Bitmap(display.width, display.height, 1)
pal = displayio.Palette(1)
pal[0] = 0x008080
root.append(displayio.TileGrid(bg, pixel_shader=pal))

# Centered label
txt = label.Label(terminalio.FONT, text="ST7789 280x240", color=0xFFFFFF)
txt.anchor_point = (0.5, 0.5)
txt.anchored_position = (display.width // 2, display.height // 2)
root.append(txt)

# Idle
while True:
    time.sleep(1)
