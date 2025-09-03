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

# Enable backlight (HIGH = on)
bl = digitalio.DigitalInOut(tft_blk)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

bus = FourWire(spi, command=tft_dc, chip_select=tft_cs, reset=tft_rst)

display = ST7789(bus, width=240, height=280, rotation=270)
