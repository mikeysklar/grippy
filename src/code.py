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

time.sleep(0.25)
displayio.release_displays()

# --- WiFi radio off (no networking; saves power) ---
try:
    import wifi
    wifi.radio.enabled = False
except Exception:
    pass

# --- Backlight ---
bl = digitalio.DigitalInOut(board.IO13)
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

# ─── USB HID setup (start OFF; keyboard only) ────────────────────────
usbmode = False
keyboard = None

def enable_hid():
    global usbmode, keyboard
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
_BASE_MENU = ["New Note", "View Note", "WiFi Sync", "Clr Note", "Clr All", "HID"]
menu_idx          = 0
menu_top          = 0
confirm_clear_all = False
clear_mode        = False     # "Clr Note" picker active
clear_idx         = 0
clear_top         = 0

# ─── Text window geometry for ST7789 ─────────────────────────────────
SCALE   = 4
GLYPH_W = 6 * SCALE          # terminalio glyph is 6x8
GLYPH_H = 8 * SCALE
COLS    = 10                 # ~10 chars/row at scale=4 fits well
ROWS    = 5                  # 5 rows on screen
WINDOW_SIZE = COLS * ROWS
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

# ─── Save-to-file config ──────────────────────────────────────────────
SAVE_PATH = "/notes.txt"

def _insert_code():
    try:
        from adafruit_hid.keycode import Keycode
        return Keycode.INSERT
    except Exception:
        return 73  # HID usage ID for Insert

INSERT_CODE = _insert_code()

def ensure_writable():
    try:
        with open("/.__rw_test__", "w") as _t:
            _t.write("x")
        try:
            import os
            os.remove("/.__rw_test__")
        except Exception:
            pass
        return True
    except OSError:
        try:
            storage.remount("/", False)  # False => read-write
            return True
        except Exception as e:
            print("Remount failed:", e)
            return False

def save_entry():
    global text_buffer
    entry = text_buffer.rstrip("\n")
    path = "/notes.txt"
    if not ensure_writable():
        print("Save aborted: filesystem still read-only")
        return
    try:
        with open(path, "a") as f:
            if entry:
                f.write(entry + ",\n")
            else:
                f.write(",\n")
        try:
            storage.sync()
        except Exception:
            pass
        print(f"Saved {len(entry)} chars to {path}")
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
    filtered = [p.rstrip("\r\n") for p in parts if p.strip() != ""]
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

def handle_page_nav(kc):
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
            elif name == "Clr All" and confirm_clear_all and i == menu_idx:
                name = "Clr All?!"
            s = ((">" if i == menu_idx else " ") + name)[:COLS]
        else:
            s = ""
        dirty |= _set_line(r, s)
    if dirty:
        NEEDS_REFRESH = True

def clear_all_notes():
    if not ensure_writable():
        print("Clear-all aborted: filesystem read-only")
        return
    try:
        with open("/notes.txt", "w") as f:
            f.write("")
        try:
            storage.sync()
        except Exception:
            pass
        print("notes.txt emptied")
    except OSError as e:
        print("Clear-all failed:", e)

def menu_activate():
    """Run the highlighted menu item."""
    global layer, thumb_taps, viewer_mode, confirm_clear_all, usbmode, typing_offset
    item = menu_items()[menu_idx]
    if item != "Clr All":
        confirm_clear_all = False
    if item == "New Note":
        viewer_mode = False
        typing_offset = 0
        layer = 2
        thumb_taps = 1            # 1 tap == alpha
        render_typing_window()
    elif item == "View Note":
        enter_viewer()
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
    elif item == "HID":
        if usbmode:
            disable_hid()
        else:
            enable_hid()
        render_menu()

def handle_menu_input(use):
    global menu_idx, confirm_clear_all
    n = len(menu_items())
    if use == (0,):
        menu_idx = (menu_idx - 1) % n
        confirm_clear_all = False
        render_menu()
    elif use == (3,):
        menu_idx = (menu_idx + 1) % n
        confirm_clear_all = False
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
    """Rewrite notes.txt without entry idx."""
    if not (0 <= idx < len(entries)):
        return
    if not ensure_writable():
        print("Delete aborted: filesystem read-only")
        return
    del entries[idx]
    try:
        with open("/notes.txt", "w") as f:
            for e in entries:
                f.write(e + ",\n")
        try:
            storage.sync()
        except Exception:
            pass
        print("Deleted entry", idx)
    except OSError as e:
        print("Delete failed:", e)

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

# ─── WiFi sync (remote) mode ─────────────────────────────────────────
# Boot stays WiFi-off (no boot connect → no association brownout). The
# "WiFi Sync" menu item turns the screen OFF and brings WiFi up only then,
# so the backlight (~80 mA) and the WiFi association spike never overlap.
remote_active = False
server = None
_mdns   = None

def _load_wifi_conf(path="/wifi.conf"):
    ssid = pw = None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().upper()
                v = v.strip().strip('"').strip("'")
                if k == "SSID":
                    ssid = v
                elif k == "PASSWORD":
                    pw = v
    except OSError:
        pass
    return ssid, pw

