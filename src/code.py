import time
import digitalio
import board
import busio
import displayio
from fourwire import FourWire
from adafruit_st7789 import ST7789
import terminalio
from adafruit_display_text import bitmap_label as label
import chords_config
import webserver
import notes
import game
import ble_hid

time.sleep(0.25)
displayio.release_displays()

# --- WiFi radio off (no networking; saves power) ---
try:
    import wifi
    wifi.radio.enabled = False
except Exception:
    pass

# --- BLE radio: OFF at boot (enabled on demand) ---
# An enabled-but-idle BLE controller draws current on EVERY boot even when BLE
# is never used. So leave the adapter OFF here and let ble_hid.start() power it
# up the first time the BLE menu item is selected (with a settle delay before
# advertising, so we still don't toggle adapter.enabled right next to a
# start_advertising — the thing that used to corrupt the controller).
#
# Still disable CircuitPython's built-in BLE WORKFLOW. It auto-advertises as
# CIRCUITPYxxxx and re-advertises on every disconnect, fighting ble_hid for the
# single radio — that caused the stray "CIRCUITPYac58e" name, macOS staying
# connected after BLE-off (workflow re-advertised → host reconnected), and the
# flaky pairing. boot.py disables it before it ever starts on a hard reset; this
# line covers soft resets (Ctrl-D), where boot.py does not run.
try:
    import supervisor
    supervisor.runtime.ble_workflow = False
except Exception:
    pass
try:
    import _bleio
    if _bleio.adapter.advertising:
        _bleio.adapter.stop_advertising()
    _bleio.adapter.enabled = False
except Exception:
    pass

# --- Backlight ---
bl = digitalio.DigitalInOut(board.IO13)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# --- Onboard RGB LED off (case covers it; saves power) ---
# CircuitPython drives the WS2812 on board.NEOPIXEL as a status LED. Drive it to
# black with the built-in neopixel_write (no neopixel lib needed) and release the
# pin. (The separate red power LED is hardwired to 3V3 — not software-controllable.)
try:
    import neopixel_write
    _np = digitalio.DigitalInOut(board.NEOPIXEL)
    _np.direction = digitalio.Direction.OUTPUT
    neopixel_write.neopixel_write(_np, bytearray([0, 0, 0]))
    _np.deinit()
except Exception:
    pass

# --- SPI + 4-wire display bus ---
spi = busio.SPI(clock=board.IO8, MOSI=board.IO9)   # no MISO required
display_bus = FourWire(
    spi,
    command=board.IO11,        # D/C
    chip_select=board.IO12,    # CS
    reset=board.IO10,          # RST
    baudrate=60_000_000
)

# --- ST7789 panel (280x240 variant) ---
display = ST7789(
    display_bus,
    width=280,
    height=240,
    rotation=270,
    rowstart=20,
    colstart=0,
    auto_refresh=False,
)

display_group = displayio.Group(scale=1)
display.root_group = display_group

# --- Black background tile ---
bg_bitmap = displayio.Bitmap(280, 240, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = 0x000000
bg = displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette)
display_group.append(bg)

try:
    display.refresh(minimum_frames_per_second=0)
except TypeError:
    display.refresh()

bl.value = True  # backlight on

# ─── Text buffer ─────────────────────────────────────────────────────
text_buffer = ""

# ─── Switch inputs ───────────────────────────────────────────────────
SW_PINS = (board.IO6, board.IO5, board.IO4, board.IO2, board.IO7)
pins = []
for gp in SW_PINS:
    p = digitalio.DigitalInOut(gp)
    p.direction = digitalio.Direction.INPUT
    p.pull = digitalio.Pull.UP
    pins.append(p)

# ─── Keyboard output (start OFF) ─────────────────────────────────────
# Two transports, one at a time: USB HID (`usbmode`, local `keyboard`) and
# BLE HID (`blemode`, owned by ble_hid). _kbd() returns whichever is ready to
# send (None if off, or BLE-on-but-not-yet-connected).
usbmode = False
blemode = False
keyboard = None
ble_err  = ""        # last BLE-enable error (shown on screen for debugging)

def enable_hid():
    global usbmode, keyboard
    if blemode:
        disable_ble()            # one transport at a time
    import usb_hid
    from adafruit_hid.keyboard import Keyboard
    keyboard = Keyboard(usb_hid.devices)
    usbmode = True
    print("USB HID enabled")

