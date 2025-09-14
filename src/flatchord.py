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
import storage

time.sleep(0.1)

displayio.release_displays()

# --- Backlight (optional; tie high if not used) ---
bl = digitalio.DigitalInOut(board.IO13)   # BLK
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

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
    rotation=270,   # matches your test
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
display_group.append(bg)  # background at z=0

#text_buffer = ""
#text_label = label.Label(terminalio.FONT, text=text_buffer, color=0xFFFFFF, x=20, y=20, scale=4)
#display_group.append(text_label)

try:
    display.refresh(minimum_frames_per_second=0)
except TypeError:
    display.refresh()

bl.value = True  # now turn on the backlight

# Main text label 
text_buffer = ""
text_label = label.Label(
    terminalio.FONT, text=text_buffer, color=0xFFFFFF, x=20, y=20, scale=5
)
display_group.append(text_label)

SW_PINS = (
    board.IO6,  # SW0
    board.IO5,  # SW1
    board.IO4,  # SW2
    board.IO2,  # SW3
    board.IO7,  # SW4
)

pins = []
for gp in SW_PINS:
    p = digitalio.DigitalInOut(gp)
    p.direction = digitalio.Direction.INPUT
    p.pull = digitalio.Pull.UP
    pins.append(p)

# ─── USB HID setup (start OFF) ─────────────────────────────────────────
usbmode = False
keyboard = mouse = cc = None

def enable_hid():
    global usbmode, keyboard, mouse, cc, Keycode, ConsumerControlCode
    import usb_hid
    from adafruit_hid.keyboard import Keyboard
    from adafruit_hid.mouse import Mouse
    from adafruit_hid.consumer_control import ConsumerControl
    from adafruit_hid.consumer_control_code import ConsumerControlCode
    from adafruit_hid.keycode import Keycode
    keyboard = Keyboard(usb_hid.devices)
    mouse = Mouse(usb_hid.devices)
    cc = ConsumerControl(usb_hid.devices)
    usbmode = True
    print("USB HID enabled")

def disable_hid():
    global usbmode, keyboard, mouse, cc
    keyboard = mouse = cc = None
    usbmode = False
    print("USB HID disabled")

# ─── Timing constants ────────────────────────────────────────────────
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
NEXT_OK = 0.0

# ─── State variables ────────────────────────────────────────────────
layer            = 1
thumb_taps       = 0
tap_in_prog      = False
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
entry_offset = 0  # kept for future per-entry scrolling (10-char steps)
typing_offset = 0

# ─── Mouse chords for layer-7 ────────────────────────────────────────
MOVE_DELTA = 5
ACCEL_MULTIPLIER = 2
ACCEL_CHORD = (1, 2, 3)

# ─── Text window geometry for ST7789 ─────────────────────────────────
COLS = 8           # chars per line
ROWS = 3           # lines on screen
WINDOW_SIZE = COLS * ROWS  # 41 chars

def _format_window(s: str) -> str:
    """Pad to window size and break into ROWS lines of COLS chars."""
    s = s + " " * max(0, WINDOW_SIZE - len(s))
    return "\n".join(s[i:i+COLS] for i in range(0, WINDOW_SIZE, COLS))

def _set_and_refresh(s: str):
    if s != text_label.text:
        text_label.text = s
        try:
            display.refresh(minimum_frames_per_second=0)
        except TypeError:
            display.refresh()

# ─── edit view ──────────────────────────────────────────────
def render_typing_window():
    """Render a COLS×ROWS window of text_buffer starting at typing_offset."""
    global text_buffer, text_label, typing_offset
    # Clamp offset in case buffer shrank
    typing_offset = max(0, min(typing_offset, max(0, len(text_buffer) - WINDOW_SIZE)))
    start = typing_offset
    end   = typing_offset + WINDOW_SIZE
    window = text_buffer[start:end]
    _set_and_refresh(_format_window(window))

# ─── Save-to-file config ──────────────────────────────────────────────
SAVE_PATH = "/notes.txt"

def _insert_code():
    # Try to get Keycode.INSERT without requiring HID to be enabled
    try:
        from adafruit_hid.keycode import Keycode
        return Keycode.INSERT
    except Exception:
        # HID usage ID for Insert is 73
        return 73

