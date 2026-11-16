import pytest
from PyQt6.QtGui import QColor

import ui_components as ui
from tray_app import charging_state


def solid_colors(pixmap):
    """Fully opaque colours: the coloured arc and the muted mic (neutral ink is 90% opaque)."""
    img = pixmap.toImage()
    return {img.pixelColor(x, y).name() for x in range(img.width()) for y in range(img.height())
            if img.pixelColor(x, y).alpha() == 255}


def max_alpha(pixmap):
    img = pixmap.toImage()
    return max(img.pixelColor(x, y).alpha() for x in range(img.width()) for y in range(img.height()))


RED, AMBER, GREEN = (c.name() for c in (ui.RED, ui.AMBER, ui.GREEN))
WHITE = QColor(255, 255, 255)


@pytest.mark.parametrize("level, charging, low, expected", [
    (80, False, 15, WHITE), (26, False, 15, WHITE), (25, False, 15, ui.AMBER), (15, False, 15, ui.RED),
    (5, True, 15, ui.GREEN), (100, True, 15, ui.GREEN),
    (11, False, 0, ui.AMBER), (10, False, 0, ui.RED),       # threshold never below 10
])
def test_arc_color(level, charging, low, expected):
    assert ui.arc_color(level, charging, low, WHITE) == expected


@pytest.mark.parametrize("kwargs, colors", [
    (dict(level=80), set()),
    (dict(level=22), {AMBER}),
    (dict(level=8), {RED}),
    (dict(level=40, charging=True), {GREEN}),
    (dict(level=8, active=False), set()),                   # asleep: no arc at all
    (dict(level=None), set()),
])
def test_ring_colors(qapp, kwargs, colors):
    assert solid_colors(ui.render_icon(64, low=15, **kwargs)) == colors


def test_inactive_icon_is_translucent(qapp):
    assert max_alpha(ui.render_icon(64, 60)) > 200
    assert max_alpha(ui.render_icon(64, 60, active=False)) < 128
    assert max_alpha(ui.render_icon(64, None)) < 128


@pytest.mark.parametrize("light, ink", [(False, "#ffffff"), (True, "#000000")])
def test_ink_follows_taskbar(qapp, light, ink):
    img = ui.render_icon(64, 100, light_taskbar=light).toImage()
    inks = {img.pixelColor(x, y).name() for x in range(64) for y in range(64) if img.pixelColor(x, y).alpha() > 200}
    assert inks == {ink}


def test_icon_has_every_tray_size(qapp):
    icon = ui.create_tray_icon(50, light_taskbar=False)
    assert {s.width() for s in icon.availableSizes()} == set(ui.ICON_SIZES)


def test_charging_state():
    base = {"battery": 50, "mode": "2.4G receiver"}
    assert charging_state({**base, "battery": None}) is None
    assert charging_state(base) == "Not charging"
    assert charging_state({**base, "mode": "USB cable"}) == "Charging"
    assert charging_state({"battery": 100, "mode": "USB cable"}) == "Fully charged"