def disable_hid():
    global usbmode, keyboard
    keyboard = None
    usbmode = False
    print("USB HID disabled")

def enable_ble():
    global blemode, ble_err
    if usbmode:
        disable_hid()            # one transport at a time
    import gc
    gc.collect()
    print("BLE: free heap before start =", gc.mem_free())
    try:
        ble_hid.start("grippy")
        blemode = True
        ble_err = ""
        print("BLE HID enabled (advertising as grippy)")
    except Exception as e:
        blemode = False          # never crash the device on a radio hiccup
        ble_err = repr(e)
        try:
            ble_hid.stop()
        except Exception:
            pass
        print("BLE enable FAILED:", ble_err)

def disable_ble():
    global blemode
    ble_hid.stop()
    blemode = False
    print("BLE HID disabled")

def _kbd():
    """The keyboard ready to send right now, or None."""
    if usbmode:
        return keyboard
    if blemode:
        return ble_hid.kbd()     # None until a host connects
    return None

# ─── Timing constants ────────────────────────────────────────────────
SCAN_LOOP = 0.001
STABLE_MS_ALPHA = 0.03
STABLE_MS_OTHER = 0.02
DEBOUNCE_UP      = 0.05
TAP_WINDOW       = 0.5
MIN_TAP_INT      = 0.1
L5_REPEAT_MS     = 0.1
NAV_REPEAT_MS    = 0.2
LAYER_LOCK_COOLDOWN = 0.1
SCROLL_REPEAT_MS  = 0.15
THUMB_HOLD_TO_LOCK = 0.12
LONG_HOLD_MENU    = 0.70   # thumb-only hold ≥ this ⇒ jump to the menu (longer = taps to alpha are safer)
NEXT_OK = 0.0

# ─── State variables ────────────────────────────────────────────────
layer            = 1
thumb_taps       = 0
tap_in_prog      = False
thumb_down_at    = 0.0
long_hold_fired  = False
thumb_gesture    = False   # True only while the thumb is held ALONE from rest;
                           # a lone (4,) reached by releasing a chord's fingers
                           # is NOT a gesture (it's a chord tail) and must reach
                           # the typing/game handler instead of switching layer.
last_tap_time    = 0.0
last_combo       = ()
pending_combo    = None
sent_release     = False
skip_scag        = False
scag_skip_combo  = None
modifier_armed   = False
held_modifier    = None
last_time        = time.monotonic()
held_combo       = ()
last_repeat      = 0.0
accel_active     = False
held_nav_combo   = ()
last_nav         = 0.0
last_pending_combo = None
last_layer_change = 0.0
held_scroll_combo = ()
last_scroll       = 0.0
last_thumb_rise    = 0.0
thumb_locked       = False
viewer_mode  = False
entries      = []
entry_idx    = 0
entry_offset = 0
typing_offset = 0

# ─── Menu / sub-mode state ───────────────────────────────────────────
# A note auto-saves on the long-hold back to the menu (the only way home),
# so layer switches never commit and there's no separate Save item.
_BASE_MENU = ["New Note", "View Note", "WiFi Sync", "Clr Note", "Game Mode", "BLE", "Clr BLE", "HID", "Clr All"]
menu_idx          = 0
menu_top          = 0
confirm_clear_all = False
confirm_clr_ble   = False     # "Clr BLE" two-tap confirm (erases BLE bonds)
clear_mode        = False     # "Clr Note" picker active
clear_idx         = 0
clear_top         = 0
game_mode         = False     # chord-trainer (game.py) active

# ─── Text window geometry for ST7789 ─────────────────────────────────
SCALE   = 4
GLYPH_W = 6 * SCALE          # terminalio glyph is 6x8
GLYPH_H = 8 * SCALE
COLS    = 10                 # ~10 chars/row at scale=4 fits well
ROWS    = 5                  # 5 rows on screen
LEFT, TOP = 20, 0
LINE_SPACING = 11            # extra pixels between rows

line_labels = []
_shown_lines = [""] * ROWS
for r in range(ROWS):
    lbl = label.Label(
        terminalio.FONT,
        text="",
        color=0xFF00FF,
        x=LEFT,
        y=TOP + (r + 1) * GLYPH_H + r * LINE_SPACING,
        scale=SCALE,
    )
    display_group.append(lbl)
    line_labels.append(lbl)

