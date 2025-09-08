# chords_config.py
# All chord mappings for c5k-left.py, grouped by layer.

from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.mouse import Mouse

# ────────────── Layer 1: Alpha ──────────────
alpha = {  # layer-1: alpha
    (0,):           Keycode.E,
    (1,):           Keycode.I,
    (2,):           Keycode.A,
    (3,):           Keycode.S,
    (0, 1):         Keycode.R,
    (0, 2):         Keycode.O,
    (0, 3):         Keycode.C,
    (1, 2):         Keycode.N,
    (1, 3):         Keycode.L,
    (2, 3):         Keycode.T,
    (0, 1, 2):      Keycode.D,
    (1, 2, 3):      Keycode.P,
    (0, 1, 2, 3):   Keycode.U,
    (0, 2, 3):      Keycode.SPACE,
    (0, 1, 3):      Keycode.BACKSPACE,
    (0, 4):         Keycode.M,
    (1, 4):         Keycode.G,
    (2, 4):         Keycode.H,
    (3, 4):         Keycode.B,
    (0, 1, 4):      Keycode.Y,
    (0, 2, 4):      Keycode.W,
    (0, 3, 4):      Keycode.X,
    (1, 2, 4):      Keycode.F,
    (1, 3, 4):      Keycode.K,
    (2, 3, 4):      Keycode.V,
    (0, 1, 2, 4):   Keycode.J,
    (1, 2, 3, 4):   Keycode.Z,
    (0, 1, 2, 3, 4):Keycode.Q,
}

# ────────────── Layer 2: Numbers & Arrows ──────────────
num_nav = {  # layer-2: numbers & thumb-based arrows
    # Numbers (unchanged)
    (0,):           Keycode.ONE,
    (1,):           Keycode.TWO,
    (2,):           Keycode.THREE,
    (3,):           Keycode.FOUR,
    (0, 1):         Keycode.FIVE,
    (1, 2):         Keycode.SIX,
    (2, 3):         Keycode.SEVEN,
    (0, 2):         Keycode.EIGHT,
    (1, 3):         Keycode.NINE,
    (0, 1, 2):      Keycode.ZERO,

    # Thumb-based ARROWS 
    (0, 4):         Keycode.UP_ARROW,
    (1, 4):         Keycode.LEFT_ARROW,
    (2, 4):         Keycode.RIGHT_ARROW,
    (3, 4):         Keycode.DOWN_ARROW,

    # Thumb-based NAV
    (0, 1, 4):      Keycode.PAGE_UP,
    (2, 3, 4):      Keycode.PAGE_DOWN,
    (0, 1, 2, 4):   Keycode.HOME,
    (0, 2, 4):      Keycode.INSERT,
    (1, 3, 4):      Keycode.DELETE,
    (1, 2, 3, 4):   Keycode.END,
}

# ────────────── Layer 3: Whitespace & Delimiters ──────────────
space_delim = {  # layer-3: whitespace & delimiters
    (0,):           Keycode.ESCAPE,
    (1,):           Keycode.TAB,
    (2,):           Keycode.PERIOD,
    (3,):           Keycode.MINUS,
    (2, 3):         Keycode.FORWARD_SLASH,
    (0, 1):         Keycode.ENTER,
    (0, 2):         Keycode.COMMA,
    (1, 3):         Keycode.LEFT_BRACKET,
    (0, 3):         Keycode.RIGHT_BRACKET,
    (1, 2, 3):      Keycode.BACKSLASH,
    (1, 2):         Keycode.BACKSPACE,
    (0, 1, 3):      Keycode.QUOTE,
    (0, 2, 3):      Keycode.SEMICOLON,
    (0, 1, 2, 3):   Keycode.GRAVE_ACCENT,
    (0, 1, 2):      Keycode.DELETE,
}

# ────────────── Layer 4: Modifiers ──────────────
scag = {
    (3,):       Keycode.LEFT_SHIFT,
    (2,):       Keycode.LEFT_CONTROL,
    (1,):       Keycode.LEFT_ALT,
    (0,):       Keycode.LEFT_GUI,      # CMD / WIN
    (0, 1):     Keycode.RIGHT_ALT,     # OPTION (⌥)
}

