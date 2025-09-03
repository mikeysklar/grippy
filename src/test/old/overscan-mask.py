# ST7789v3 (240x280) with safe-area masking
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

# --- backlight ---
bl = digitalio.DigitalInOut(board.IO13)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# --- SPI bus ---
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)

# --- 4-wire bus ---
bus = FourWire(
    spi,
    command=board.IO11,
    chip_select=board.IO12,
    reset=board.IO10,
    baudrate=24_000_000
)

# --- display ---
display = ST7789(
    bus,
    width=240,
    height=280,
    rotation=270,
    colstart=0,
    rowstart=40     # your panel’s correct offset
)

# --- safe-area masking ---
MARGIN_L = 0
MARGIN_R = 0
INNER_W  = display.width - (MARGIN_L + MARGIN_R)
INNER_H  = display.height

root = displayio.Group()
display.root_group = root

# paint whole background black (covers edges)
bg = displayio.Bitmap(display.width, display.height, 1)
pal = displayio.Palette(1)
pal[0] = 0x000000
root.append(displayio.TileGrid(bg, pixel_shader=pal))

# all content goes into a translated group
content = displayio.Group(x=MARGIN_L, y=0)
root.append(content)

# --- demo scene inside the safe area ---
colors = [0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00, 0xFF00FF, 0x00FFFF]
stripe_h = max(1, INNER_H // len(colors))
for i, c in enumerate(colors):
    content.append(Rect(0, i * stripe_h, INNER_W, stripe_h, fill=c))

txt = label.Label(terminalio.FONT, text="Safe Area", color=0x000000)
txt.anchor_point = (0.5, 0.5)
txt.anchored_position = (INNER_W // 2, INNER_H // 2)
content.append(txt)

# --- blink BL to prove control ---
for _ in range(2):
    bl.value = False; time.sleep(0.15)
    bl.value = True;  time.sleep(0.15)

while True:
    time.sleep(1)