def _set_line(row: int, s: str) -> bool:
    """Update one line if text changed; return True if dirtied."""
    if s != _shown_lines[row]:
        line_labels[row].text = s
        _shown_lines[row] = s
        return True
    return False

def _format_window_lines(s: str):
    win = COLS * ROWS
    s = s + " " * max(0, win - len(s))
    return [s[i:i+COLS] for i in range(0, win, COLS)]

# ─── Budgeted manual refresh ─────────────────────────────────────────
USE_NS = hasattr(time, "monotonic_ns")
_now = (time.monotonic_ns if USE_NS else lambda: int(time.monotonic()*1_000_000_000))

NEEDS_REFRESH = False
LAST_REFRESH_NS = 0
MIN_REFRESH_INTERVAL_NS = int(1e9 / 55)   # ~55 fps cap (~18ms)

def _maybe_refresh_budgeted():
    global NEEDS_REFRESH, LAST_REFRESH_NS
    if not NEEDS_REFRESH:
        return
    now_ns = _now()
    if (now_ns - LAST_REFRESH_NS) >= MIN_REFRESH_INTERVAL_NS:
        try:
            display.refresh(minimum_frames_per_second=0)
        except TypeError:
            display.refresh()
        LAST_REFRESH_NS = now_ns
        NEEDS_REFRESH = False

# ─── edit view ──────────────────────────────────────────────
def render_typing_window():
    """Render a COLS×ROWS window of text_buffer starting at typing_offset."""
    global typing_offset, NEEDS_REFRESH
    win = COLS * ROWS
    typing_offset = max(0, min(typing_offset, max(0, len(text_buffer) - win)))
    start, end = typing_offset, typing_offset + win
    lines = _format_window_lines(text_buffer[start:end])
    dirty = False
    for r, s in enumerate(lines):
        dirty |= _set_line(r, s)
    if dirty:
        NEEDS_REFRESH = True

# ─── Save-to-file (note storage lives in notes.py) ───────────────────
def save_entry():
    global text_buffer
    if notes.append_entry(text_buffer.rstrip("\n")):
        text_buffer = ""
        render_typing_window()

# ─── viewer mode ───────────────────────────────────────────────
def load_entries():
    global entries, entry_idx, entry_offset
    entries = notes.read_entries()
    entry_idx = 0
    entry_offset = 0

def render_entry_window():
    global NEEDS_REFRESH
    if not entries:
        d = _set_line(0, "(no notes)")
        d |= _set_line(1, "")
        d |= _set_line(2, "")
        d |= _set_line(3, "")
        if d: NEEDS_REFRESH = True
        return
    s = entries[entry_idx]
    max_off = max(0, len(s) - (COLS*ROWS))
    start = max(0, min(entry_offset, max_off))
    window = s[start:start+(COLS*ROWS)]
    lines = _format_window_lines(window)
    d = False
    for r, t in enumerate(lines):
        d |= _set_line(r, t)
    if d: NEEDS_REFRESH = True

def enter_viewer():
    # NOTE: do NOT clear text_buffer — an in-progress note must survive a peek
    # at the viewer (resume it later via "Add Note").
    global viewer_mode, NEEDS_REFRESH
    d = False
    for r in range(ROWS):
        d |= _set_line(r, "")
    if d: NEEDS_REFRESH = True
    load_entries()
    viewer_mode = True
    render_entry_window()

def _update_last_char_only():
    global NEEDS_REFRESH
    win = COLS * ROWS
    start = typing_offset
    caret = len(text_buffer) - 1
    if caret < start or caret >= start + win:
        return
    rel = caret - start
    row = rel // COLS
    row_start = start + row * COLS
    row_text = text_buffer[row_start:row_start+COLS]
    row_text = row_text + " " * max(0, COLS - len(row_text))
    if _set_line(row, row_text):
        NEEDS_REFRESH = True

# ─── Printable-char map for the local note buffer ────────────────────
# HID keycode → character to echo into text_buffer. Letters/digits are
# computed; punctuation & whitespace come from this table. Non-printable
# keys (Esc, arrows, nav, Delete) map to None → sent over HID but not echoed.
_KC_CHAR = {
    39: "0", 40: "\n", 43: " ", 44: " ", 45: "-", 46: "=",
    47: "[", 48: "]", 49: "\\", 51: ";", 52: "'", 53: "`",
    54: ",", 55: ".", 56: "/",
}

