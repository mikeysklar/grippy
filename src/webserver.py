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

import time

_active = False
_server = None
_mdns = None


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
    global _active, _server, _mdns

    ssid, pw = _load_wifi_conf()
    if not ssid:
        print("Remote: no SSID in wifi.conf; aborting")
        return False

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
        _server = srv
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


def stop():
    """Tear down server + WiFi. Does NOT touch the screen."""
    global _active, _server, _mdns
    _active = False
    if _server is not None:
        try:
            _server.stop()
        except Exception:
            pass
        _server = None
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


def poll():
    """Service one round of HTTP requests; no-op when not active."""
    if _active and _server is not None:
        try:
            _server.poll()
        except Exception as e:
            print("server poll err:", e)


def active():
    return _active
