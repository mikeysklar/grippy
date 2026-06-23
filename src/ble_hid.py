# ble_hid.py — BLE HID keyboard transport for grippy.
#
# Mechanism-only (like webserver.py / notes.py): owns the BLE radio, the HID
# GATT service, advertising, and the adafruit_hid Keyboard built on top of it.
# code.py owns the menu item, routes keystrokes through kbd(), and renders the
# connection status. No display / backlight here.
#
# Heavy imports (adafruit_ble) are done lazily in start() so the ~35 KB BLE
# stack is only paid for when the user actually turns BLE on.
#
# Needs `circup install adafruit_ble` (device-local lib, not in repo).
#
# FIRMWARE NOTE (ESP32-S3): BLE HID works on **CircuitPython 10.3.0-alpha.2+**.
#  - On 10.2.x it failed with "Unknown system firmware error: 519" (= NimBLE HCI
#    "Memory Capacity Exceeded") — a controller OOM when advertising from inside
#    code.py. Fixed upstream by adafruit/circuitpython PR #11036 (in 10.3.0+).
#  - On 10.3.x's NimBLE 6.0.1 the "advertise forever" default (timeout None/0) is
#    rejected with "Invalid BLE parameter", and the advertising duration is
#    capped (~60-80s). So we advertise in finite 60s windows re-armed by poll()
#    (see _ADV_TIMEOUT below). This is the key to making it work on 10.3.x.
import gc
import time

_KEYBOARD_APPEARANCE = 961   # 0x03C1 — GAP "HID Keyboard", so hosts pair it as one
# Advertise for a finite window, re-armed by poll(). On NimBLE 6.0.1 (CP 10.3.x)
# the "advertise forever" default (timeout None / 0) is rejected with "Invalid
# BLE parameter", and the duration is capped (~60-80s; 60 works, 90 fails), so
# we advertise in 60s windows and poll() re-arms. Stays discoverable until a
# host connects.
_ADV_TIMEOUT = 60
_last_adv = 0.0   # monotonic time of last start_advertising (poll() rate-limit)

_ble = None     # adafruit_ble.BLERadio
_hid = None     # HIDService
_adv = None     # ProvideServicesAdvertisement
_kbd = None     # adafruit_hid.keyboard.Keyboard over the BLE HID device
_di = None      # DeviceInfoService  (required by the HID-over-GATT profile)
_bat = None     # BatteryService     (required by the HID-over-GATT profile)

def start(name="grippy"):
    """Bring up BLE HID and begin advertising. Returns the Keyboard object."""
    global _ble, _hid, _adv, _kbd, _di, _bat, _last_adv
    import _bleio
    import adafruit_ble
    from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
    from adafruit_ble.services.standard.hid import HIDService
    from adafruit_ble.services.standard.device_info import DeviceInfoService
    from adafruit_hid.keyboard import Keyboard

    # IMPORTANT: do NOT toggle _bleio.adapter.enabled here. On this board,
    # flipping enabled right before advertising leaves the controller in a bad
    # state and start_advertising throws "Unknown system firmware error". The
    # radio is turned on once at boot (code.py), far from advertising time, so
    # here we just build the services and advertise an already-enabled adapter.
    _hid = HIDService()
    # HID-over-GATT mandates Device Information + Battery services; without them
    # macOS/iOS list the device but won't let you pair it as a keyboard.
    _di = DeviceInfoService(manufacturer="grippy", model_number="grippy")
    try:
        from adafruit_ble.services.standard import BatteryService
        _bat = BatteryService()
        _bat.level = 100
    except Exception:
        _bat = None

    _adv = ProvideServicesAdvertisement(_hid)
    _adv.appearance = _KEYBOARD_APPEARANCE   # advertise as a keyboard
    _adv.complete_name = name                # show a friendly name in the scan list
    _ble = adafruit_ble.BLERadio()
    _ble.name = name
    if _ble.connected:                 # drop any stale link before re-advertising
        for c in _ble.connections:
            c.disconnect()

    err = None                         # retry advertising through transient errors
    for _ in range(5):
        try:
            _ble.start_advertising(_adv, timeout=_ADV_TIMEOUT)
            err = None
            break
        except Exception as e:
            err = e
            time.sleep(0.3)
    if err:
        raise err
    _last_adv = time.monotonic()

    _kbd = Keyboard(_hid.devices)
    return _kbd

def connected():
    return bool(_ble and _ble.connected)

def poll():
    """Re-advertise if the host dropped or the ad window lapsed. Call from the
    main loop while active. Rate-limited so we don't hammer start_advertising
    during the brief connect window (advertising stopped, not yet connected) —
    the runaway pattern that exhausts NimBLE memory on builds without PR #11036."""
    global _last_adv
    if _ble and _adv and not _ble.connected and not _ble.advertising:
        now = time.monotonic()
        if now - _last_adv < 3.0:
            return
        _last_adv = now
        try:
            _ble.start_advertising(_adv, timeout=_ADV_TIMEOUT)
        except Exception:
            pass

def kbd():
    """The active Keyboard, or None. Returns None unless a host is connected so
    callers never push reports into the void (which can raise on _bleio)."""
    return _kbd if connected() else None

def stop():
    """Tear down advertising + connection and turn the BLE radio fully off."""
    global _ble, _hid, _adv, _kbd, _di, _bat
    try:
        if _ble:
            if _ble.advertising:
                _ble.stop_advertising()
            for c in tuple(_ble.connections or ()):
                c.disconnect()
    except Exception:
        pass
    try:
        import _bleio                       # make sure nothing is left
        if _bleio.adapter.advertising:      # advertising (no enabled toggle, so
            _bleio.adapter.stop_advertising()  # USB isn't reset on this board)
    except Exception:
        pass
    _kbd = _adv = _hid = _di = _bat = None
    gc.collect()
