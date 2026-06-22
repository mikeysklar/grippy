# notes.py — local note storage for grippy.
#
# Pure file I/O over /notes.txt: owns the on-disk format and the read-only
# remount dance. Holds NO app state (text_buffer, entries) and does no
# rendering — the caller owns those.
#
# Format: entries are separated by ",\n". A bare comma inside a note is fine
# (only ",\n" splits). Empty/whitespace-only entries are dropped on read.
#
# ⚠️ On USB the Mac owns the filesystem, so writes are read-only and the
# append/write functions return False (expected, not a bug). Take notes on
# battery, where CircuitPython owns the FS.

import storage

PATH = "/notes.txt"


def ensure_writable():
    """True if / is writable, remounting read-write if needed."""
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


def read_entries(path=PATH):
    """Parse the notes file → list of entry strings (empty list if missing)."""
    try:
        with open(path, "r") as f:
            data = f.read().replace("\r\n", "\n")
    except OSError:
        return []
    parts = data.split(",\n")
    if parts and parts[-1] == "":
        parts.pop()
    return [p.rstrip("\r\n") for p in parts if p.strip() != ""]


def append_entry(text, path=PATH):
    """Append one entry. Returns True on success, False if read-only."""
    if not ensure_writable():
        print("Save aborted: filesystem still read-only")
        return False
    try:
        with open(path, "a") as f:
            f.write((text + ",\n") if text else ",\n")
        try:
            storage.sync()
        except Exception:
            pass
        print("Saved %d chars to %s" % (len(text), path))
        return True
    except OSError as e:
        print("Save failed:", e)
        return False


def write_entries(entries, path=PATH):
    """Rewrite the whole file from a list of entries (delete / clear-all).
    write_entries([]) empties the file. Returns True on success, False if
    read-only."""
    if not ensure_writable():
        print("Rewrite aborted: filesystem read-only")
        return False
    try:
        with open(path, "w") as f:
            for e in entries:
                f.write(e + ",\n")
        try:
            storage.sync()
        except Exception:
            pass
        return True
    except OSError as e:
        print("Rewrite failed:", e)
        return False
