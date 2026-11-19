"""End-to-end tests: tray app + worker thread + protocol against the fake receiver."""
from PyQt6.QtWidgets import QSystemTrayIcon

from conftest import settle, wait_until

CLICK = QSystemTrayIcon.ActivationReason.Trigger


def pick(group, value):
    next(a for a in group.actions() if a.data() == value).trigger()


def checked(group):
    return [a.data() for a in group.actions() if a.isChecked()]


def test_startup_reads_battery(app):
    s = app.state
    assert (s["receiver"], s["awake"], s["battery"], s["mode"]) == (True, True, 80, "2.4G receiver")
    assert app.connection_info.text() == "Keyboard connected (2.4G receiver)"
    assert app.battery_info.text() == "Battery level: 80%"
    assert app.charging_info.text() == "Charging status: Not charging"
    assert "Keyboard battery: 80%" in app.tray.toolTip()


def test_battery_is_polled(app, receiver):
    receiver.battery = 42
    assert wait_until(lambda: app.state["battery"] == 42, timeout=4)


def test_left_click_opens_panel_and_refreshes(app, receiver):
    app.worker.poll_interval_s = 600
    app.worker.refresh_now()       # restart the wait with the long interval
    settle(0.3)
    receiver.battery = 55
    app.on_tray_activated(CLICK)
    assert wait_until(lambda: app.state["battery"] == 55, timeout=3)


def test_asleep_keeps_last_reading(app, receiver):
    receiver.awake = False
    assert wait_until(lambda: app.state["awake"] is False)
    assert app.state["battery"] == 80
    assert app.connection_info.text() == "Keyboard asleep / not responding"
    assert app.last_seen_info.text().startswith("Last reading: ")
    assert "Last reading" in app.tray.toolTip()
    receiver.awake = True
    assert wait_until(lambda: app.state["awake"] is True)


def test_usb_cable_means_charging(app, receiver):
    receiver.mode = 0
    assert wait_until(lambda: app.state["mode"] == "USB cable")
    assert app.charging_info.text() == "Charging status: Charging"
    receiver.battery = 100
    assert wait_until(lambda: app.charging_info.text() == "Charging status: Fully charged")


def test_receiver_unplugged(app, receiver):
    receiver.present = False
    assert wait_until(lambda: app.state["receiver"] is False)
    assert app.state["battery"] is None
    assert app.connection_info.text() == "Keyboard not found"
    receiver.present = True
    assert wait_until(lambda: app.state["battery"] == 80)


def test_bluetooth_fallback(app, receiver, bt_battery):
    receiver.present = False
    bt_battery["level"] = 64
    assert wait_until(lambda: app.state["mode"] == "Bluetooth" and app.state["battery"] == 64)
    assert app.connection_info.text() == "Keyboard connected (Bluetooth)"
    # Bluetooth link drops: the last reading stays, shown as asleep.
    bt_battery["level"] = None
    assert wait_until(lambda: app.state["awake"] is False)
    assert app.state["battery"] == 64


def test_bluetooth_check_can_be_disabled(app, receiver, bt_battery):
    app.bluetooth_act.trigger()
    assert app.worker.bluetooth is False
    receiver.present = False
    bt_battery["level"] = 64
    assert wait_until(lambda: app.state["receiver"] is False)
    calls = bt_battery["calls"]
    app.worker.refresh_now()
    settle(0.3)
    assert bt_battery["calls"] == calls and app.state["battery"] is None


def test_low_battery_warning_once(app, receiver):
    receiver.battery = 12
    assert wait_until(lambda: len(app.messages) == 1)
    receiver.battery = 11
    assert wait_until(lambda: app.state["battery"] == 11)
    settle(1.2)
    assert len(app.messages) == 1
    # Charged and drained again: warns again.
    receiver.battery = 40
    assert wait_until(lambda: app.state["battery"] == 40)
    receiver.battery = 14
    assert wait_until(lambda: len(app.messages) == 2)


def test_settings_menus(app):
    pick(app.poll_group, 300)
    assert app.worker.poll_interval_s == 300 and app.settings.poll_interval_s == 300
    assert checked(app.poll_group) == [300]
    pick(app.low_group, 0)
    assert app.settings.low_battery == 0 and checked(app.low_group) == [0]


def test_quit_stops_worker(app):
    app.on_quit()
    assert not app.worker.isRunning()


def test_release_unused_memory_is_safe(qapp):
    import tray_app
    tray_app.release_unused_memory()
