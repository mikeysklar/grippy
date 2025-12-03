# Grippy – Ultracompact One-Handed Keyboard

## Overview

![Grippy Assembled](images/grippy-asm.jpeg)

Started as a one-handed chording keyboard.
Five revs later: a slim, ultralight EDC note-taker.

Grippy also supports USB or BLE keyboard modes.

---

## Features

![FreeCAD](images/freecad-case.png)

- **Slim & Lightweight**
  - About the thickness of a AAA battery  
  - ~7× lighter than an iPhone  

- **One-Handed SAIE Chording**
  - Full text entry: letters, numbers, symbols  
  - Three layers, zero finger travel  

- **EDC Note-Taking**
  - Write and review notes directly on the device  
  - Works even while pocketed  

- **USB Keyboard Mode**
  - USB HID for quick input or macros  

- **BLE Keyboard Mode**
  - Wireless typing to phones and computers  

- **USB Storage Mode**
  - Mounts as a flash drive to edit notes  

- **Open & Hackable**
  - KiCad, STEP, FreeCAD, and 3MF files  
  - CircuitPython 10.x firmware + chording config

---

## Specs

![3D Board](images/kicad-raytrace.png)

| Item        | Value                  |
| ----------- | ---------------------- |
| Dimensions  | 61 x 35 x 11 mm        |
| Weight      | 29 grams               |
| Firmware    | CircuitPython 10.x     |
| Controller  | ESP32-S3               |
| Construction| SMD components on PCB  |

---

## PCB

![PCB Dimensions](images/kicad-dimensions.png)

- KiCAD 9.x
- single sided PCB
- SMT design

---

## Stencil

![PCB Stencil](images/pcb-stencil.jpeg)

- low temp 140C solderpaste
- laser cut metal business card


---

## Schematic

![PCB schematic](images/kicad-sch.png)

---

## CircuitPython Setup

- <a href="https://circuitpython.org/board/espressif_esp32s3_devkitc_1_n8/">Bootloader 0.35.0 or later</a>
- <a href="https://circuitpython.org/board/espressif_esp32s3_devkitc_1_n8/">CircuitPython 10.0.3 or later</a>

```                                                                                                                                          circup install adafruit_st7789 adafruit_display_text adafruit_hid
```

---

## BOM

![Inside](images/no-dissassemble.jpeg)

| Part                                                                                                  | Desc.                | Qty |
| ------------------------------------------------------------------------------------------------------ | -------------------- | --- |
| <a href="https://amzn.to/4idmH0o">ESP32-S3 SuperMini</a> | dual-core 240MHz / 512KB SRAM / 4MB Flash   | 1   |
| <a href="https://amzn.to/484M9jT">1.69” TFT Display</a> | ST7789 SPI           | 1   |
| <a href="https://www.digikey.com/en/products/detail/panasonic-electronic-components/EVQ-PUL02K/286340">Panasonic Tactile Switch</a> | EVQ-PUL02K SPST-NO Side Actuated | 1 |
| <a href=https://amzn.to/48axBAR>Standoff</a> | M2 × 5 mm | 4   |
| <a href=https://amzn.to/44vQJXr>Screws</a>| M2 × 5 mm            | 8   |
| <a href=https://www.aliexpress.us/item/3256804992051151.html>Female SMD Header</a> | 8-pin                | 1   |
| <a href=https://www.aliexpress.us/item/3256807383526945.html>Rt Ang Male Header | 8-pin                | 1   |
| <a href=https://www.ebay.com/itm/357161444108>Small LiPo Battery | 130 mAh (JST-1.25)   | 1   |
| <a href="https://www.aliexpress.us/item/3256805695475806.html">Slide Switch</a>| MSTK-12c03 | 1   |

