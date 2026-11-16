"""Tray icon: a battery ring around a device glyph.

The presentation follows HaloBattery (https://github.com/HeyOkay/HaloBattery, MIT):
a dim track with the charge arc filling clockwise from the top, the glyph in the
taskbar colour (white on a dark taskbar, black on a light one), the arc amber close
to the low-battery threshold, red at or below it and green while charging. With no
reading (asleep, off, not found) the icon is translucent and has no arc.

The glyph is Lucide "keyboard" (https://lucide.dev, ISC, see licenses/), redrawn
from its 24x24 SVG path so no SVG module has to be bundled.
"""
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64)   # tray sizes from 100% to 400% scaling
UNIT = 64.0                                 # the icon is designed on a 64x64 grid

RING_RADIUS = 29.5                          # centre of the ring stroke
RING_WIDTH = 4.0                            # one pixel at the 16 px tray size
NEUTRAL_OPACITY = 0.9                       # like the softer Windows tray ink
TRACK_OPACITY = (70 / 255, 45 / 255)        # track: (active, inactive)
INACTIVE_OPACITY = 110 / 255

RED = QColor(232, 17, 35)
AMBER = QColor(255, 185, 0)
GREEN = QColor(16, 196, 80)

GLYPH_FIT = 0.46                            # glyph size relative to the Lucide 24-unit grid at 0.5


def taskbar_is_light():
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "SystemUsesLightTheme")[0] == 1
    except OSError:
        return False


def arc_color(level, charging, low, fg):
    """Green while charging, red at or below the threshold, amber 10 points above it."""
    if charging:
        return GREEN
    threshold = max(low or 0, 10)
    if level is not None and level <= threshold:
        return RED
    if level is not None and level <= threshold + 10:
        return AMBER
    return fg


def _keyboard_path():
    """Lucide keyboard: rounded body, two rows of key dots and a space bar."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 4, 20, 16), 2, 2)
    for x, y in ((6, 8), (10, 8), (14, 8), (18, 8), (8, 12), (12, 12), (16, 12)):
        path.moveTo(x, y)
        path.lineTo(x + 0.01, y)            # round caps turn these into dots
    path.moveTo(7, 16)
    path.lineTo(17, 16)
    return path


GLYPH = _keyboard_path()


def _draw_glyph(painter, path, color, opacity):
    scale = 4 * GLYPH_FIT                   # 24 Lucide units -> 64-unit icon grid
    painter.save()
    painter.translate(32, 32)
    painter.scale(scale, scale)
    painter.translate(-12, -12)
    painter.setOpacity(opacity)
    painter.setPen(QPen(color, RING_WIDTH / scale, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()


def render_icon(size, level, charging=False, active=True, low=20, light_taskbar=False):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / UNIT, size / UNIT)

    fg = QColor(0, 0, 0) if light_taskbar else QColor(255, 255, 255)
    active = active and level is not None
    ring = QRectF(32 - RING_RADIUS, 32 - RING_RADIUS, 2 * RING_RADIUS, 2 * RING_RADIUS)

    # track
    painter.setOpacity(NEUTRAL_OPACITY * TRACK_OPACITY[0 if active else 1])
    painter.setPen(QPen(fg, RING_WIDTH))
    painter.drawEllipse(ring)

    # charge arc
    if active and level > 0:
        color = arc_color(level, charging, low, fg)
        painter.setOpacity(NEUTRAL_OPACITY if color == fg else 1.0)
        pen = QPen(color, RING_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        if level >= 100:
            painter.drawEllipse(ring)
        else:
            span = 360 * max(level, 2) / 100
            painter.drawArc(ring, 90 * 16, -round(span * 16))

    _draw_glyph(painter, GLYPH, fg, NEUTRAL_OPACITY * (1.0 if active else INACTIVE_OPACITY))
    painter.end()
    return pixmap


def create_tray_icon(level, charging=False, active=True, low=20, light_taskbar=None):
    """QIcon with every tray size drawn separately, so the 1 px ring stays sharp."""
    if light_taskbar is None:
        light_taskbar = taskbar_is_light()
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(render_icon(size, level, charging, active, low, light_taskbar))
    return icon


# --- STYLESHEET ---
DARK_MENU_STYLE = """
QMenu {
    background-color: #1e1e1e;
    color: #e0e0e0;
    border: 1px solid #3d3d3d;
    padding: 4px;
    font-family: 'Segoe UI', Arial;
    font-size: 13px;
}
QMenu::item {
    background-color: transparent;
    padding: 6px 30px 6px 15px;
    border-radius: 4px;
    margin: 1px 4px;
}
QMenu::item:selected {
    background-color: #3d3d3d;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #717171;
}
QMenu::separator {
    height: 1px;
    background: #3d3d3d;
    margin: 4px 8px;
}
"""
