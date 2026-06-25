# webserver.py — WiFi sync for grippy.
#
# Serves /notes.txt over HTTP at http://grippy.local/notes.txt.
# Pure networking: this module owns NO display or backlight. The caller is
# responsible for the screen.
#
# ⚠️ BROWNOUT CONTRACT: the caller MUST turn the backlight OFF before calling
# start(). The backlight (~80 mA) plus the WiFi association spike together
# brown out the 130 mAh cell. start() never touches the screen, so screen-off
# ordering lives entirely in the caller. On failure start() returns False so
# the caller can turn the screen back on.
#
# ⚠️ HEAP: this serves a single static text file over a RAW socket on purpose.
# adafruit_httpserver costs ~25 KB to import, which on-device (display + app
# resident) left only ~12 KB free — too little for the lwIP stack to allocate
# packet buffers, so the board got an IP but answered ping/HTTP only slowly or
# not at all. socketpool/mdns/wifi are firmware built-ins (~0 heap), so the raw
# server keeps ~25 KB more free and the network stack stays healthy.

import time

_active = False
_listen = None
_mdns = None
_pool = None
_buf = bytearray(512)   # preallocated request scratch — no per-request alloc


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


def start():
    """WiFi up → serve notes.txt at grippy.local. Returns True on success.

    Caller MUST kill the backlight first (see brownout contract above)."""
    global _active, _listen, _mdns, _pool

    ssid, pw = _load_wifi_conf()
    if not ssid:
        print("Remote: no SSID in wifi.conf; aborting")
        return False

    import wifi
    import socketpool
    import mdns
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

        # mDNS (grippy.local) is a convenience — access by IP works without it.
        # mdns.Server can only be created ONCE per boot, so a failed/again start
        # must NOT abort the whole server (stop() deinits it; see below).
        try:
            _mdns = mdns.Server(wifi.radio)
            _mdns.hostname = "grippy"
            _mdns.advertise_service(service_type="_http", protocol="_tcp", port=80)
        except Exception as e:
            print("Remote: mDNS skipped:", e)
            _mdns = None

        _pool = socketpool.SocketPool(wifi.radio)
        sock = _pool.socket(_pool.AF_INET, _pool.SOCK_STREAM)
        try:
            sock.setsockopt(_pool.SOL_SOCKET, _pool.SO_REUSEADDR, 1)
        except Exception:
            pass
        sock.bind((ip, 80))
        sock.listen(1)
        sock.settimeout(0)            # non-blocking accept; poll() never stalls
        _listen = sock

        _active = True
        try:
            import gc
            print("Remote: mem_free", gc.mem_free())
        except Exception:
            pass
        print("Remote: http://grippy.local/notes.txt  (or http://%s/notes.txt)" % ip)
        return True
    except Exception as e:
        print("Remote: start failed:", e)
        stop()
        return False


def _read_notes():
    try:
        with open("/notes.txt") as f:
            return f.read()
    except OSError:
        return ""


def _handle(conn):
    """Read (and discard) the request, then send notes.txt. Best-effort."""
    try:
        conn.settimeout(1)
        try:
            conn.recv_into(_buf)      # drain the request line/headers
        except Exception:
            pass
        body = _read_notes().encode("utf-8")
        hdr = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n"
            "\r\n" % len(body)
        ).encode("utf-8")
        conn.send(hdr)
        if body:
            conn.send(body)
    except Exception as e:
        print("server send err:", e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def stop():
    """Tear down server + WiFi. Does NOT touch the screen."""
    global _active, _listen, _mdns, _pool
    _active = False
    if _listen is not None:
        try:
            _listen.close()
        except Exception:
            pass
        _listen = None
    if _mdns is not None:
        # Free the firmware mDNS instance — mdns.Server can only be created once
        # per boot, so without deinit() the NEXT start() throws "mDNS already
        # initialized" and WiFi Sync fails on every attempt after the first.
        try:
            _mdns.deinit()
        except Exception:
            pass
        _mdns = None
    _pool = None
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


def poll():
    """Accept + serve at most one pending request; no-op when not active."""
    if not (_active and _listen is not None):
        return
    try:
        conn, _addr = _listen.accept()
    except OSError:
        return                        # nothing pending (non-blocking timeout)
    except Exception as e:
        print("server accept err:", e)
        return
    _handle(conn)


def active():
    return _active
