import os
import sys
import time

# Must happen before anything imports Qt or the HID binding.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(TESTS_DIR))
sys.path.insert(0, TESTS_DIR)

import fake_hid  # noqa: E402

sys.modules["hid"] = fake_hid

import pytest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


class FakeSettings:
    """Keeps tests away from the real registry."""
    poll_interval_s = 1
    low_battery = 15
    bluetooth = True


def wait_until(condition, timeout=5.0):
    """Process Qt events until condition() is true. Returns whether it became true."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return condition()


def settle(seconds=0.5):
    """Process events for a while (for checks that something did NOT happen)."""
    wait_until(lambda: False, seconds)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def receiver():
    fake_hid.RECEIVER.reset()
    yield fake_hid.RECEIVER
    fake_hid.RECEIVER.reset()


@pytest.fixture
def bt_battery(monkeypatch):
    """Simulated Windows Bluetooth battery level (None = not connected over BT)."""
    import keyboard_logic

    box = {"level": None, "calls": 0}

    def fake(*_):
        box["calls"] += 1
        return box["level"]

    monkeypatch.setattr(keyboard_logic, "read_bluetooth_battery", fake)
    return box


@pytest.fixture
def app(qapp, receiver, bt_battery, monkeypatch):
    import app_settings
    import keyboard_logic
    import tray_app

    monkeypatch.setattr(app_settings, "is_autostart_enabled", lambda: False)
    tray = tray_app.KeyboardApp(keyboard_logic, FakeSettings())
    tray.messages = []
    monkeypatch.setattr(tray.tray, "showMessage", lambda *a: tray.messages.append(a))
    assert wait_until(lambda: tray.state["battery"] is not None), "first poll did not finish"
    yield tray
    tray.on_quit()