INSERT_CODE = _insert_code()

# ─── Make FS writable if it’s read-only ──────────────────────────────
def ensure_writable():
    try:
        with open("/.__rw_test__", "w") as _t:
            _t.write("x")
        # cleanup
        try:
            import os
            os.remove("/.__rw_test__")
        except Exception:
            pass
        return True
    except OSError:
        # Attempt to remount read-write
        try:
            storage.remount("/", False)  # False => read-write
            return True
        except Exception as e:
            print("Remount failed:", e)
            return False

# ─── save ────────────────────────────────────────────
def save_entry():
    global text_buffer, text_label
    entry = text_buffer.rstrip("\n")
    path = "/notes.txt"

    # Ensure FS is writable; try once to fix if not
    if not ensure_writable():
        print("Save aborted: filesystem still read-only")
        return

    try:
        with open(path, "a") as f:
            if entry:
                f.write(entry + ",\n")   # <-- add comma + newline
            else:
                f.write(",\n")           # <-- blank entry still has comma
        try:
            storage.sync()
        except Exception:
            pass
        print(f"Saved {len(entry)} chars to {path}")
        # Clear buffer for the next entry
        text_buffer = ""
        _set_and_refresh(text_buffer)
    except OSError as e:
        print("Save failed:", e)

# ─── viewer mode ───────────────────────────────────────────────

def _kc(vname, fallback):
    try:
        from adafruit_hid.keycode import Keycode
        return getattr(Keycode, vname)
    except Exception:
        return fallback

KC_PAGE_UP   = _kc("PAGE_UP",   75)
KC_PAGE_DOWN = _kc("PAGE_DOWN", 78)
KC_UP        = _kc("UP_ARROW",  82)
KC_DOWN      = _kc("DOWN_ARROW",81)

def load_entries():
    """(Re)load entries from /notes.txt, ignoring blanks like ',\\n'."""
    global entries, entry_idx, entry_offset
    try:
        with open(SAVE_PATH, "r") as f:
            data = f.read().replace("\r\n", "\n")
    except OSError:
        entries = []
        entry_idx = 0
        entry_offset = 0
        return

    parts = data.split(",\n")
    if parts and parts[-1] == "":
        parts.pop()

    filtered = []
    for p in parts:
        if p.strip() == "":
            continue
        filtered.append(p.rstrip("\r\n"))

    entries = filtered
    entry_idx = 0 if entries else 0
    entry_offset = 0

def render_entry_window():
    """Show current entry in a fixed COLS×ROWS window starting at entry_offset."""
    global text_label
    if not entries:
        text_label.text = "(no notes)"
        _set_and_refresh("(no notes)")
        return
    s = entries[entry_idx]
    # Clamp offset
    max_off = max(0, len(s) - WINDOW_SIZE)
    start = max(0, min(entry_offset, max_off))
    window = s[start:start+WINDOW_SIZE]
    _set_and_refresh(_format_window(window))

def enter_viewer():
    """Clear screen, load entries, show first entry."""
    global viewer_mode, text_buffer
    text_buffer = ""           # clear typing buffer on entry
    _set_and_refresh("")
    load_entries()
    viewer_mode = True
    render_entry_window()

def handle_page_nav(kc):
    """PAGE_UP/PAGE_DOWN with wrap-around between entries."""
    global entry_idx, entry_offset
    if not entries:
        render_entry_window()
        return
    if kc == KC_PAGE_UP:
        entry_idx = (entry_idx - 1) % len(entries)
    elif kc == KC_PAGE_DOWN:
        entry_idx = (entry_idx + 1) % len(entries)
    entry_offset = 0
    render_entry_window()

def handle_intra_scroll(kc):
    """Scroll inside the current entry by one line (COLS chars)."""
    global entry_offset
    if not entries:
        render_entry_window()
        return
    s = entries[entry_idx]
    max_off = max(0, len(s) - WINDOW_SIZE)
    if kc == KC_UP:
        entry_offset = max(0, entry_offset - COLS)
    elif kc == KC_DOWN:
        entry_offset = min(max_off, entry_offset + COLS)
    render_entry_window()

