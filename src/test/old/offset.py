# ST7789v3 (240x280) test with correct offset
# ESP32-S3 SuperMini / Waveshare ESP32-S3-Zero
# Wiring: SCK=IO8, MOSI=IO9, CS=IO12, DC=IO11, RST=IO10, BLK=IO13

import time
import board, busio, displayio, digitalio
from fourwire import FourWire
from adafruit_st7789 import ST7789
from adafruit_display_text import label
from adafruit_display_shapes.rect import Rect
import terminalio

displayio.release_displays()

# Backlight (GPIO13)
bl = digitalio.DigitalInOut(board.IO13)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# SPI bus (GPIO8 = SCK, GPIO9 = MOSI)
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)

# 4-wire display bus
bus = FourWire(
    spi,
    command=board.IO11,      # D/C
    chip_select=board.IO12,  # CS
    reset=board.IO10,        # RST
    baudrate=24_000_000
)

# ST7789v3: need to skip 40 rows (240x320 RAM -> 240x280 glass)
display = ST7789(
    bus,
    width=240,
    height=280,
    rotation=270,      # portrait (USB at bottom, in your setup)
    colstart=0,
    rowstart=40        # <<< key fix
)

# --- Scene: color bars + centered text
root = displayio.Group()
display.root_group = root

colors = [0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00, 0xFF00FF, 0x00FFFF]
stripe_h = max(1, display.height // len(colors))
for i, c in enumerate(colors):
    root.append(Rect(0, i * stripe_h, display.width, stripe_h, fill=c))

txt = label.Label(terminalio.FONT, text="rowstart=40 • rotation=270", color=0x000000)
txt.anchor_point = (0.5, 0.5)
txt.anchored_position = (display.width // 2, display.height // 2)
root.append(txt)

# quick backlight blink to prove control
for _ in range(2):
    bl.value = False; time.sleep(0.15)
    bl.value = True;  time.sleep(0.15)

while True:
    time.sleep(1)
