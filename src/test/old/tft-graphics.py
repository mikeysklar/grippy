import board, busio, displayio, digitalio
import framebufferio
import rgbmatrix        # ignore this, leftover — wait

from adafruit_st7789 import ST7789
from adafruit_display_text import label
import terminalio
from adafruit_display_shapes.rect import Rect
import time

displayio.release_displays()

# backlight
bl = digitalio.DigitalInOut(board.IO13)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# spi
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)

# st7789 bus directly
display_bus = displayio.FourWire(   # <-- check if FourWire is in displayio
    spi,
    command=board.IO11,
    chip_select=board.IO12,
    reset=board.IO10,
    baudrate=24000000
)

display = ST7789(
    display_bus,
    width=240,
    height=280,
    rotation=270,
    colstart=20,
    rowstart=0
)

# --- Scene: color bars + checker + text ---
root = displayio.Group()
display.root_group = root

# color bars
bar_colors = [0xFF0000, 0xFF7F00, 0xFFFF00, 0x00FF00, 0x0000FF, 0x4B0082, 0x9400D3]
bar_w = max(1, display.width // len(bar_colors))
for i, c in enumerate(bar_colors):
    root.append(Rect(i * bar_w, 0, bar_w, display.height, fill=c))

# checker tile
tile = displayio.Bitmap(8, 8, 2)
pal = displayio.Palette(2)
pal[0] = 0x000000
pal[1] = 0xFFFFFF
for y in range(8):
    for x in range(8):
        tile[x, y] = (x + y) & 1
for y in range(0, display.height, 16):
    for x in range(0, display.width, 16):
        g = displayio.Group(x=x, y=y)
        g.append(displayio.TileGrid(tile, pixel_shader=pal))
        root.append(g)

# centered text
txt = label.Label(terminalio.FONT, text="ST7789 240x280 OK", color=0x000000)
txt.anchor_point = (0.5, 0.5)
txt.anchored_position = (display.width // 2, display.height // 2)
root.append(txt)

# blink BL to prove control
for _ in range(2):
    bl.value = False
    time.sleep(0.15)
    bl.value = True
    time.sleep(0.15)

while True:
    time.sleep(1)
