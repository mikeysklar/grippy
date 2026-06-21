# chords_config.py
# Active chord mappings, grouped by layer.
#
# Layer plan (thumb taps select layer):
#   1  menu         (handled in code.py — not a keycode map)
#   2  alpha
#   3  num_nav      (numeric / navigation)
#   4  space_delim  (whitespace & delimiters)
#   5  scag         (Shift/Ctrl/Alt/Gui modifiers)
#
# Archived layers (mouse, media, function) live in chords_unused.py.

from adafruit_hid.keycode import Keycode

# ────────────── Layer 2: Alpha ──────────────
alpha = {
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

# ────────────── Layer 3: Numbers & Arrows ──────────────
num_nav = {
    # Numbers
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

    # Same backspace / space chords as the alpha layer
    (0, 1, 3):      Keycode.BACKSPACE,
    (0, 2, 3):      Keycode.SPACE,

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

# ────────────── Layer 4: Whitespace & Delimiters ──────────────
space_delim = {
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

# ────────────── Layer 5: Modifiers (SCAG) ──────────────
scag = {
    (3,):       Keycode.LEFT_SHIFT,
    (2,):       Keycode.LEFT_CONTROL,
    (1,):       Keycode.LEFT_ALT,
    (0,):       Keycode.LEFT_GUI,      # CMD / WIN
    (0, 1):     Keycode.RIGHT_ALT,     # OPTION (⌥)
}

# ────────────── Central Layer Map ──────────────
layer_maps = {
    1: "menu",        # sentinel — menu navigation handled in code.py
    2: alpha,
    3: num_nav,
    4: space_delim,
    5: scag,
}