def _kc_to_char(kc):
    if 4 <= kc <= 29:
        return chr(kc - 4 + ord('a'))
    if 30 <= kc <= 38:
        return chr(kc - 30 + ord('1'))
    return _KC_CHAR.get(kc)

# ─── Menu (layer 1) ──────────────────────────────────────────────────
def menu_items():
    return _BASE_MENU

def render_menu():
    """Draw the layer-1 menu as a scrolling ROWS-high window with a > cursor."""
    global NEEDS_REFRESH, menu_top, menu_idx
    items = menu_items()
    n = len(items)
    if menu_idx >= n:
        menu_idx = n - 1
    if menu_idx < 0:
        menu_idx = 0
    if menu_idx < menu_top:
        menu_top = menu_idx
    elif menu_idx >= menu_top + ROWS:
        menu_top = menu_idx - ROWS + 1
    dirty = False
    for r in range(ROWS):
        i = menu_top + r
        if i < n:
            name = items[i]
            if name == "HID":
                name = "HID On" if usbmode else "HID Off"
            elif name == "BLE":
                # Off / advertising / connected, so you can see pairing succeed
                name = ("BLE " + ("Con" if ble_hid.connected() else "Adv")
                        ) if blemode else "BLE Off"
            elif name == "Clr All" and confirm_clear_all and i == menu_idx:
                name = "Clr All?!"
            elif name == "Clr BLE" and confirm_clr_ble and i == menu_idx:
                name = "Clr BLE?!"
            s = ((">" if i == menu_idx else " ") + name)[:COLS]
        else:
            s = ""
        dirty |= _set_line(r, s)
    if dirty:
        NEEDS_REFRESH = True

def clear_all_notes():
    if notes.write_entries([]):
        print("notes.txt emptied")

def menu_activate():
    """Run the highlighted menu item."""
    global layer, thumb_taps, viewer_mode, confirm_clear_all, confirm_clr_ble, usbmode, typing_offset
    item = menu_items()[menu_idx]
    if item != "Clr All":
        confirm_clear_all = False
    if item != "Clr BLE":
        confirm_clr_ble = False
    if item == "New Note":
        viewer_mode = False
        typing_offset = 0
        layer = 2
        thumb_taps = 1            # 1 tap == alpha
        render_typing_window()
    elif item == "View Note":
        enter_viewer()
    elif item == "Game Mode":
        enter_game()              # chord trainer
    elif item == "WiFi Sync":
        start_remote()            # screen off + WiFi up
    elif item == "Clr Note":
        enter_clear()             # per-note delete picker
    elif item == "Clr All":
        if not confirm_clear_all:
            confirm_clear_all = True
            render_menu()         # shows "Clr All?!" — select again to wipe
        else:
            confirm_clear_all = False
            clear_all_notes()
            render_menu()
    elif item == "Clr BLE":
        # Wipe stored BLE bonds so a host can pair fresh (recovers macOS "stuck
        # on pairing" from a stale on-device bond). Also Forget the device on the
        # host. Two-tap confirm so it isn't triggered by accident.
        if not confirm_clr_ble:
            confirm_clr_ble = True
            render_menu()         # shows "Clr BLE?!" — select again to erase
        else:
            confirm_clr_ble = False
            ok = ble_hid.erase_pairing()
            print("BLE bonds erased" if ok else "BLE erase failed")
            render_menu()
    elif item == "HID":
        if usbmode:
            disable_hid()
        else:
            enable_hid()
        render_menu()
    elif item == "BLE":
        if blemode:
            disable_ble()
            render_menu()
        else:
            enable_ble()
            if blemode:
                render_menu()
            else:
                # enable failed — surface the error on screen (serial dies when
                # the BLE adapter toggles, so this is the only way to read it)
                _draw_lines(["BLE FAIL"] +
                            [ble_err[i:i + COLS]
                             for i in range(0, min(len(ble_err), COLS * 4), COLS)])

def handle_menu_input(use):
    global menu_idx, confirm_clear_all, confirm_clr_ble
    n = len(menu_items())
    if use == (0,):
        menu_idx = (menu_idx - 1) % n
        confirm_clear_all = False
        confirm_clr_ble = False
        render_menu()
    elif use == (3,):
        menu_idx = (menu_idx + 1) % n
        confirm_clear_all = False
        confirm_clr_ble = False
        render_menu()
    elif use in ((1,), (2,), (1, 2)):
        menu_activate()