# ────────────── Layer 5: Mouse Actions ──────────────

# ─── Mouse move chords: thumb + one finger ───────────────────────────
mouse_move_chords = {
    (0, 4): ( 0, -50),  # Up
    (1, 4): ( 0,  50),  # Down
    (2, 4): ( 50,  0),  # Right
    (3, 4): (-50,  0),  # Left
}

# ─── Mouse button chords: two fingers only ──────────────────────────
mouse_button_chords = {
    (3, 2): Mouse.LEFT_BUTTON,     # ← no thumb
    (1, 1): Mouse.MIDDLE_BUTTON,
    (0, 1): Mouse.RIGHT_BUTTON,
    (0, 3): Mouse.FORWARD_BUTTON,
}

# ─── Mouse scroll chords: two fingers + thumb ───────────────────────
mouse_scroll_chords = {
    (0, 1, 4):  50,   # Scroll Up
    (2, 3, 4): -50,   # Scroll Down
}

# ─── Mouse hold/release chords (three fingers) ─────────────────────
mouse_hold_chords = {
    (0, 1, 2): Mouse.LEFT_BUTTON,   # press & hold
}
mouse_release_chords = {
    (0, 1, 3): Mouse.LEFT_BUTTON,   # release
}

# ─── Acceleration chord (three fingers) ─────────────────────────────
ACCEL_CHORD = (1, 2, 3)

# ────────────── Layer 6: macOS Media Keys ──────────────
media = {   # 6: macOS media keys
    (0,):           ConsumerControlCode.BRIGHTNESS_DECREMENT,
    (1,):           ConsumerControlCode.BRIGHTNESS_INCREMENT,
    (2,):           ConsumerControlCode.VOLUME_DECREMENT,
    (3,):           ConsumerControlCode.VOLUME_INCREMENT,
    (0, 1):         ConsumerControlCode.MUTE,
    (2, 3):         ConsumerControlCode.PLAY_PAUSE,
    (0, 2):         ConsumerControlCode.SCAN_NEXT_TRACK,
    (1, 3):         ConsumerControlCode.SCAN_PREVIOUS_TRACK,
    (0, 3):         ConsumerControlCode.FAST_FORWARD,
    (1, 2):         ConsumerControlCode.REWIND,
    (0, 1, 2):      ConsumerControlCode.STOP,
    (0, 1, 3):      ConsumerControlCode.EJECT,
}

# Layer 7: Function keys F1–F12, mapped to the same chord order as 1–0 digits
function = {
    (0,):        Keycode.F1,   # 1 → F1
    (1,):        Keycode.F2,   # 2 → F2
    (2,):        Keycode.F3,   # 3 → F3
    (3,):        Keycode.F4,   # 4 → F4
    (0, 1):      Keycode.F5,   # 5 → F5
    (1, 2):      Keycode.F6,   # 6 → F6
    (2, 3):      Keycode.F7,   # 7 → F7
    (0, 2):      Keycode.F8,   # 8 → F8
    (1, 3):      Keycode.F9,   # 9 → F9
    (0, 1, 2):   Keycode.F10,  # 0 → F10
    (1, 2, 3):   Keycode.F11,  # next free 3-finger combo → F11
    (0, 2, 3):   Keycode.F12,  # following 3-finger combo → F12
}

# ────────────── Central Layer Map ──────────────
layer_maps = {
    1: alpha,                                   # letters
    2: num_nav,                                 # numbers / navigation
    3: space_delim,                             # spaces / delimeters
    4: scag,
    5: {   # Mouse 
        "move":    mouse_move_chords,
        "button":  mouse_button_chords,
        "scroll":  mouse_scroll_chords,
        "hold":    mouse_hold_chords,
        "release": mouse_release_chords,
        "accel":   ACCEL_CHORD,
    },
    6: media,                                   # macOS media keys
    7: function,                                # F1 - F12
}