def start_remote():
    """Screen off → WiFi up → serve notes.txt at grippy.local."""
    global remote_active, server, _mdns
    # Screen off FIRST so backlight + WiFi association never overlap.
    bl.value = False
    try:
        display.refresh(minimum_frames_per_second=0)
    except Exception:
        pass

    ssid, pw = _load_wifi_conf()
    if not ssid:
        print("Remote: no SSID in wifi.conf; aborting")
        bl.value = True
        return

    import wifi
    import socketpool
    import mdns
    from adafruit_httpserver import Server, Response
    try:
        # Clean radio cycle before connect — a half-open radio throws
        # "Unknown failure 2". Off → settle → on → settle, then connect.
        wifi.radio.enabled = False
        time.sleep(1)
        wifi.radio.enabled = True
        time.sleep(0.5)
        try:
            wifi.radio.tx_power = 11   # dBm — trim the association current spike
        except Exception:
            pass
        print("Remote: connecting to", ssid)
        for attempt in range(4):
            try:
                wifi.radio.connect(ssid, pw)
                break
            except Exception as e:
                print("Remote: connect retry", attempt, e)
                time.sleep(2)
        ip = str(wifi.radio.ipv4_address)
        if ip == "None":
            raise RuntimeError("no IP after connect")
        print("Remote: connected", ip, "tx_power", wifi.radio.tx_power)

        _mdns = mdns.Server(wifi.radio)
        _mdns.hostname = "grippy"
        _mdns.advertise_service(service_type="_http", protocol="_tcp", port=80)

        pool = socketpool.SocketPool(wifi.radio)
        srv = Server(pool, "/", debug=False)

        def _serve_notes(request):
            try:
                with open("/notes.txt") as f:
                    data = f.read()
            except OSError:
                data = ""
            return Response(request, data, content_type="text/plain")

        srv.route("/")(_serve_notes)
        srv.route("/notes.txt")(_serve_notes)

        srv.start(ip, port=80)
        server = srv
        remote_active = True
        try:
            import gc
            print("Remote: mem_free", gc.mem_free())
        except Exception:
            pass
        print("Remote: http://grippy.local/notes.txt  (or http://%s/notes.txt)" % ip)
    except Exception as e:
        print("Remote: start failed:", e)
        stop_remote()

def stop_remote():
    """Tear down server + WiFi, screen back on."""
    global remote_active, server, _mdns
    remote_active = False
    if server is not None:
        try:
            server.stop()
        except Exception:
            pass
        server = None
    _mdns = None
    try:
        import wifi
        wifi.radio.enabled = False
    except Exception:
        pass
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    bl.value = True

# ─── Core chord logic ────────────────────────────────────────────────
def check_chords():
    global layer, thumb_taps, last_tap_time, thumb_down_at, long_hold_fired
    global last_combo, pending_combo, sent_release, skip_scag, scag_skip_combo
    global modifier_armed, held_modifier, last_time, last_repeat, accel_active
    global held_nav_combo, last_nav, held_combo, last_pending_combo
    global held_scroll_combo, last_scroll, text_buffer
    global usbmode, typing_offset, NEXT_OK
    global viewer_mode, confirm_clear_all, clear_mode

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
            render_menu()
            sent_release = True
            NEXT_OK      = now + DEBOUNCE_UP
        last_combo = combo
        return

    # A) Thumb-only gesture.
    #    Short tap(s) → typing layer: 1=alpha, 2=numeric, 3=delim, 4=scag.
    #    Long-hold (≥ LONG_HOLD_MENU) → jump to the menu, auto-saving any
    #    in-progress note. Short taps never reach the menu, so hopping layers /
    #    using thumb-chords never commits a note.
    if combo == (4,):
        if last_combo != (4,):
            thumb_down_at   = now
            long_hold_fired = False
        elif (not long_hold_fired) and (now - thumb_down_at) >= LONG_HOLD_MENU:
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
            confirm_clear_all = False
            if text_buffer:
                save_entry()      # auto-save the in-progress note on the way home
            print("→ menu (long-hold)")
            render_menu()
        last_combo = combo
        return

    if last_combo == (4,) and combo == ():
        if long_hold_fired:
            long_hold_fired = False          # menu already entered; consume release
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
            if layer == 5 and modifier_armed and last_combo in chords_config.alpha and usbmode:
                key = chords_config.alpha[last_combo]
                keyboard.press(held_modifier, key)
                keyboard.release_all()
                layer           = 2          # back to alpha to keep typing
                thumb_taps      = 1          # 1 tap == alpha
                modifier_armed  = False
                skip_scag       = False

            elif layer in (2, 3, 4):
                if use != (4,):
                    kc = lm.get(use)
                    if kc:
                        if usbmode:
                            keyboard.press(kc)
                            keyboard.release_all()

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

while True:
    check_chords()
    if remote_active and server is not None:
        try:
            server.poll()
        except Exception as e:
            print("server poll err:", e)
    _maybe_refresh_budgeted()
    time.sleep(SCAN_LOOP)
