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

# space is its own chord (alpha (0,2,3)); derived so it tracks the live map
_SPACE_CHORD = None
for _chord, _kc in chords_config.alpha.items():
    if _kc == chords_config.Keycode.SPACE:
        _SPACE_CHORD = _chord
        break

def _chord_for(ch):
    if ch == ' ':
        return _SPACE_CHORD
    if ch.isdigit():
        return _NUM_CHORD.get(ch)
    return _LETTER_CHORD.get(ch.upper())

def _pattern(chord):
    """Render a chord as a 5-slot finger map: thumb + space + 4 fingers.
    Thumb is on the left to match the physical orientation of the thumb key.
    e.g. E=(0,) -> '- #---',  M=(0,4) -> '# #---'."""
    if not chord:
        return "?"
    fingers = "".join("#" if i in chord else "-" for i in range(4))
    thumb = "#" if 4 in chord else "-"
    return thumb + " " + fingers

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

# Timed mode types whole phrases (Monkeytype-style): several short common
# words + spaces, for realistic speed practice. Lowercase, letters + spaces
# only; each wraps to <=3 rows of 10 chars.
_PHRASES = [
    "the cat ran to the sun",
    "we sit in the red car",
    "a dog and a cat play",
    "she had a cup of tea",
    "run to the top of it",
    "he put the box on it",
    "let us go for a walk",
    "i can see the big sun",
    "the man sat on a log",
    "we go up the big hill",
    "the sea is far from us",
    "a red bus is on the way",
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

# timed (phrase typing)
_W = 10                  # display columns (mirrors code.py COLS) for wrapping
_phrase_idx = 0
_cpos = 0                # index of the next char to type in the phrase
_t0 = 0.0
_last_time = 0.0
_last_wpm = 0
_errors = 0

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
    global _phase, _mode, _phrase_idx, _cpos, _t0, _errors
    _phase = "play"
    _mode = "timed"
    _phrase_idx = 0
    _cpos = 0
    _errors = 0
    _t0 = _now()
    return _timed_lines()

def _wrap(s, width, max_rows):
    """Word-wrap s into <=max_rows lines of <=width chars (break at spaces)."""
    rows = []
    cur = ""
    for w in s.split(" "):
        cand = w if cur == "" else cur + " " + w
        if len(cand) <= width:
            cur = cand
        else:
            rows.append(cur)
            cur = w
    if cur:
        rows.append(cur)
    while len(rows) < max_rows:
        rows.append("")
    return rows[:max_rows]

def _timed_lines(done_time=None):
    if _phrase_idx >= len(_PHRASES):
        # whole set finished — show the last result
        return ["", " FINISHED", "%dwpm" % _last_wpm, "", "Back=menu"]
    phrase = _PHRASES[_phrase_idx]
    # typed chars uppercase, remaining lowercase — the case edge is the caret
    marked = "".join(c.upper() if i < _cpos else c
                     for i, c in enumerate(phrase))
    r0, r1, r2 = _wrap(marked, _W, 3)
    head = "%d/%d %.1fs" % (_phrase_idx + 1, len(_PHRASES), _now() - _t0)
    if done_time is not None:
        wpm = int(round(len(phrase) * 12.0 / done_time)) if done_time > 0 else 0
        foot = "%dwpm" % wpm
    else:
        nxt = phrase[_cpos] if _cpos < len(phrase) else " "
        foot = "next: " + ("_" if nxt == " " else nxt)
    return [head[:_W], r0, r1, r2, foot[:_W]]

def _handle_timed(use):
    global _phrase_idx, _cpos, _t0, _last_time, _last_wpm, _errors
    if _phrase_idx >= len(_PHRASES):
        return _timed_lines()
    phrase = _PHRASES[_phrase_idx]
    if use == _chord_for(phrase[_cpos]):
        _cpos += 1
        if _cpos >= len(phrase):
            _last_time = _now() - _t0
            _last_wpm = (int(round(len(phrase) * 12.0 / _last_time))
                         if _last_time > 0 else 0)
            _phrase_idx += 1
            _cpos = 0
            _t0 = _now()
            return _timed_lines(done_time=_last_time)
        return _timed_lines()
    _errors += 1
    return _timed_lines()   # wrong chord: ignore, keep going
