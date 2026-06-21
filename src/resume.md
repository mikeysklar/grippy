# grippy — session resume

Handoff notes to continue this work from another machine.

## Device
- **Board:** ESP32-S3-DevKitC-1-**N8** (8 MB flash, **no PSRAM**, 512 KB SRAM).
- **CircuitPython:** 10.2.0.
- **Display:** 1.69" ST7789 IPS 240×280 (driven 280×240 rot 270) over SPI; **backlight on IO13** (on/off only — PWM has no effect on this panel).
- **Switches:** `SW_PINS = (IO6, IO5, IO4, IO2, IO7)` → chord indices 0–4; **index 4 = thumb** (taps select layers 1–7).
- **Battery:** 130 mAh LiPo. Key constraint — it **cannot source WiFi's sustained ~200–340 mA association burst** → brownout reboot loop. This drove the whole design.

## Git state
- Branch: **`backlight-off`** (off `main`; `main` untouched).
- Committed: `a8b5f0b` "working backlight off" (the original `(3,4)` backlight toggle).
- **Uncommitted/working changes since then** (boot-dark, wake-on-keypress, and now BLE) — see "What changed this session."
- `settings.toml` is **device-local, not in the repo** (never committed — safe for creds).
- ⚠️ If picking up on a different machine, **push from the original machine and pull here**, or these working-tree changes won't be present.

## Power profile (measured, @ ~5.16 V)
| State | WiFi | Backlight | Draw |
|---|---|---|---|
| idle, screen on | idle | on | 150 mA |
| idle, screen off | idle | off | 70 mA |
| screen on, no wifi | off | on | 140 mA |
| both off | off | off | ~60 mA |
| active web access, screen off | TX | off | 130–170 mA |

Decomposition: **base ~60 mA, backlight ~80 mA, WiFi idle ~10 mA, WiFi TX spikes ~200 mA+** (the brownout cause).

## Design decisions (settled)
1. **WiFi is dead on battery.** Any `CIRCUITPY_WIFI_SSID` in `settings.toml` → boot brownout loop (display blinks). Confirmed empirically. Do **not** put WiFi creds in settings.toml.
2. **Backlight boots dark; any key wakes it.** Saves ~80 mA. Reuses the sleep/wake logic.
3. **Never radio + display both on** (battery budget). `(3,4)` = Remote (display off), wake = Local (display on).
4. **Pivoted to BLE** for wireless `notes.txt` editing — low duty cycle, no sustained spike, and `supervisor.runtime.ble_workflow` is a **runtime toggle** (no reload, no settings.toml hacks).

## What changed this session (in `src/code.py`)
- **Boot dark:** both backlight init lines set `bl.value = False` (was a bug — a second line at the old ~line 72 was relighting it).
- **Sleep/wake:** `(3,4)` on layer 3 = sleep (backlight off); **any key on any layer wakes** (rising-edge gated so the `(3,4)` release flicker doesn't re-wake; wake press is consumed). Lives in `check_chords()` as an early `if not bl.value:` block.
- **BLE (new):** at boot, WiFi radio off + `supervisor.runtime.ble_workflow = False` (low power). `(3,4)` → backlight off + `ble_workflow = True`. Wake → backlight on + `ble_workflow = False`.
- Removed all the dead WiFi-connect code (`os`/`wifi` top imports, `ON_BATTERY`, runtime connect).

## settings.toml (device-local) — set this on the board
```toml
CIRCUITPY_BLE_NAME = "grippy"
# NO CIRCUITPY_WIFI_* keys (they brown out the battery at boot)
```

## NEXT STEP — test BLE (do this first)
1. Deploy `src/code.py` to the board (USB drive `cp` when CIRCUITPY mounts host-writable, or Web Workflow — but WW needs WiFi which we removed, so use the **USB drive**). Set `CIRCUITPY_BLE_NAME = "grippy"` in `settings.toml`.
2. On the device: tap thumb ×3 → layer 3, press **thumb+pinky `(3,4)`** → screen goes dark, BLE workflow turns on (serial prints `Remote: backlight OFF, BLE workflow ON (grippy)`).
3. **From a Mac (guaranteed path):** open **Chrome** → `https://code.circuitpython.org` → "Connect via BLE" → pick `grippy` → open/edit/save `notes.txt`.
4. **From iPhone/iPad (untested):** Safari has no Web Bluetooth. Try the **Bluefy** app pointed at `code.circuitpython.org`. If it fails, fall back to a custom Nordic-UART service + Bluefruit Connect (see research below).
5. Test **on battery** to confirm BLE doesn't brown out the 130 mAh cell. (Editing `notes.txt` over BLE only works when CircuitPython owns the FS, i.e. on battery / no USB host; read-only when plugged into USB.)

## Known gotchas / risks
- **No bulk cap (no space).** BLE peaks are still brief ~170 mA — *probably* fine (sub-ms blips vs WiFi's sustained burst) but unverified on this cell. Main thing to confirm in testing.
- **RAM:** no PSRAM. Watch `gc.mem_free()` with BLE + displayio + HID; most likely failure mode.
- **BLE bonding bug** (adafruit/circuitpython #9708) on ESP32-S3 — repeated pair/bond cycles can hard-fault to safe mode; avoid bonding / `_bleio.adapter.erase_bonding()` if it acts up. May still affect 10.2.0.
- **Random EDIT/NOTES storage mode at boot** (no boot.py → `usb_connected` unreliable early). Makes USB deploys flaky — retry resets until CIRCUITPY mounts host-writable, or add a deterministic `boot.py` (wait-for-enumeration → remount). Not yet done.
- Backlight boot **flash**: IO13 floats high (backlight on) from power-on until `code.py` drives it low — unavoidable in software (would need an IO13 pulldown resistor).

## Open / possible follow-ups
- Decide iOS path (Bluefy vs custom NUS service) after testing.
- Optional deterministic `boot.py` to stop the EDIT/NOTES flapping.
- The bigger **Settings menu** idea (layer renumber inserting a Menu at layer 3, combined items) was deferred in favor of this power/BLE work.
- Commit the BLE work and merge `backlight-off` → `main` once BLE is verified.

## Tooling notes
- Board reachable over USB serial via the `circuitpython-repl` MCP (`/dev/cu.usbmodem0FE9E9A75CC81`). The MCP REPL **resets its namespace between calls** — put multi-step snippets in one call.
- Web Workflow creds were `circuitpython.local` / device host `cpy-3_devkitc_1_n8-f09e9e7ac58c.local`, API password `funafuti` — but WiFi is now removed, so Web Workflow is gone; deploy via USB drive.