# ─── Core chord logic ────────────────────────────────────────────────
def check_chords():
    global layer, thumb_taps, last_tap_time
    global last_combo, pending_combo, sent_release, skip_scag, scag_skip_combo
    global modifier_armed, held_modifier, last_time, last_repeat, accel_active
    global held_nav_combo, last_nav, held_combo, last_pending_combo
    global held_scroll_combo, last_scroll, text_buffer, text_label
    global usbmode, typing_offset, NEXT_OK

    now     = time.monotonic()
    if now < NEXT_OK:
        # still in debounce window—keep tracking state but don’t emit
        last_combo = tuple(i for i, down in enumerate(tuple(not p.value for p in pins)) if down)
        return
    pressed = tuple(not p.value for p in pins)
    combo   = tuple(i for i, down in enumerate(pressed) if down)

    # ─── A) Pure-thumb release ⇒ layer-lock ───────────────────────────
    if last_combo == (4,) and combo == ():
        if now - last_tap_time < TAP_WINDOW:
            thumb_taps += 1
        else:
            thumb_taps = 1
        last_tap_time = now
        layer = min(thumb_taps, 7)
        print(f"→ locked to layer-{layer}")
        pending_combo = None
        sent_release  = False
        skip_scag     = False
        modifier_armed = False
        held_modifier = None
        scag_skip_combo = None
        held_scroll_combo = ()
        last_combo = combo
        return

    # ─── B) Stabilize into pending_combo ──────────────────────────────
    if combo != last_combo:
        last_time = now
        if last_combo == () and combo != ():
            pending_combo = None
            sent_release  = False

    ms = STABLE_MS_ALPHA if layer == 1 else STABLE_MS_OTHER
    if combo and (now - last_time) >= ms and combo != pending_combo:
        pending_combo = combo

    pending_changed    = (pending_combo != last_pending_combo)
    last_pending_combo = pending_combo

    lm = chords_config.layer_maps[layer]

    # ─── Special: Layer‑3 chord (0,1,2,3,4) → toggle HID ──────────────
    if layer == 3 and combo == (0,1,2,3,4) and combo != last_combo:
        if not usbmode:
            enable_hid()
        else:
            disable_hid()
        _set_and_refresh("HID: ON" if usbmode else "HID: OFF")
        last_combo = combo
        sent_release = True
        time.sleep(0.3)  # debounce
        return

    # ─── macOS media keys ─────────────────────────────────────────────
    if usbmode and layer == 6:
        if combo and combo != last_combo and combo in lm:
            code = lm[combo]
            cc.send(code)
            sent_release = True
            NEXT_OK = now + DEBOUNCE_UP

    # ─── Layer-4 SCAG “arm” ───────────────────────────────────────────
    if layer == 4 and not modifier_armed and pending_combo in chords_config.scag:
        held_modifier   = chords_config.scag[pending_combo]
        modifier_armed  = True
        scag_skip_combo = pending_combo
        skip_scag       = True
        pending_combo   = None
        last_combo      = ()
        return

    # ─── Layer-5: Mouse ───────────────────────────────────────────────
    if usbmode and layer == 5:
        accel_active = (pending_combo == chords_config.ACCEL_CHORD)

        if pending_combo in chords_config.mouse_button_chords and pending_changed:
            mouse.click(chords_config.mouse_button_chords[pending_combo])
            held_combo   = ()
            sent_release = True
            NEXT_OK = now + DEBOUNCE_UP
            return

        if pending_combo in chords_config.mouse_scroll_chords and pending_changed:
            amt = chords_config.mouse_scroll_chords[pending_combo]
            if accel_active: amt *= ACCEL_MULTIPLIER
            mouse.move(wheel=amt)
            held_scroll_combo = pending_combo
            last_scroll       = now
            sent_release      = True
            return

        if (
            pending_combo == held_scroll_combo
            and pending_combo in chords_config.mouse_scroll_chords
            and (now - last_scroll) >= SCROLL_REPEAT_MS
        ):
            amt = chords_config.mouse_scroll_chords[pending_combo]
            if accel_active: amt *= ACCEL_MULTIPLIER
            mouse.move(wheel=amt)
            last_scroll = now
            return

        if pending_combo in chords_config.mouse_move_chords and pending_changed:
            dx, dy = chords_config.mouse_move_chords[pending_combo]
            if accel_active: dx *= ACCEL_MULTIPLIER; dy *= ACCEL_MULTIPLIER
            mouse.move(dx, dy)
            held_combo   = pending_combo
            last_repeat  = now
            sent_release = True
            return

        if pending_combo == held_combo \
           and pending_combo in chords_config.mouse_move_chords \
           and (now - last_repeat) >= L5_REPEAT_MS:
            dx, dy = chords_config.mouse_move_chords[held_combo]
            if accel_active: dx *= ACCEL_MULTIPLIER; dy *= ACCEL_MULTIPLIER
            mouse.move(dx, dy)
            last_repeat = now
            return

        if pending_combo in chords_config.mouse_hold_chords and pending_changed:
            mouse.press(chords_config.mouse_hold_chords[pending_combo])
            held_combo   = ()
            sent_release = True
            return

        if pending_combo in chords_config.mouse_release_chords and pending_changed:
            mouse.release(chords_config.mouse_release_chords[pending_combo])
            held_combo   = ()
            sent_release = True
            return

    # ─── First-release send for layers 1–3,6-7 ───────────────────────
    if len(combo) < len(last_combo) and last_combo and not sent_release:
        if skip_scag and last_combo == scag_skip_combo:
            skip_scag = False
        else:
            use = pending_combo or last_combo
            if layer == 4 and modifier_armed and last_combo in chords_config.alpha and usbmode:
                key = chords_config.alpha[last_combo]
                keyboard.press(held_modifier, key)
                keyboard.release_all()
                layer           = 1
                thumb_taps      = 1
                modifier_armed  = False
                skip_scag       = False

            elif layer in (1, 2, 3, 6, 7):
                # Skip HID toggle chord (layer-3, (0,1,2,3,4))
                if use != (4,) and not (layer == 3 and use == (0,1,2,3,4)):
                    kc = lm.get(use)
                    if kc:
                        if usbmode:
                            keyboard.press(kc)
                            keyboard.release_all()

                        if kc == 61:  # handled above
                            pass

                        elif kc == 42:  # Backspace
                            if text_buffer:
                                text_buffer = text_buffer[:-1]
                                # If we deleted back past the current window, pull it up by one line
                                if typing_offset > 0 and len(text_buffer) <= typing_offset:
                                    typing_offset = max(0, typing_offset - COLS)
                            render_typing_window()

                        elif kc == INSERT_CODE:
                            save_entry()
                            time.sleep(0.15)

                        elif kc in (KC_PAGE_UP, KC_PAGE_DOWN):
                            if not viewer_mode:
                                enter_viewer()          # clears screen, loads first entry
                            else:
                                handle_page_nav(kc)     # wrap-around prev/next
                            time.sleep(0.12)

                        elif kc in (KC_UP, KC_DOWN):
                            if not viewer_mode:
                                enter_viewer()
                            handle_intra_scroll(kc)
                            time.sleep(0.08)

                        else:
                            # 1. Map kc -> printable char
                            if 4 <= kc <= 29:        # A-Z
                                char = chr(kc - 4 + ord('a'))
                            elif 30 <= kc <= 38:     # 1-9
                                char = chr(kc - 30 + ord('1'))
                            elif kc == 39:           # 0
                                char = "0"
                            elif kc == 44:           # Space
                                char = " "
                            else:
                                char = "?"           # fallback

                            # 2. Append the character
                            text_buffer += char

                            # 3. If we overflow the COLS×ROWS window, scroll down one line (COLS chars)
                            if len(text_buffer) > typing_offset + WINDOW_SIZE:
                                typing_offset += COLS

                            # 4. Render the current typing window
                            render_typing_window()

        sent_release = True
        NEXT_OK = now + DEBOUNCE_UP

    if not combo and last_combo:
        pending_combo  = None
        sent_release   = False
        held_nav_combo = ()
        skip_layer_lock = False

    last_combo = combo

# ─── Main loop ───────────────────────────────────────────────────────
while True:
    check_chords()
    time.sleep(0.01)
