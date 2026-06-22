# game.py — chord-training game for grippy.
#
# A level-based trainer for learning the chord map one character at a time.
# Logic-only and display-free (like notes.py / webserver.py): every entry
# point returns a list of <=5 short strings for code.py to blit, or the
# sentinel "EXIT" to ask code.py to drop back to the main menu.
#
# Flow: the Game menu item lands on this module's own mode picker. Pick a
# mode → play. Long-hold (handled in code.py) always exits to the main menu.
#
# Modes (increasing difficulty):
#   Guided    — show the target AND its finger pattern; you copy it.
#   Hint Miss — recall from memory; a miss reveals the pattern, retry to clear.
#   Timed     — type simple words against a clock.

import time
import chords_config

# ─── target → chord lookup (built from the live chord maps) ──────────
def _kc_char(kc):
    if 4 <= kc <= 29:
        return chr(kc - 4 + ord('A'))   # A–Z (uppercase for display)
    if 30 <= kc <= 38:
        return chr(kc - 30 + ord('1'))  # 1–9
    if kc == 39:
        return '0'
    return None

_LETTER_CHORD = {}
for _chord, _kc in chords_config.alpha.items():
    _c = _kc_char(_kc)
    if _c and _c.isalpha():
        _LETTER_CHORD[_c] = _chord

_NUM_CHORD = {}
for _chord, _kc in chords_config.num_nav.items():
    _c = _kc_char(_kc)
    if _c and _c.isdigit():
        _NUM_CHORD[_c] = _chord

def _chord_for(ch):
    if ch.isdigit():
        return _NUM_CHORD.get(ch)
    return _LETTER_CHORD.get(ch.upper())

def _pattern(chord):
    """Render a chord as a 5-slot finger map: 4 fingers + space + thumb.
    e.g. E=(0,) -> '#--- -',  M=(0,4) -> '#--- #'."""
    if not chord:
        return "?"
    fingers = "".join("#" if i in chord else "-" for i in range(4))
    thumb = "#" if 4 in chord else "-"
    return fingers + " " + thumb

# ─── content: stages walked by Guided + Hint, words used by Timed ────
# Letters grouped by chord size (= difficulty = ~frequency, since the alpha
# map is frequency-ordered), then numbers.
_STAGES = [
    ("L1", "EIAS"),       # single finger
    ("L2", "ROCNLT"),     # two fingers
    ("L3", "DPU"),        # three / four fingers
    ("L4", "MGHB"),       # thumb + one
    ("L5", "YWXFKVJZQ"),  # thumb + more
    ("N1", "1234"),       # single-finger numbers
    ("N2", "567890"),     # number combos
]

_WORDS = [
    "CAT", "DOG", "SUN", "RUN", "TOP", "TEN", "SEA", "ONE", "RED", "SIT",
    "NOT", "TOE", "EAR", "LINE", "RAIN", "NOTE", "STAR", "CANE", "TONE", "SAIL",
]

# ─── state ───────────────────────────────────────────────────────────
_phase = "menu"          # "menu" | "play"
_mode = None             # "guided" | "hint" | "timed"

_GAME_MENU = ["Guided", "Hint Miss", "Timed", "Back"]
_menu_idx = 0

# guided / hint
_stage_idx = 0
_queue = []              # remaining (char, chord) for the current stage
_cleared = 0             # chars cleared in this stage
_stage_total = 0
_miss = False            # last attempt was wrong (reveal pattern in hint mode)

# timed
_word_idx = 0
_wpos = 0
_t0 = 0.0
_last_word_time = 0.0
_word_errors = 0

def _now():
    return time.monotonic()

# ─── public entry points ─────────────────────────────────────────────
def start():
    """Enter the game; show the mode picker."""
    global _phase, _menu_idx
    _phase = "menu"
    _menu_idx = 0
    return _menu_lines()

def handle(use):
    """Process one released chord. Returns display lines, or 'EXIT'."""
    if _phase == "menu":
        return _handle_menu(use)
    if _mode == "timed":
        return _handle_timed(use)
    return _handle_drill(use)   # guided + hint

