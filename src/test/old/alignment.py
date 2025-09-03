import board, busio, displayio
from fourwire import FourWire
from adafruit_st7789 import ST7789
import digitalio

displayio.release_displays()

# SPI on your chosen pins
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)

tft_cs  = board.IO12
tft_dc  = board.IO11
tft_rst = board.IO10
tft_blk = board.IO13  # backlight control

# Backlight HIGH = on
bl = digitalio.DigitalInOut(tft_blk)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

bus = FourWire(
    spi,
    command=tft_dc,
    chip_select=tft_cs,
    reset=tft_rst,
    baudrate=24_000_000  # you can push to 32_000_000 later if wiring is short/clean
)

# ST7789v3 (240x280) — common offset for rotation=270
display = ST7789(
    bus,
    width=240,
    height=280,
    rotation=270,
    colstart=0,   # <<< primary fix for left-edge noise
    rowstart=20
)
