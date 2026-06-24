# boot.py — runs once at power-on / hard reset, before USB, the workflows, or
# code.py. The only reliable place to stop CircuitPython's built-in BLE WORKFLOW
# from ever advertising.
#
# The BLE workflow (file transfer / REPL over BLE) advertises as CIRCUITPYxxxx
# and re-advertises after every disconnect. With ble_hid.py also driving the one
# BLE radio, the two fight: the host saw the stray "CIRCUITPYxxxx" name, stayed
# connected after BLE was turned off (the workflow re-advertised, so macOS
# reconnected), and pairing was flaky. Disabling the workflow makes our HID code
# the sole owner of the adapter.
import supervisor
supervisor.runtime.ble_workflow = False
