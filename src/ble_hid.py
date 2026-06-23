# ble_hid.py — BLE HID keyboard transport for grippy.
#
# Mechanism-only (like webserver.py / notes.py): owns the BLE radio, the HID
# GATT service, advertising, and the adafruit_hid Keyboard built on top of it.
# code.py owns the menu item, routes keystrokes through kbd(), and renders the
# connection status. No display / backlight here.
#
# Needs `circup install adafruit_ble` (device-local lib, not in repo).
#
# ── Hard-won ESP32-S3 / CP 10.3.0-alpha.2 lessons ────────────────────────────
#  * BUILD THE GATT ONCE. adafruit_ble Services register characteristics on the
#    local GATT and there's no clean teardown on _bleio. Recreating HIDService on
#    every enable piles up duplicate services and HANGS the re-enable. So _build()
#    runs a single time and start()/stop() just flip advertising + an _active flag.
#  * NEVER disconnect(). connection.disconnect() hard-faults the board (CP
#    #9708/#10849) — that was the "freeze" on toggling BLE off. We stop
#    advertising and let the host drop the link.
#  * NEVER toggle _bleio.adapter.enabled near advertising (firmware error / USB
#    reset). The radio is enabled once at boot (code.py).
#  * FINITE advertising timeout. NimBLE 6.0.1 rejects "advertise forever"
#    (timeout None/0) with "Invalid BLE parameter" and caps the duration
#    (~60-80s; 60 works, 90 fails). We advertise in 60s windows re-armed by poll().
#  * A stale on-device bond blocks fresh pairing ("stuck on pairing" on macOS).
#    erase_pairing() clears it. (On 10.2.x advertising also hit error 519 = NimBLE
#    HCI "Memory Capacity Exceeded"; fixed upstream by PR #11036 in 10.3.0+.)
import gc
import time

_KEYBOARD_APPEARANCE = 961   # 0x03C1 — GAP "HID Keyboard", so hosts pair it as one
_ADV_TIMEOUT = 60            # finite advertising window (s); poll() re-arms it

_ble = None     # adafruit_ble.BLERadio          (built once)
_hid = None     # HIDService
_adv = None     # ProvideServicesAdvertisement
_kbd = None     # adafruit_hid.keyboard.Keyboard over the BLE HID device
_di  = None     # DeviceInfoService  (required by the HID-over-GATT profile)
_bat = None     # BatteryService     (required by the HID-over-GATT profile)
_active   = False   # True while BLE output is turned on from the menu
_last_adv = 0.0     # monotonic time of last start_advertising (poll() rate-limit)

def _build():
    """Create the BLE radio + HID GATT + Keyboard ONCE and cache them. Recreating
    services churns the GATT (no clean removal on _bleio) and hangs re-enable."""
    global _ble, _hid, _adv, _kbd, _di, _bat
    if _ble is not None:
        return
    import adafruit_ble
    from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
    from adafruit_ble.services.standard.hid import HIDService
    from adafruit_ble.services.standard.device_info import DeviceInfoService
    from adafruit_hid.keyboard import Keyboard

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
    _adv.complete_name = "grippy"
    _ble = adafruit_ble.BLERadio()
    _ble.name = "grippy"
    _kbd = Keyboard(_hid.devices)

def _advertise():
    if _ble.advertising or _ble.connected:
        return
    err = None
    for _ in range(5):
        try:
            _ble.start_advertising(_adv, timeout=_ADV_TIMEOUT)
            return
        except Exception as e:
            err = e
            time.sleep(0.3)
    if err:
        raise err

def start(name="grippy"):
    """Turn BLE output on: build (once), advertise, and route keystrokes."""
    global _active, _last_adv
    _build()
    _active = True
    _advertise()
    _last_adv = time.monotonic()
    return _kbd

def stop():
    """Turn BLE output off: stop advertising and stop routing keystrokes. Keep
    the GATT/radio built (re-enable just re-advertises) and never disconnect."""
    global _active
    _active = False
    try:
        if _ble and _ble.advertising:
            _ble.stop_advertising()
    except Exception:
        pass
    gc.collect()

def connected():
    return bool(_active and _ble and _ble.connected)

def kbd():
    """The active Keyboard, or None unless BLE is on AND a host is connected."""
    return _kbd if connected() else None

def poll():
    """Re-advertise if the ad window lapsed / host dropped. Call from the main
    loop while active. Rate-limited (>=3s) so it can't hammer start_advertising
    during the connect window (the runaway pattern PR #11036 addresses)."""
    global _last_adv
    if _active and _ble and not _ble.connected and not _ble.advertising:
        now = time.monotonic()
        if now - _last_adv < 3.0:
            return
        _last_adv = now
        try:
            _ble.start_advertising(_adv, timeout=_ADV_TIMEOUT)
        except Exception:
            pass

def erase_pairing():
    """Clear stored bonds so a host can pair fresh (recovers macOS 'stuck on
    pairing' when the board holds a stale bond). Safe to call with BLE off."""
    try:
        import _bleio
        _bleio.adapter.erase_bonding()
        return True
    except Exception:
        return False