def handle_viewer_input(use):
    """0 = previous entry, 3 = next entry, select = back to menu."""
    global viewer_mode, entry_idx, entry_offset
    if use in ((1,), (2,), (1, 2)):
        viewer_mode = False
        render_menu()
        return
    if not entries:
        return
    if use == (0,):
        entry_idx = (entry_idx - 1) % len(entries)
        entry_offset = 0
        render_entry_window()
    elif use == (3,):
        entry_idx = (entry_idx + 1) % len(entries)
        entry_offset = 0
        render_entry_window()

# ─── Clr Note: per-entry delete picker ───────────────────────────────
def render_clear_list():
    """Scrolling list of notes.txt entries with a > cursor (for deletion)."""
    global NEEDS_REFRESH, clear_top
    n = len(entries)
    if n == 0:
        d = _set_line(0, "(no notes)")
        for r in range(1, ROWS):
            d |= _set_line(r, "")
        if d:
            NEEDS_REFRESH = True
        return
    if clear_idx < clear_top:
        clear_top = clear_idx
    elif clear_idx >= clear_top + ROWS:
        clear_top = clear_idx - ROWS + 1
    dirty = False
    for r in range(ROWS):
        i = clear_top + r
        if i < n:
            text = entries[i].replace("\n", " ")
            s = ((">" if i == clear_idx else " ") + text)[:COLS]
        else:
            s = ""
        dirty |= _set_line(r, s)
    if dirty:
        NEEDS_REFRESH = True

def enter_clear():
    global clear_mode, clear_idx, clear_top
    load_entries()
    clear_idx = 0
    clear_top = 0
    clear_mode = True
    render_clear_list()

def delete_entry(idx):
    """Rewrite notes.txt without entry idx (restores the list if write fails)."""
    if not (0 <= idx < len(entries)):
        return
    removed = entries[idx]
    del entries[idx]
    if notes.write_entries(entries):
        print("Deleted entry", idx)
    else:
        entries.insert(idx, removed)   # write failed (read-only) → undo

def handle_clear_input(use):
    global clear_mode, clear_idx
    if not entries:
        if use in ((0,), (3,), (1,), (2,), (1, 2)):
            clear_mode = False
            render_menu()
        return
    if use == (0,):
        clear_idx = (clear_idx - 1) % len(entries)
        render_clear_list()
    elif use == (3,):
        clear_idx = (clear_idx + 1) % len(entries)
        render_clear_list()
    elif use in ((1,), (2,), (1, 2)):
        delete_entry(clear_idx)
        if not entries:
            clear_mode = False
            render_menu()
        else:
            if clear_idx >= len(entries):
                clear_idx = len(entries) - 1
            render_clear_list()

# ─── Game (chord trainer) — logic in game.py ─────────────────────────
def _draw_lines(lines):
    """Blit a list of up to ROWS strings (game.py's display bridge)."""
    global NEEDS_REFRESH
    dirty = False
    for r in range(ROWS):
        s = lines[r] if r < len(lines) else ""
        dirty |= _set_line(r, s[:COLS])
    if dirty:
        NEEDS_REFRESH = True

def enter_game():
    global game_mode
    game_mode = True
    _draw_lines(game.start())

def handle_game_input(use):
    global game_mode
    r = game.handle(use)
    if r == "EXIT":
        game_mode = False
        render_menu()
    else:
        _draw_lines(r)

# ─── WiFi sync (remote) mode ─────────────────────────────────────────
# Boot stays WiFi-off (no boot connect → no association brownout). The
# "WiFi Sync" menu item turns the screen OFF and brings WiFi up only then,
# so the backlight (~80 mA) and the WiFi association spike never overlap.
# The networking lives in webserver.py; backlight ordering lives here.

def start_remote():
    """Screen off → WiFi up → serve notes.txt at grippy.local."""
    # Screen off FIRST so backlight + WiFi association never overlap.
    bl.value = False
    try:
        display.refresh(minimum_frames_per_second=0)
    except Exception:
        pass
    if not webserver.start():     # WiFi failed → screen back on
        bl.value = True

def stop_remote():
    """Tear down server + WiFi, screen back on."""
    webserver.stop()
    bl.value = True

