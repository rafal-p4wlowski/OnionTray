from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap, QPolygonF

ICON_SIZE = 64
OUTLINE = QColor("#111111")
CHARGING_COLOR = QColor("#FACC15")
ASLEEP_COLOR = "#9CA3AF"


def get_battery_color(level, awake=True):
    if level is None or not awake: return ASLEEP_COLOR
    if level >= 60: return "#22C55E"
    if level >= 25: return "#F59E0B"
    return "#EF4444"


def _draw_big_bolt(painter):
    """Yellow lightning bolt filling the whole icon (charging over USB)."""
    bolt = QPolygonF([QPointF(x, y) for x, y in
                      ((44, 1), (7, 38), (28, 38), (19, 63), (57, 23), (36, 23), (52, 1))])
    painter.setPen(QPen(OUTLINE, 3, join=Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(CHARGING_COLOR)
    painter.drawPolygon(bolt)


def create_qicon(text, color_hex, charging=False):
    """Tray icon: the battery level as digits, or a lightning bolt while charging."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if charging:
        _draw_big_bolt(painter)
    else:
        font = QFont("Segoe UI")
        font.setBold(True)
        size = 48
        while size > 12:
            font.setPixelSize(size)
            if QFontMetrics(font).horizontalAdvance(text) <= ICON_SIZE - 2:
                break
            size -= 2
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(font)
        painter.setPen(QColor(color_hex))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)

    painter.end()
    return QIcon(pixmap)


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
