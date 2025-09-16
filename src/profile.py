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

try:
    display.refresh(minimum_frames_per_second=0)
except TypeError:
    display.refresh()

bl.value = True  # now turn on the backlight

# Main text label
text_buffer = ""

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
SCAN_LOOP = 0.001
STABLE_MS_ALPHA = 0.001
STABLE_MS_OTHER = 0.001
DEBOUNCE_UP      = 0.001
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

# --- PROFILER ---------------------------------------------------------
USE_NS = hasattr(time, "monotonic_ns")
_now = (time.monotonic_ns if USE_NS else lambda: int(time.monotonic()*1_000_000_000))

PROF_PRINT_SEC = 2
_prof_last_print = _now()
prof = {
    "loop_ct": 0,
    "loop_ns": 0,
    "loop_ns_max": 0,
    "render_calls": 0,
    "render_ns": 0,
    "render_ns_max": 0,
    "refresh_calls": 0,
    "refresh_ns": 0,
    "refresh_ns_max": 0,
    "missed_scans": 0,
}

def prof_note_loop(dt_ns):
    prof["loop_ct"] += 1
    prof["loop_ns"] += dt_ns
    if dt_ns > prof["loop_ns_max"]: prof["loop_ns_max"] = dt_ns

def prof_note_render(dt_ns):
    prof["render_calls"] += 1
    prof["render_ns"] += dt_ns
    if dt_ns > prof["render_ns_max"]: prof["render_ns_max"] = dt_ns

def prof_note_refresh(dt_ns):
    prof["refresh_calls"] += 1
    prof["refresh_ns"] += dt_ns
    if dt_ns > prof["refresh_ns_max"]: prof["refresh_ns_max"] = dt_ns

def prof_missed_scan():
    prof["missed_scans"] += 1

def prof_maybe_print():
    global _prof_last_print
    now = _now()
    if now - _prof_last_print >= PROF_PRINT_SEC * 1_000_000_000:
        loops = max(1, prof["loop_ct"])
        avg_loop_us   = prof["loop_ns"]   / loops / 1000.0
        max_loop_us   = prof["loop_ns_max"] / 1000.0
        avg_r_us = (prof["render_ns"] / max(1, prof["render_calls"])) / 1000.0 if prof["render_calls"] else 0
        max_r_us = prof["render_ns_max"] / 1000.0
        avg_rf_us = (prof["refresh_ns"] / max(1, prof["refresh_calls"])) / 1000.0 if prof["refresh_calls"] else 0
        max_rf_us = prof["refresh_ns_max"] / 1000.0
        miss = prof["missed_scans"]

        print("LOOP avg={:.2f}us max={:.2f}us | render avg={:.2f}us max={:.2f}us | refresh avg={:.2f}us max={:.2f}us | missed_scans={}".format(
            avg_loop_us, max_loop_us, avg_r_us, max_r_us, avg_rf_us, max_rf_us, miss
        ))
        # reset rolling stats
        for k in prof: prof[k] = 0
        _prof_last_print = now

# ─── Text window geometry for ST7789 ─────────────────────────────────
SCALE   = 4
GLYPH_W = 6 * SCALE          # terminalio glyph is 6x8
GLYPH_H = 8 * SCALE
COLS    = 10                 # ~10 chars/row at scale=4 fits well
ROWS    = 5                  # now 5 rows on screen
LEFT, TOP = 20, 0
LINE_SPACING = 11  # extra pixels between rows

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

def _format_window(s: str) -> str:
    """Pad to window size and break into ROWS lines of COLS chars."""
    s = s + " " * max(0, WINDOW_SIZE - len(s))
    return "\n".join(s[i:i+COLS] for i in range(0, WINDOW_SIZE, COLS))

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
        render_typing_window()
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
    global viewer_mode, text_buffer, NEEDS_REFRESH
    text_buffer = ""
    d = False
    for r in range(ROWS): d |= _set_line(r, "")
    if d: NEEDS_REFRESH = True
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
        prof_missed_scan()
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
        if _set_line(ROWS-1, "HID: ON" if usbmode else "HID: OFF"):
            NEEDS_REFRESH = True
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
                            if len(text_buffer) > typing_offset + (COLS*ROWS):
                                typing_offset += COLS     # scrolled one line
                                render_typing_window()    # multiple rows changed
                            else:
                                _update_last_char_only()  # only one row changed

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
# --- in main loop:
while True:
    t0 = _now()
    check_chords()
    _maybe_refresh_budgeted()     # push at most one frame per ~18ms
    t1 = _now()
    prof_note_loop(t1 - t0)
    prof_maybe_print()
    time.sleep(SCAN_LOOP)