# ─── Core chord logic ────────────────────────────────────────────────
def check_chords():
    global layer, thumb_taps, last_tap_time, thumb_down_at, long_hold_fired, thumb_gesture
    global last_combo, pending_combo, sent_release, skip_scag, scag_skip_combo
    global modifier_armed, held_modifier, last_time, last_repeat, accel_active
    global held_nav_combo, last_nav, held_combo, last_pending_combo
    global held_scroll_combo, last_scroll, text_buffer
    global usbmode, typing_offset, NEXT_OK
    global viewer_mode, confirm_clear_all, clear_mode, game_mode

    now = time.monotonic()
    if now < NEXT_OK:
        # still in debounce window—keep tracking state but don’t emit
        last_combo = tuple(i for i, down in enumerate(tuple(not p.value for p in pins)) if down)
        return

    pressed = tuple(not p.value for p in pins)
    combo   = tuple(i for i, down in enumerate(pressed) if down)

    # Sleep/wake: while the backlight is off the device sleeps. Any new chord
    # turns the backlight back on and is consumed (so it doesn't type), since
    # you can't see the screen to navigate back to the (3,4) toggle.
    if not bl.value:
        # Wake only on a clean press from fully-released (rising edge), so the
        # partial-release flicker of the (3,4) sleep chord doesn't re-wake it.
        if combo and last_combo == ():
            stop_remote()   # WiFi off (if up) + backlight back on
            print("Backlight: ON (wake)")
            layer        = 1          # wake home = menu
            thumb_taps   = 1
            viewer_mode  = False
            clear_mode   = False
            game_mode    = False
            render_menu()
            sent_release = True
            NEXT_OK      = now + DEBOUNCE_UP
        last_combo = combo
        return

    # The thumb-only gesture is only real when the thumb is pressed ALONE from
    # rest. The instant any non-thumb finger is involved we're in a chord, so
    # disarm the gesture — a later lone (4,) is then just the tail of releasing
    # that chord and must reach the typing/game handler, not switch layers.
    if any(i != 4 for i in combo):
        thumb_gesture = False

    # A) Thumb-only gesture.
    #    Short tap(s) → typing layer: 1=alpha, 2=numeric, 3=delim, 4=scag.
    #    Long-hold (≥ LONG_HOLD_MENU) → jump to the menu, auto-saving any
    #    in-progress note. Short taps never reach the menu, so hopping layers /
    #    using thumb-chords never commits a note.
    if combo == (4,):
        if last_combo == ():
            # clean rising edge from rest → a genuine thumb-only gesture begins
            thumb_down_at   = now
            long_hold_fired = False
            thumb_gesture   = True
        # A lone (4,) that is NOT a gesture is a chord tail (e.g. (0,4)->(4,)):
        # fall through to the normal handler so the game/typing layer still
        # receives the chord on release.
        if thumb_gesture:
            if (not long_hold_fired) and (now - thumb_down_at) >= LONG_HOLD_MENU:
                long_hold_fired = True
                layer           = 1
                thumb_taps      = 0
                pending_combo   = None
                sent_release    = False
                skip_scag       = False
                modifier_armed  = False
                held_modifier   = None
                scag_skip_combo = None
                viewer_mode     = False
                clear_mode      = False
                game_mode       = False
                confirm_clear_all = False
                if text_buffer:
                    save_entry()  # auto-save the in-progress note on the way home
                print("→ menu (long-hold)")
                render_menu()
            last_combo = combo
            return

    # Thumb released after a genuine thumb-only gesture: long-hold already
    # acted (consume it); a short tap selects a typing layer. A chord tail
    # (thumb_gesture False) skips this so releasing a thumb-chord never
    # switches layers or exits the game.
    if last_combo == (4,) and combo == () and thumb_gesture:
        thumb_gesture = False
        if long_hold_fired:
            long_hold_fired = False          # menu already entered; consume release
        elif game_mode:
            # In the game, layers are meaningless — drills accept the raw chord
            # directly (numbers are finger-only, no layer switch needed). So a
            # thumb tap is consumed but ignored; only a long-hold exits.
            pass
        else:
            # short tap → select typing layer (1 tap == alpha == layer 2)
            if now - last_tap_time < TAP_WINDOW:
                thumb_taps += 1
            else:
                thumb_taps = 1
            last_tap_time = now
            layer = min(thumb_taps + 1, 5)
            print("→ layer-%d" % layer)
            viewer_mode = False
            clear_mode = False
            game_mode = False
            confirm_clear_all = False
            render_typing_window()
        pending_combo   = None
        sent_release    = False
        skip_scag       = False
        modifier_armed  = False
        held_modifier   = None
        scag_skip_combo = None
        held_scroll_combo = ()
        last_combo = combo
        return

    # B) Stabilize into pending_combo
    if combo != last_combo:
        last_time = now
        if last_combo == () and combo != ():
            pending_combo = None
            sent_release  = False

    ms = STABLE_MS_ALPHA if layer == 2 else STABLE_MS_OTHER
    if combo and (now - last_time) >= ms and combo != pending_combo:
        pending_combo = combo

    pending_changed    = (pending_combo != last_pending_combo)
    last_pending_combo = pending_combo

    # Layer 1: menu home (+ View / Clr-Note sub-modes). Act on finger-release.
    # 0 = up/prev, 3 = down/next, 1 / 2 / (1,2) = select. Thumb taps switch layer.
    if layer == 1:
        if len(combo) < len(last_combo) and last_combo and not sent_release:
            use = pending_combo or last_combo
            if use != (4,):
                if clear_mode:
                    handle_clear_input(use)
                elif viewer_mode:
                    handle_viewer_input(use)
                elif game_mode:
                    handle_game_input(use)
                else:
                    handle_menu_input(use)
            sent_release = True
            NEXT_OK = now + 0.12
        if not combo and last_combo:
            pending_combo = None
            sent_release  = False
        last_combo = combo
        return

    lm = chords_config.layer_maps[layer]

    # Layer-5 SCAG “arm”
    if layer == 5 and not modifier_armed and pending_combo in chords_config.scag:
        held_modifier   = chords_config.scag[pending_combo]
        modifier_armed  = True
        scag_skip_combo = pending_combo
        skip_scag       = True
        pending_combo   = None
        last_combo      = ()
        return

    # First-release send for typing layers (2 alpha, 3 num, 4 delim) + SCAG (5)
    if len(combo) < len(last_combo) and last_combo and not sent_release:
        if skip_scag and last_combo == scag_skip_combo:
            skip_scag = False
        else:
            use = pending_combo or last_combo
            if layer == 5 and modifier_armed and last_combo in chords_config.alpha and (usbmode or blemode):
                key = chords_config.alpha[last_combo]
                kb = _kbd()
                if kb:
                    kb.press(held_modifier, key)
                    kb.release_all()
                layer           = 2          # back to alpha to keep typing
                thumb_taps      = 1          # 1 tap == alpha
                modifier_armed  = False
                skip_scag       = False

            elif layer in (2, 3, 4):
                if use != (4,):
                    kc = lm.get(use)
                    if kc:
                        kb = _kbd()
                        if blemode:
                            print("BLE type kc=%d kb=%s conn=%s" %
                                  (kc, kb is not None, ble_hid.connected()))
                        if kb:
                            try:
                                kb.press(kc)
                                kb.release_all()
                            except Exception as e:
                                print("BLE send err:", repr(e))

                        if kc == 42:  # Backspace — edit local buffer
                            if text_buffer:
                                text_buffer = text_buffer[:-1]
                                if typing_offset > 0 and len(text_buffer) <= typing_offset:
                                    typing_offset = max(0, typing_offset - COLS)
                            render_typing_window()
                        else:
                            char = _kc_to_char(kc)   # None for non-printable nav keys
                            if char is not None:
                                text_buffer += char
                                if len(text_buffer) > typing_offset + (COLS*ROWS):
                                    typing_offset += COLS
                                    render_typing_window()
                                else:
                                    _update_last_char_only()

        sent_release = True
        NEXT_OK = now + DEBOUNCE_UP

    if not combo and last_combo:
        pending_combo  = None
        sent_release   = False
        held_nav_combo = ()
        skip_layer_lock = False

    last_combo = combo

# ─── Main loop ───────────────────────────────────────────────────────
render_menu()   # boot home = layer-1 menu
_maybe_refresh_budgeted()

_ble_was_connected = False

while True:
    check_chords()
    webserver.poll()
    if blemode:
        ble_hid.poll()                       # re-advertise if the host dropped
        c = ble_hid.connected()
        if c != _ble_was_connected:          # connection state changed
            _ble_was_connected = c
            print("BLE connected" if c else "BLE advertising")
            if layer == 1 and not (viewer_mode or clear_mode or game_mode):
                render_menu()                # live Adv -> Con in the menu
    _maybe_refresh_budgeted()
    time.sleep(SCAN_LOOP)
