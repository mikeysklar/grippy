# chords_unused.py
# Archived chord layers, kept for possible future use. NOT imported by code.py.
#
# Previously these were layers 5 (mouse), 6 (media), 7 (function). To revive,
# import the relevant dict(s) into chords_config.layer_maps and restore the
# matching handler block(s) in code.py (see git history around the BLE/WiFi era).

from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_hid.mouse import Mouse

# ────────────── Mouse ──────────────
# Mouse move chords: thumb + one finger
mouse_move_chords = {
    (0, 4): ( 0, -50),  # Up
    (1, 4): ( 0,  50),  # Down
    (2, 4): ( 50,  0),  # Right
    (3, 4): (-50,  0),  # Left
}

# Mouse button chords: two fingers only
mouse_button_chords = {
    (3, 2): Mouse.LEFT_BUTTON,     # no thumb
    (1, 1): Mouse.MIDDLE_BUTTON,
    (0, 1): Mouse.RIGHT_BUTTON,
    (0, 3): Mouse.FORWARD_BUTTON,
}

# Mouse scroll chords: two fingers + thumb
mouse_scroll_chords = {
    (0, 1, 4):  50,   # Scroll Up
    (2, 3, 4): -50,   # Scroll Down
}

# Mouse hold/release chords (three fingers)
mouse_hold_chords = {
    (0, 1, 2): Mouse.LEFT_BUTTON,   # press & hold
}
mouse_release_chords = {
    (0, 1, 3): Mouse.LEFT_BUTTON,   # release
}

# Acceleration chord (three fingers)
ACCEL_CHORD = (1, 2, 3)

# ────────────── macOS Media Keys ──────────────
media = {
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

# ────────────── Function keys F1–F12 ──────────────
function = {
    (0,):        Keycode.F1,
    (1,):        Keycode.F2,
    (2,):        Keycode.F3,
    (3,):        Keycode.F4,
    (0, 1):      Keycode.F5,
    (1, 2):      Keycode.F6,
    (2, 3):      Keycode.F7,
    (0, 2):      Keycode.F8,
    (1, 3):      Keycode.F9,
    (0, 1, 2):   Keycode.F10,
    (1, 2, 3):   Keycode.F11,
    (0, 2, 3):   Keycode.F12,
}
