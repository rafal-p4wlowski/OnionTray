from PyQt6.QtGui import QColor

from tray_app import charging_state
from ui_components import ASLEEP_COLOR, create_qicon, get_battery_color


def pixel_colors(icon):
    img = icon.pixmap(64, 64).toImage()
    return {QColor(img.pixel(x, y)).name() for x in range(0, 64, 2) for y in range(0, 64, 2)
            if QColor.fromRgba(img.pixel(x, y)).alpha() > 200}


def test_battery_colors():
    assert get_battery_color(None) == ASLEEP_COLOR
    assert get_battery_color(80, awake=False) == ASLEEP_COLOR
    assert get_battery_color(80) == "#22C55E"
    assert get_battery_color(40) == "#F59E0B"
    assert get_battery_color(10) == "#EF4444"


def test_icons_render(qapp):
    assert not create_qicon("100", "#22C55E").isNull()
    assert "#22c55e" in pixel_colors(create_qicon("88", "#22C55E"))
    assert "#facc15" in pixel_colors(create_qicon("50", "#22C55E", charging=True))


def test_charging_state():
    base = {"battery": 50, "mode": "2.4G receiver"}
    assert charging_state({**base, "battery": None}) is None
    assert charging_state(base) == "Not charging"
    assert charging_state({**base, "mode": "USB cable"}) == "Charging"
    assert charging_state({"battery": 100, "mode": "USB cable"}) == "Fully charged"
