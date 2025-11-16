# Grippy – Ultracompact One-Handed “Grippy” Keyboard

![Grippy Assembled](images/grippy-asm.jpeg)

## Overview

Grippy started as a one-handed pocket keyboard. It uses chords (SAIE layout) to enter letters, numbers, and symbols. It quickly evolved into an everyday-carry note-taking pocket comptuer. 

I’ve gone through five complete hardware re-designs to achieve a low-profile ultralight EDC.

![FreeCAD](images/freecad-case.png)

### Features

- **One-handed SAIE chording**
  - Enter letters, numbers, symbols, and whitespace via chords.
  - Optimized for thumb + fingers usage in a “grippy” hold.

- **Everyday carry note-taking**
  - Designed to live in a pocket or bag.
  - Note-taking directly on device (no external keyboard required).
  - Review notes on device

- **USB keyboard mode**
  - Acts as a USB HID keyboard when connected to a host.
  - Can be used for quick text entry or macro-style workflows.

- **Ultracompact, slim form factor**
  - Small footprint 
  - Stacked SMD construction to keep the profile low 
  - Minimal weight

- **Open hardware / hackable**
  - KiCad PCB project and STEP files.
  - FreeCAD case modeling.
  - 3D-printable shell, buttons, and cap (`.3mf` files).
  - CircuitPython 10.x source, chord config, and main app code.

![3D Board](images/kicad-raytrace.jpg)

## Specs

| Item        | Value                  |
| ----------- | ---------------------- |
| Dimensions  | 61 x 35 mm             |
| Weight      | 29 grams               |
| Firmware    | CircuitPython 10.x     |
| Controller  | ESP32-S3               |
| Construction| SMD components on PCB  |

---

![Inside](images/no-dissassemble.jpeg)

## Files & Project Layout

| File                     | Description                        | Markdown usage example |
| ------------------------ | ---------------------------------- | ---------------------- |
| `![cad](cad)`            | FreeCAD case Files (3mF)           | `![case](images/freecad-case.png)` |
| `![kicad](grippy)`       | KiCAD files ippy                   | `![grippy asm](images/grippy-asm.jpeg)` |
| `images/kicad-raytrace.jpg`  | Render / raytrace from KiCad       | `![raytrace](images/kicad-raytrace.jpg)` |
| `images/no-dissassemble.jpeg`| “No disassemble” glam shot         | `![no disassemble](images/no-dissassemble.jpeg)` |