# ─── mode picker ─────────────────────────────────────────────────────
def _menu_lines():
    lines = []
    for i, name in enumerate(_GAME_MENU):
        lines.append(((">" if i == _menu_idx else " ") + name)[:10])
    return lines

def _handle_menu(use):
    global _menu_idx, _phase, _mode
    n = len(_GAME_MENU)
    if use == (0,):
        _menu_idx = (_menu_idx - 1) % n
        return _menu_lines()
    if use == (3,):
        _menu_idx = (_menu_idx + 1) % n
        return _menu_lines()
    if use in ((1,), (2,), (1, 2)):
        choice = _GAME_MENU[_menu_idx]
        if choice == "Back":
            return "EXIT"
        if choice == "Guided":
            return _start_drill("guided")
        if choice == "Hint Miss":
            return _start_drill("hint")
        if choice == "Timed":
            return _start_timed()
    return _menu_lines()

# ─── guided / hint drill ─────────────────────────────────────────────
def _load_stage():
    global _queue, _cleared, _stage_total, _miss
    _name, chars = _STAGES[_stage_idx]
    _queue = [(c, _chord_for(c)) for c in chars if _chord_for(c)]
    _cleared = 0
    _stage_total = len(_queue)
    _miss = False

def _start_drill(mode):
    global _phase, _mode, _stage_idx
    _phase = "play"
    _mode = mode
    _stage_idx = 0
    _load_stage()
    return _drill_lines()

def _drill_lines():
    name = _STAGES[_stage_idx][0]
    if not _queue:
        return ["", "  done!", "%s clear" % name, "", ""]
    ch, chord = _queue[0]
    head = "%s  %d/%d" % (name, _cleared, _stage_total)
    show_pattern = (_mode == "guided") or _miss
    pat = _pattern(chord) if show_pattern else ""
    if _mode == "guided":
        foot = "copy it"
    else:
        foot = "miss-try" if _miss else "recall"
    return [head, "", "  " + ch, pat, foot]

def _handle_drill(use):
    global _stage_idx, _cleared, _miss
    if not _queue:
        return _drill_lines()
    ch, chord = _queue[0]
    if use == chord:
        _queue.pop(0)
        _cleared += 1
        _miss = False
        if not _queue:
            # stage complete → advance, or finish the whole game
            if _stage_idx + 1 < len(_STAGES):
                _stage_idx += 1
                _load_stage()
                name = _STAGES[_stage_idx][0]
                return ["stage up!", "", "  next:", "  " + name, ""]
            return ["", " ALL DONE", " well done", "", "Back=menu"]
        return _drill_lines()
    _miss = True
    return _drill_lines()

# ─── timed words ─────────────────────────────────────────────────────
def _start_timed():
    global _phase, _mode, _word_idx, _wpos, _t0, _word_errors
    _phase = "play"
    _mode = "timed"
    _word_idx = 0
    _wpos = 0
    _word_errors = 0
    _t0 = _now()
    return _timed_lines()

def _timed_lines(done_time=None):
    if _word_idx >= len(_WORDS):
        return ["", " FINISHED", "all words", "", "Back=menu"]
    word = _WORDS[_word_idx]
    typed = word[:_wpos] + "." * (len(word) - _wpos)
    if done_time is not None:
        foot = "%.1fs ok" % done_time
    else:
        foot = "%.1fs" % (_now() - _t0)
    return ["word %d" % (_word_idx + 1), " " + word, " " + typed, "", foot]

def _handle_timed(use):
    global _word_idx, _wpos, _t0, _last_word_time, _word_errors
    if _word_idx >= len(_WORDS):
        return _timed_lines()
    word = _WORDS[_word_idx]
    expected = _chord_for(word[_wpos])
    if use == expected:
        _wpos += 1
        if _wpos >= len(word):
            _last_word_time = _now() - _t0
            _word_idx += 1
            _wpos = 0
            _t0 = _now()
            return _timed_lines(done_time=_last_word_time)
        return _timed_lines()
    _word_errors += 1
    return _timed_lines()   # wrong chord: ignore, keep going
