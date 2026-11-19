"""Keyboard panel: every setting of the vendor web driver in one window.

Opened by a left click on the tray icon or "Keyboard panel..." in the tray menu.
All device I/O runs on one background thread (DeviceBridge), in order, and
holds keyboard_logic.IO_LOCK, so it never overlaps the battery poll.
"""
import logging
import queue
import threading
import time

from PyQt6.QtCore import QObject, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSizePolicy, QSlider, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

import app_settings
import i18n
import keyboard_config as kc
import keyboard_defaults
import keyboard_layout as layout
import keyboard_logic as kl
from i18n import tr

log = logging.getLogger("oniontray")

WRITE_DEBOUNCE_MS = 300
SWATCHES = ("#000000", "#0000ff", "#00ffff", "#00ff00", "#ffff00", "#ff0000", "#ff00ff", "#ffffff")

ACCENT = "#2f6fff"
PANEL_STYLE = f"""
QWidget {{ background: #1b1c1f; color: #e0e0e0; font-family: 'Segoe UI', Arial; font-size: 13px; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px; border: 1px solid #5a5e66; background: #24262b; }}
QCheckBox::indicator {{ border-radius: 3px; }}
QRadioButton::indicator {{ border-radius: 7px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: #3a3d44; }}
QTabWidget::pane {{ border: 1px solid #2c2e33; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 18px; color: #a0a0a0; border: none; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QPushButton {{ background: #2a2c31; border: 1px solid #3a3d44; border-radius: 5px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QPushButton:disabled {{ color: #666; border-color: #2c2e33; }}
QPushButton#danger {{ background: #6b1f24; border-color: #8a2a30; }}
QPushButton#palette {{ padding: 5px 8px; border-color: #24407f; }}
QLineEdit, QSpinBox, QComboBox, QListWidget, QTableWidget {{
    background: #24262b; border: 1px solid #3a3d44; border-radius: 4px; padding: 3px; }}
QHeaderView::section {{ background: #2a2c31; border: none; padding: 4px; }}
QSlider::groove:horizontal {{ height: 4px; background: #3a3d44; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 14px; margin: -6px 0; border-radius: 7px; }}
QLabel#title {{ font-size: 18px; font-weight: 600; }}
QLabel#muted {{ color: #8a8d93; }}
QLabel#error {{ color: #ff6b6b; }}
QFrame#card {{ background: #222428; border-radius: 6px; }}
"""


# ------------------------------------------------------------------ device I/O

class DeviceBridge(QObject):
    """Runs jobs `fn(session)` one at a time on a background thread."""

    finished = pyqtSignal(object, object, object)    # callback, result, error text
    busy_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._jobs = queue.Queue()
        self._pending = 0
        self.finished.connect(self._deliver)
        self._thread = threading.Thread(target=self._loop, name="kbd-config", daemon=True)
        self._thread.start()

    def submit(self, fn, callback=None):
        self._pending += 1
        if self._pending == 1:
            self.busy_changed.emit(True)
        self._jobs.put((fn, callback))

    def _loop(self):
        while (job := self._jobs.get()) is not None:
            fn, callback = job
            try:
                with kl.open_session() as session:
                    result = fn(session)
                self.finished.emit(callback, result, None)
            except Exception as e:      # KeyboardError, ValueError from encoders, ...
                log.warning("Keyboard config job failed: %s", e)
                self.finished.emit(callback, None, str(e))

    def _deliver(self, callback, result, error):
        self._pending -= 1
        if self._pending == 0:
            self.busy_changed.emit(False)
        if callback is not None:
            callback(result, error)

    def shutdown(self):
        """Finish the queued writes, then stop the thread."""
        self._jobs.put(None)
        self._thread.join(timeout=30)


# ------------------------------------------------------------- keyboard view

class KeyboardView(QWidget):
    """The keyboard drawn from keyboard_layout.GEOMETRY. Shows one label per key
    (and optionally a colour), highlights the selection and emits key_clicked."""

    key_clicked = pyqtSignal(int)
    key_right_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels = {}
        self.colors = None           # value -> QColor when showing per-key colours
        self.selected = set()
        self.disabled = set()
        self.marked = set()          # keys whose action differs from the default
        self.setMinimumSize(720, 210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMouseTracking(True)
        self._hover = None

    def sizeHint(self):
        return QSize(1000, 290)

    def _unit(self):
        return min(self.width() / layout.LAYOUT_SIZE[0], self.height() / layout.LAYOUT_SIZE[1])

    def _rects(self):
        u = self._unit()
        ox = (self.width() - u * layout.LAYOUT_SIZE[0]) / 2
        for value, x, y, w, h in layout.GEOMETRY:
            yield value, QRectF(ox + x * u + 2, y * u + 2, w * u - 4, h * u - 4)

    def key_at(self, pos):
        for value, rect in self._rects():
            if rect.contains(pos):
                return value
        return None

    def mousePressEvent(self, event):
        value = self.key_at(event.position())
        if value is None or value in self.disabled:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.key_clicked.emit(value)
        elif event.button() == Qt.MouseButton.RightButton:
            self.key_right_clicked.emit(value)

    def mouseMoveEvent(self, event):
        value = self.key_at(event.position())
        if value != self._hover:
            self._hover = value
            self.setToolTip(layout.key_name(value) if value is not None else "")
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        u = self._unit()
        font = QFont("Segoe UI")
        font.setPixelSize(max(8, int(u * 0.22)))
        p.setFont(font)
        for value, rect in self._rects():
            fill = QColor("#262a33")
            if self.colors is not None:
                fill = self.colors.get(value, QColor("#000000"))
            elif value in self.disabled:
                fill = QColor("#3a3c40")
            border = QColor("#353a46")
            if value == self._hover and value not in self.disabled:
                border = QColor("#5b7fd6")
            if value in self.selected:
                border = QColor(ACCENT)
            p.setPen(QPen(border, 2 if value in self.selected else 1))
            p.setBrush(fill)
            p.drawRoundedRect(rect, 5, 5)
            text = self.labels.get(value) or layout.key_name(value)
            if self.colors is not None and fill.rgb() & 0xFFFFFF == 0:
                ink = QColor("#5a5d63")         # key turned off
            elif self.colors is not None:
                ink = QColor("#000") if fill.lightness() > 140 else QColor("#fff")
            elif value in self.disabled:
                ink = QColor("#77797d")
            elif value in self.marked:
                ink = QColor("#7fa7ff")
            else:
                ink = QColor("#e6e6e6")
            p.setPen(ink)
            box = rect.adjusted(3, 2, -3, -2)
            flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
            size = font.pixelSize()
            while size > 7:                     # shrink long labels until they fit the keycap
                f = QFont(font)
                f.setPixelSize(size)
                p.setFont(f)
                fits = p.boundingRect(box, flags, text)
                if fits.width() <= box.width() and fits.height() <= box.height():
                    break
                size -= 1
            p.drawText(box, flags, text)
            p.setFont(font)
        p.end()


# ---------------------------------------------------------------- helpers

def _card(title=None):
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(14, 12, 14, 12)
    if title:
        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight: 600;")
        box.addWidget(lbl)
    return frame, box


def _muted(text):
    lbl = QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    return lbl


def _flow_buttons(entries, handler, columns=6):
    """Grid of palette buttons. entries: (label, payload)."""
    w = QWidget()
    grid = QGridLayout(w)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(6)
    for i, (label, payload) in enumerate(entries):
        b = QPushButton(tr(label))
        b.setObjectName("palette")
        b.clicked.connect(lambda _=False, pl=payload: handler(pl))
        grid.addWidget(b, i // columns, i % columns)
    return w


def _scroll(widget):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(widget)
    return area


# Windows scan codes (as Qt reports them: extended keys | 0x100) -> HID usage,
# used when recording macros.
SCANCODE_TO_HID = {
    0x01: 41, 0x0C: 45, 0x0D: 46, 0x0E: 42, 0x0F: 43, 0x1A: 47, 0x1B: 48, 0x1C: 40, 0x1D: 224,
    0x27: 51, 0x28: 52, 0x29: 53, 0x2A: 225, 0x2B: 49, 0x33: 54, 0x34: 55, 0x35: 56, 0x36: 229,
    0x37: 85, 0x38: 226, 0x39: 44, 0x3A: 57, 0x45: 83, 0x145: 83, 0x46: 71, 0x47: 95, 0x48: 96,
    0x49: 97, 0x4A: 86, 0x4B: 92, 0x4C: 93, 0x4D: 94, 0x4E: 87, 0x4F: 89, 0x50: 90, 0x51: 91,
    0x52: 98, 0x53: 99, 0x56: 100, 0x57: 68, 0x58: 69,
    0x11C: 88, 0x11D: 228, 0x135: 84, 0x137: 70, 0x138: 230, 0x147: 74, 0x148: 82, 0x149: 75,
    0x14B: 80, 0x14D: 79, 0x14F: 77, 0x150: 81, 0x151: 78, 0x152: 73, 0x153: 76, 0x15B: 227,
    0x15C: 231, 0x15D: 101,
}
SCANCODE_TO_HID.update({0x02 + i: 30 + i for i in range(10)})                          # 1..0
SCANCODE_TO_HID.update(zip(range(0x10, 0x1A), (20, 26, 8, 21, 23, 28, 24, 12, 18, 19)))   # QWERTYUIOP
SCANCODE_TO_HID.update(zip(range(0x1E, 0x27), (4, 22, 7, 9, 10, 11, 13, 14, 15)))        # ASDFGHJKL
SCANCODE_TO_HID.update(zip(range(0x2C, 0x33), (29, 27, 6, 25, 5, 17, 16)))               # ZXCVBNM
SCANCODE_TO_HID.update({0x3B + i: 58 + i for i in range(10)})                          # F1..F10


# ------------------------------------------------------------------- panel

class KeyboardPanel(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.WindowType.Window)
        self.app = app                       # KeyboardApp (battery state, app settings)
        self.bridge = DeviceBridge()
        self.config = None
        self.macro_names = app_settings.MacroNames()
        self.led_memory = app_settings.LedColorMemory()
        self.setWindowTitle(tr("OnionTray - Keyboard"))
        self.setStyleSheet(PANEL_STYLE)
        self.resize(1180, 820)

        self._led_timer = QTimer(self, singleShot=True, interval=WRITE_DEBOUNCE_MS)
        self._led_timer.timeout.connect(self._write_led)
        self._colors_timer = QTimer(self, singleShot=True, interval=WRITE_DEBOUNCE_MS)
        self._colors_timer.timeout.connect(self._write_colors)
        self._settings_timer = QTimer(self, singleShot=True, interval=WRITE_DEBOUNCE_MS)
        self._settings_timer.timeout.connect(self._write_settings)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 10)
        root.addLayout(self._build_header())
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_keys_tab(), tr("Keys"))
        self.tabs.addTab(self._build_lighting_tab(), tr("Lighting"))
        self.tabs.addTab(self._build_macros_tab(), tr("Macros"))
        self.tabs.addTab(self._build_socd_tab(), "SOCD")
        self.tabs.addTab(self._build_settings_tab(), tr("Settings"))
        root.addWidget(self.tabs, 1)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        root.addWidget(self.status)

        self.bridge.busy_changed.connect(self._on_busy)
        self._set_enabled(False)

    # ------------------------------------------------------------- lifecycle
    def show_panel(self):
        self.sync_app_settings()
        self.update_battery(self.app.state)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.config is None:
            self.reload()

    def adopt(self, old):
        """Take over the state of a panel being replaced (language switch)."""
        self.restoreGeometry(old.saveGeometry())
        self.tabs.setCurrentIndex(old.tabs.currentIndex())
        self.config = old.config
        self._macros_dirty = old._macros_dirty
        if self.config is not None:
            self._set_enabled(True)
            self._refresh_all()

    def closeEvent(self, event):
        self._stop_recording()
        self._flush_pending()
        event.accept()

    def shutdown(self):
        self._flush_pending()
        self.bridge.shutdown()

    def _flush_pending(self):
        for timer, fn in ((self._led_timer, self._write_led), (self._colors_timer, self._write_colors),
                          (self._settings_timer, self._write_settings)):
            if timer.isActive():
                timer.stop()
                fn()

    def reload(self):
        self.status.setText(tr("Reading keyboard settings..."))
        self.bridge.submit(kc.read_config, self._on_loaded)

    def _on_loaded(self, result, error):
        if error:
            self.status.setText("")
            self.error_label.setText(
                tr("Cannot read the keyboard: {}.\nWake it up by pressing a key, then click Reload.").format(error))
            self.error_label.show()
            return
        self.error_label.hide()
        self.config = result
        self._apply_remembered_color()
        self._set_enabled(True)
        self._refresh_all()
        self.status.setText(tr("Settings read at {}").format(time.strftime('%H:%M:%S')))

    def _on_busy(self, busy):
        self.busy_label.setText(tr("Working...") if busy else "")

    def _set_enabled(self, enabled):
        for i in range(self.tabs.count()):
            page = self.tabs.widget(i)
            if page is not self.settings_page:
                page.setEnabled(enabled)
        self.keyboard_settings_card.setEnabled(enabled)

    def _done(self, what):
        def callback(_result, error):
            if error:
                self.status.setText(tr("{} failed: {}").format(what, error))
            else:
                self.status.setText(tr("{} saved at {}").format(what, time.strftime('%H:%M:%S')))
        return callback

    def _refresh_all(self):
        self.update_battery(self.app.state)
        self._refresh_keys()
        self._refresh_lighting()
        self._refresh_macros()
        self._refresh_socd()
        self._refresh_keyboard_settings()

    # ----------------------------------------------------------------- header
    def _build_header(self):
        row = QHBoxLayout()
        col = QVBoxLayout()
        self.title = QLabel("ALU104 Onionite")
        self.title.setObjectName("title")
        self.subtitle = _muted("")
        self.subtitle.setWordWrap(False)
        col.addWidget(self.title)
        col.addWidget(self.subtitle)
        row.addLayout(col)
        row.addStretch(1)
        self.error_label = QLabel("")
        self.error_label.setObjectName("error")
        self.error_label.hide()
        row.addWidget(self.error_label)
        self.busy_label = _muted("")
        row.addWidget(self.busy_label)
        reload_btn = QPushButton(tr("Reload"))
        reload_btn.clicked.connect(self._on_reload_clicked)
        row.addWidget(reload_btn)
        return row

    def _on_reload_clicked(self):
        self.app.worker.refresh_now()
        self.reload()

    def update_battery(self, state):
        """Called by the tray app whenever the battery state changes."""
        bat = state.get("battery")
        parts = [tr(state.get("mode") or "not connected")]
        if bat is not None:
            parts.append(tr("battery {}%").format(bat))
        if not state.get("awake") and bat is not None:
            parts.append(tr("asleep"))
        if self.config:
            parts.append(tr("firmware {}").format(self.config.info.firmware))
        self.subtitle.setText(" · ".join(parts))

    # =================================================================== KEYS
    def _build_keys_tab(self):
        page = QWidget()
        box = QVBoxLayout(page)
        top = QHBoxLayout()
        self.layer_group = QButtonGroup(page)
        for i, (layer, text) in enumerate(((kc.LAYER_NORMAL, tr("Normal layer")), (kc.LAYER_FN, tr("Fn layer")))):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("layer", layer)
            self.layer_group.addButton(b, i)
            top.addWidget(b)
        self.layer_group.button(0).setChecked(True)
        self.layer_group.idToggled.connect(lambda _id, on: on and self._refresh_keys())
        top.addStretch(1)
        self.selected_key_label = _muted(tr("Click a key, then pick what it should do."))
        top.addWidget(self.selected_key_label)
        restore = QPushButton(tr("Restore key"))
        restore.clicked.connect(self._restore_key)
        top.addWidget(restore)
        reset_layer = QPushButton(tr("Restore layer"))
        reset_layer.clicked.connect(self._restore_layer)
        top.addWidget(reset_layer)
        box.addLayout(top)

        self.keys_view = KeyboardView()
        self.keys_view.key_clicked.connect(self._select_key)
        box.addWidget(self.keys_view, 3)

        self.palette_tabs = QTabWidget()
        for title, entries in layout.PALETTES:
            self.palette_tabs.addTab(_scroll(_flow_buttons(entries, self._assign_action, 8)), tr(title))
        macro_page = QWidget()
        mbox = QVBoxLayout(macro_page)
        mrow = QHBoxLayout()
        self.assign_macro_combo = QComboBox()
        self.assign_mode_combo = QComboBox()
        for mode, text in kc.MACRO_MODES:
            self.assign_mode_combo.addItem(tr(text), mode)
        self.assign_count = QSpinBox()
        self.assign_count.setRange(1, 255)
        self.assign_mode_combo.currentIndexChanged.connect(
            lambda: self.assign_count.setEnabled(self.assign_mode_combo.currentData() == kc.MACRO_REPEAT))
        self.assign_count.setEnabled(False)
        assign = QPushButton(tr("Assign macro"))
        assign.clicked.connect(self._assign_macro)
        for w in (QLabel(tr("Macro")), self.assign_macro_combo, QLabel(tr("Playback")), self.assign_mode_combo,
                  QLabel(tr("Times")), self.assign_count, assign):
            mrow.addWidget(w)
        mrow.addStretch(1)
        mbox.addLayout(mrow)
        mbox.addWidget(_muted(tr("Record macros on the Macros tab first.")))
        mbox.addStretch(1)
        self.palette_tabs.addTab(macro_page, tr("Macros"))
        box.addWidget(self.palette_tabs, 2)
        self.selected_key = None
        return page

    @property
    def current_layer(self):
        return self.layer_group.checkedButton().property("layer")

    @staticmethod
    def _layer_defaults(layer):
        return keyboard_defaults.LAYERS[layer]

    @classmethod
    def _key_default(cls, layer, value):
        """Factory action of one key. A key that is half of a factory SOCD pair
        gets its plain key back (SOCD needs both keys)."""
        action = cls._layer_defaults(layer)[value]
        if action.page == kc.PAGE_SOCD and value in layout.KEYS:
            return layout.default_action(value)
        return action

    def _apply_remembered_color(self):
        """The keyboard always reports FD FD FD as the colour; show the colour
        that was last set from this program instead."""
        remembered = self.led_memory.color()
        if remembered is not None and tuple(self.config.led.color) == kc.REPORTED_COLOR:
            self.config.led.color = remembered

    def _refresh_keys(self):
        if not self.config:
            return
        layer = self.current_layer
        actions = self.config.layers[layer]
        defaults = self._layer_defaults(layer)
        names = self.macro_names.all()
        self.keys_view.labels = {v: layout.action_label(actions[v], names) or layout.key_name(v)
                                 for v in layout.KEYS}
        self.keys_view.marked = {v for v in layout.KEYS if actions[v] != defaults[v]}
        locked = set(layout.FN_LOCKED) if layer == kc.LAYER_FN else set()
        self.keys_view.disabled = locked | {layout.FN_KEY}
        if self.selected_key in self.keys_view.disabled:
            self.selected_key = None
        self.keys_view.selected = {self.selected_key} if self.selected_key is not None else set()
        self.keys_view.update()
        self._update_selected_label()

    def _update_selected_label(self):
        if self.selected_key is None:
            self.selected_key_label.setText(tr("Click a key, then pick what it should do."))
            return
        act = self.config.layers[self.current_layer][self.selected_key]
        now = layout.action_label(act, self.macro_names.all()) or tr("default")
        self.selected_key_label.setText(f"{layout.key_name(self.selected_key)}  →  {now}")

    def _select_key(self, value):
        self.selected_key = value
        self.keys_view.selected = {value}
        self.keys_view.update()
        self._update_selected_label()

    def _assign_action(self, action):
        if self.selected_key is None:
            self.status.setText(tr("Select a key on the keyboard first."))
            return
        self._set_slot(self.current_layer, self.selected_key, action)

    def _assign_macro(self):
        mid = self.assign_macro_combo.currentData()
        if mid is None:
            self.status.setText(tr("There are no macros yet."))
            return
        mode = self.assign_mode_combo.currentData()
        self._assign_action(kc.KeyAction.macro(mid, mode, self.assign_count.value()))

    def _restore_key(self):
        if self.selected_key is not None:
            layer = self.current_layer
            self._set_slot(layer, self.selected_key, self._key_default(layer, self.selected_key))

    def _restore_layer(self):
        layer = self.current_layer
        name = tr("normal") if layer == kc.LAYER_NORMAL else "Fn"
        if QMessageBox.question(self, tr("Restore layer"),
                                tr("Restore every key of the {} layer to its default?").format(name)) != QMessageBox.StandardButton.Yes:
            return
        actions = list(self._layer_defaults(layer))
        self._write_layer(layer, actions)

    def _set_slot(self, layer, value, action):
        actions = list(self.config.layers[layer])
        old = actions[value]
        if old.page == kc.PAGE_SOCD and layer == kc.LAYER_NORMAL:
            # The partner key of a SOCD pair goes back to its default as well.
            for v, act in enumerate(actions):
                if v != value and act == old:
                    actions[v] = self._key_default(layer, v)
        actions[value] = action
        self._write_layer(layer, actions)

    def _write_layer(self, layer, actions):
        self.config.layers[layer] = actions
        self._refresh_keys()
        self._refresh_socd()
        self.bridge.submit(lambda s: kc.write_layer(s, layer, actions), self._done(tr("Key assignment")))

    # =============================================================== LIGHTING
    def _build_lighting_tab(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        self.color_view = KeyboardView()
        self.color_view.colors = {}
        self.color_view.key_clicked.connect(self._paint_key)
        self.color_view.key_right_clicked.connect(self._key_off)
        self.color_view.hide()
        outer.addWidget(self.color_view, 3)

        row = QHBoxLayout()
        outer.addLayout(row, 2)

        effects, ebox = _card()
        head = QHBoxLayout()
        title = QLabel(tr("Lighting effects"))
        title.setStyleSheet("font-weight: 600;")
        head.addWidget(title)
        head.addStretch(1)
        self.led_on = QCheckBox(tr("Lights on"))
        self.led_on.toggled.connect(self._on_led_toggle)
        head.addWidget(self.led_on)
        ebox.addLayout(head)
        grid = QGridLayout()
        grid.setSpacing(6)
        self.mode_group = QButtonGroup(page)
        for i, mode in enumerate(kc.LIGHTING_MODES):
            b = QPushButton(tr(mode.name))
            b.setCheckable(True)
            self.mode_group.addButton(b, mode.id)
            grid.addWidget(b, i // 3, i % 3)
        self.mode_group.idClicked.connect(self._on_mode_clicked)
        ebox.addLayout(grid)
        ebox.addStretch(1)
        row.addWidget(effects, 3)

        edit, xbox = _card(tr("Effect"))
        xbox.addWidget(QLabel(tr("Colour mode")))
        crow = QHBoxLayout()
        self.single_color_radio = QRadioButton(tr("Single colour"))
        self.rainbow_radio = QRadioButton(tr("RGB (rainbow)"))
        self.single_color_radio.toggled.connect(self._on_color_mode)
        crow.addWidget(self.single_color_radio)
        crow.addWidget(self.rainbow_radio)
        crow.addStretch(1)
        xbox.addLayout(crow)
        self.brightness_slider = self._slider_row(xbox, tr("Brightness"), kc.BRIGHTNESS_RANGE)
        self.brightness_slider.valueChanged.connect(lambda v: self._led_change(brightness=v))
        self.speed_slider = self._slider_row(xbox, tr("Speed"), kc.SPEED_RANGE)
        self.speed_slider.valueChanged.connect(lambda v: self._led_change(speed=v))
        drow = QHBoxLayout()
        self.direction_label = QLabel(tr("Direction"))
        drow.addWidget(self.direction_label)
        self.direction_combo = QComboBox()
        self.direction_combo.activated.connect(lambda: self._led_change(direction=self.direction_combo.currentData()))
        drow.addWidget(self.direction_combo, 1)
        xbox.addLayout(drow)
        xbox.addStretch(1)
        row.addWidget(edit, 2)

        color, cbox = _card(tr("Colour"))
        hrow = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(7)
        self.hex_edit.editingFinished.connect(self._on_hex)
        self.color_button = QPushButton(tr("Pick..."))
        self.color_button.clicked.connect(self._pick_color)
        hrow.addWidget(QLabel("HEX"))
        hrow.addWidget(self.hex_edit, 1)
        hrow.addWidget(self.color_button)
        cbox.addLayout(hrow)
        srow = QHBoxLayout()
        for hexcolor in SWATCHES:
            sw = QPushButton()
            sw.setFixedSize(26, 26)
            sw.setStyleSheet(f"background: {hexcolor}; border: 1px solid #555; border-radius: 4px;")
            sw.clicked.connect(lambda _=False, c=hexcolor: self._set_color(QColor(c)))
            srow.addWidget(sw)
        srow.addStretch(1)
        cbox.addLayout(srow)
        self.custom_hint = _muted(tr("Custom mode: click keys on the keyboard above to paint them with this "
                                     "colour. Right-click a key to turn it off."))
        cbox.addWidget(self.custom_hint)
        self.custom_tools = QWidget()
        tools = QGridLayout(self.custom_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        self.eraser_btn = QPushButton(tr("Eraser (turn keys off)"))
        self.eraser_btn.setCheckable(True)
        self.fill_all_btn = QPushButton(tr("Fill all keys"))
        self.fill_all_btn.clicked.connect(self._fill_all)
        self.all_off_btn = QPushButton(tr("Turn all keys off"))
        self.all_off_btn.clicked.connect(lambda: self._fill_all(off=True))
        tools.addWidget(self.eraser_btn, 0, 0, 1, 2)
        tools.addWidget(self.fill_all_btn, 1, 0)
        tools.addWidget(self.all_off_btn, 1, 1)
        cbox.addWidget(self.custom_tools)
        cbox.addStretch(1)
        row.addWidget(color, 2)
        self.current_color = QColor(255, 255, 255)
        self._loading_led = False
        self._last_mode = 0
        return page

    @staticmethod
    def _slider_row(box, title, rng):
        box.addWidget(QLabel(title))
        r = QHBoxLayout()
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(*rng)
        s.setPageStep(1)
        val = QLabel(str(rng[1]))
        s.valueChanged.connect(lambda v: val.setText(str(v)))
        r.addWidget(s, 1)
        r.addWidget(val)
        box.addLayout(r)
        return s

    def _refresh_lighting(self):
        if not self.config:
            return
        led = self.config.led
        self._loading_led = True
        try:
            self.led_on.setChecked(led.on)
            mode = kc.LIGHTING_BY_ID.get(led.mode)
            for b in self.mode_group.buttons():
                b.setChecked(mode is not None and self.mode_group.id(b) == mode.id)
            self.brightness_slider.setValue(led.brightness)
            self.speed_slider.setValue(led.speed)
            self.rainbow_radio.setChecked(led.rainbow)
            self.single_color_radio.setChecked(not led.rainbow)
            self._set_color_widgets(QColor(*led.color))
            self.direction_combo.clear()
            if mode:
                for d in mode.direction:
                    self.direction_combo.addItem(tr(kc.DIRECTION_NAMES[d]), d)
                idx = self.direction_combo.findData(led.direction)
                self.direction_combo.setCurrentIndex(max(idx, 0))
            self._update_lighting_enabled(mode)
            self._refresh_color_view()
        finally:
            self._loading_led = False

    def _update_lighting_enabled(self, mode):
        on = self.config.led.on
        for b in self.mode_group.buttons():
            b.setEnabled(on)
        has_mode = on and mode is not None
        self.brightness_slider.setEnabled(has_mode)
        self.speed_slider.setEnabled(has_mode and mode.speed)
        self.direction_combo.setVisible(bool(mode and mode.direction))
        self.direction_label.setVisible(bool(mode and mode.direction))
        custom = has_mode and mode.id == kc.LED_CUSTOM
        self.single_color_radio.setEnabled(has_mode and mode.color and not custom)
        self.rainbow_radio.setEnabled(has_mode and mode.color and not custom)
        self.color_view.setVisible(custom)
        self.custom_hint.setVisible(custom)
        self.custom_tools.setVisible(custom)

    def _refresh_color_view(self):
        self.color_view.colors = {v: QColor(*self.config.custom_colors[v]) for v in layout.KEYS}
        self.color_view.update()

    def _led_change(self, **fields):
        if self._loading_led or not self.config:
            return
        for k, v in fields.items():
            setattr(self.config.led, k, v)
        self._led_timer.start()

    def _write_led(self):
        led = kc.LedEffect(**vars(self.config.led))
        self.led_memory.set_color(led.color)
        self.bridge.submit(lambda s: kc.write_led(s, led), self._done(tr("Lighting")))

    def _on_led_toggle(self, on):
        if self._loading_led or not self.config:
            return
        led = self.config.led
        if on:
            led.mode = self._last_mode or 1
        else:
            self._last_mode = led.mode
            led.mode = kc.LED_OFF
        self._led_timer.start()
        self._refresh_lighting()

    def _on_mode_clicked(self, mode_id):
        mode = kc.LIGHTING_BY_ID[mode_id]
        led = self.config.led
        led.mode = mode_id
        if mode.direction and led.direction not in mode.direction:
            led.direction = mode.direction[0]
        if not mode.color:
            led.rainbow = True
        self._led_timer.start()
        self._refresh_lighting()

    def _on_color_mode(self):
        if not self._loading_led:
            self._led_change(rainbow=self.rainbow_radio.isChecked())

    def _set_color_widgets(self, color):
        self.current_color = color
        self.hex_edit.setText(color.name())
        self.color_button.setStyleSheet(
            f"background: {color.name()}; color: {'#000' if color.lightness() > 140 else '#fff'};")

    def _set_color(self, color):
        if not color.isValid():
            return
        self._set_color_widgets(color)
        if not self.config:
            return
        mode = kc.LIGHTING_BY_ID.get(self.config.led.mode)
        if mode and mode.id == kc.LED_CUSTOM:
            return                          # in custom mode the colour is the paint brush
        if mode and mode.color:
            self._loading_led = True
            self.single_color_radio.setChecked(True)
            self._loading_led = False
            self._led_change(color=(color.red(), color.green(), color.blue()), rainbow=False)

    def _pick_color(self):
        self._set_color(QColorDialog.getColor(self.current_color, self, tr("Lighting colour")))

    def _on_hex(self):
        c = QColor(self.hex_edit.text().strip())
        if c.isValid() and c != self.current_color:
            self._set_color(c)

    def _paint_key(self, value):
        if self.eraser_btn.isChecked():
            self._key_off(value)
            return
        c = self.current_color
        self.config.custom_colors[value] = (c.red(), c.green(), c.blue())
        self._refresh_color_view()
        self._colors_timer.start()

    def _key_off(self, value):
        """A key with colour 000000 stays dark in the custom mode."""
        self.config.custom_colors[value] = (0, 0, 0)
        self._refresh_color_view()
        self._colors_timer.start()

    def _fill_all(self, off=False):
        c = self.current_color
        rgb = (0, 0, 0) if off else (c.red(), c.green(), c.blue())
        for v in layout.KEYS:
            self.config.custom_colors[v] = rgb
        self._refresh_color_view()
        self._colors_timer.start()

    def _write_colors(self):
        colors = list(self.config.custom_colors)
        self.bridge.submit(lambda s: kc.write_custom_colors(s, colors), self._done(tr("Key colours")))

    # ================================================================= MACROS
    def _build_macros_tab(self):
        page = QWidget()
        row = QHBoxLayout(page)

        left, lbox = _card(tr("Macros"))
        self.macro_list = QListWidget()
        self.macro_list.currentRowChanged.connect(self._on_macro_selected)
        lbox.addWidget(self.macro_list, 1)
        brow = QGridLayout()
        for i, (text, fn) in enumerate(((tr("New"), self._new_macro), (tr("Rename"), self._rename_macro),
                                        (tr("Copy"), self._copy_macro), (tr("Delete"), self._delete_macro))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            brow.addWidget(b, i // 2, i % 2)
        lbox.addLayout(brow)
        row.addWidget(left, 1)

        mid, mbox = _card(tr("Record"))
        self.delay_group = QButtonGroup(page)
        for i, text in enumerate((tr("Record real intervals"), tr("No delay between actions"), tr("Fixed delay"))):
            r = QRadioButton(text)
            self.delay_group.addButton(r, i)
            mbox.addWidget(r)
        self.delay_group.button(0).setChecked(True)
        frow = QHBoxLayout()
        self.fixed_delay = QSpinBox()
        self.fixed_delay.setRange(1, 60000)
        self.fixed_delay.setValue(10)
        self.fixed_delay.setSuffix(" ms")
        frow.addWidget(self.fixed_delay)
        frow.addStretch(1)
        mbox.addLayout(frow)
        self.record_btn = QPushButton(tr("Start recording"))
        self.record_btn.setCheckable(True)
        self.record_btn.toggled.connect(self._on_record_toggled)
        mbox.addWidget(self.record_btn)
        mbox.addWidget(_muted(tr("While recording, press keys on the keyboard; the panel window must have focus. "
                                 "Recorded actions are added at the selected row.")))
        mbox.addSpacing(12)
        add_title = QLabel(tr("Add action"))
        add_title.setStyleSheet("font-weight: 600;")
        mbox.addWidget(add_title)
        self.add_kind = QComboBox()
        self.add_kind.addItem(tr("Key"), False)
        self.add_kind.addItem(tr("Mouse button"), True)
        self.add_kind.currentIndexChanged.connect(self._fill_add_targets)
        self.add_target = QComboBox()
        mbox.addWidget(self.add_kind)
        mbox.addWidget(self.add_target)
        add_btn = QPushButton(tr("Add press + release"))
        add_btn.clicked.connect(self._add_manual_action)
        mbox.addWidget(add_btn)
        mbox.addStretch(1)
        row.addWidget(mid, 1)

        right, rbox = _card(tr("Actions"))
        self.event_table = QTableWidget(0, 3)
        self.event_table.setHorizontalHeaderLabels([tr("Key"), tr("Action"), tr("Delay (ms)")])
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.event_table.verticalHeader().setVisible(False)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.event_table.itemChanged.connect(self._on_delay_edited)
        rbox.addWidget(self.event_table, 1)
        erow = QHBoxLayout()
        for text, fn in ((tr("Move up"), lambda: self._move_event(-1)), (tr("Move down"), lambda: self._move_event(1)),
                         (tr("Remove"), self._remove_event), (tr("Clear"), self._clear_events)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            erow.addWidget(b)
        rbox.addLayout(erow)
        self.save_macros_btn = QPushButton(tr("Save macros to keyboard"))
        self.save_macros_btn.clicked.connect(self._save_macros)
        rbox.addWidget(self.save_macros_btn)
        self.macro_dirty_label = _muted("")
        rbox.addWidget(self.macro_dirty_label)
        row.addWidget(right, 2)

        self._recording = False
        self._last_event_time = None
        self._macros_dirty = False
        self._fill_add_targets()
        return page

    def _fill_add_targets(self):
        self.add_target.clear()
        if self.add_kind.currentData():
            for mask, name in layout.MOUSE_BUTTON_NAMES.items():
                self.add_target.addItem(tr(name), mask)
        else:
            for label, act in layout.BASIC + layout.EXTENDED:
                if act.b2 != 111:
                    self.add_target.addItem(tr(label), act.b2)

    def _refresh_macros(self, select=None):
        if not self.config:
            return
        names = self.macro_names.all()
        current = select if select is not None else self._current_macro_id()
        self.macro_list.blockSignals(True)
        self.macro_list.clear()
        for mid in sorted(self.config.macros):
            item = QListWidgetItem(names.get(mid) or tr("Macro {}").format(mid + 1))
            item.setData(Qt.ItemDataRole.UserRole, mid)
            self.macro_list.addItem(item)
            if mid == current:
                self.macro_list.setCurrentItem(item)
        self.macro_list.blockSignals(False)
        self._refresh_events()
        # macro choices on the Keys tab
        self.assign_macro_combo.clear()
        for mid in sorted(self.config.macros):
            self.assign_macro_combo.addItem(names.get(mid) or tr("Macro {}").format(mid + 1), mid)
        self.macro_dirty_label.setText(tr("Unsaved changes") if self._macros_dirty else "")

    def _current_macro_id(self):
        item = self.macro_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _current_macro(self):
        mid = self._current_macro_id()
        return self.config.macros.get(mid) if mid is not None and self.config else None

    def _on_macro_selected(self, _row):
        self._stop_recording()
        self._refresh_events()

    def _refresh_events(self):
        macro = self._current_macro()
        self.event_table.blockSignals(True)
        self.event_table.setRowCount(0)
        for ev in (macro.events if macro else []):
            r = self.event_table.rowCount()
            self.event_table.insertRow(r)
            name = tr(layout.MOUSE_BUTTON_NAMES.get(ev.usage, "Mouse")) if ev.mouse else layout.usage_name(ev.usage)
            for c, text in enumerate((name, tr("Press") if ev.press else tr("Release"), str(ev.delay))):
                item = QTableWidgetItem(text)
                if c < 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.event_table.setItem(r, c, item)
        self.event_table.blockSignals(False)

    def _mark_macros_dirty(self):
        self._macros_dirty = True
        self.macro_dirty_label.setText(tr("Unsaved changes"))

    def _free_macro_id(self):
        return next((i for i in range(kc.MACRO_COUNT) if i not in self.config.macros), None)

    def _new_macro(self, events=None, name=None):
        mid = self._free_macro_id()
        if mid is None:
            QMessageBox.warning(self, tr("Macros"), tr("All 100 macro slots are used."))
            return
        if name is None:
            name, ok = QInputDialog.getText(self, tr("New macro"), tr("Name:"), text=tr("Macro {}").format(mid + 1))
            if not ok:
                return
        self.config.macros[mid] = kc.Macro(mid, list(events or []))
        self.macro_names.set(mid, name.strip() or tr("Macro {}").format(mid + 1))
        self._mark_macros_dirty()
        self._refresh_macros(select=mid)

    def _rename_macro(self):
        mid = self._current_macro_id()
        if mid is None:
            return
        old = self.macro_names.all().get(mid) or tr("Macro {}").format(mid + 1)
        name, ok = QInputDialog.getText(self, tr("Rename macro"), tr("Name:"), text=old)
        if ok and name.strip():
            self.macro_names.set(mid, name.strip())
            self._refresh_macros()
            self._refresh_keys()

    def _copy_macro(self):
        macro = self._current_macro()
        if macro:
            old = self.macro_names.all().get(macro.id) or tr("Macro {}").format(macro.id + 1)
            self._new_macro([kc.MacroEvent(**vars(e)) for e in macro.events], tr("{} (copy)").format(old))

    def _delete_macro(self):
        mid = self._current_macro_id()
        if mid is None:
            return
        bound = [v for layer in self.config.layers.values() for v, a in enumerate(layer)
                 if a.page == kc.PAGE_MACRO and a.b1 == mid]
        msg = tr("Delete this macro?")
        if bound:
            msg += tr("\nIt is assigned to {} key(s); they will be restored to their defaults.").format(len(bound))
        if QMessageBox.question(self, tr("Delete macro"), msg) != QMessageBox.StandardButton.Yes:
            return
        del self.config.macros[mid]
        self.macro_names.remove(mid)
        for layer, actions in self.config.layers.items():
            if any(a.page == kc.PAGE_MACRO and a.b1 == mid for a in actions):
                fixed = [self._key_default(layer, v) if a.page == kc.PAGE_MACRO and a.b1 == mid else a
                         for v, a in enumerate(actions)]
                self._write_layer(layer, fixed)
        self._mark_macros_dirty()
        self._refresh_macros()

    def _insert_events(self, events):
        macro = self._current_macro()
        if macro is None:
            if self._free_macro_id() is not None:
                self._new_macro(events, name=tr("Macro {}").format(self._free_macro_id() + 1))
            return
        row = self.event_table.currentRow()
        pos = row + 1 if row >= 0 else len(macro.events)
        macro.events[pos:pos] = events
        self._mark_macros_dirty()
        self._refresh_events()
        self.event_table.selectRow(pos + len(events) - 1)

    def _add_manual_action(self):
        usage = self.add_target.currentData()
        if usage is None:
            return
        mouse = bool(self.add_kind.currentData())
        delay = self.fixed_delay.value()
        self._insert_events([kc.MacroEvent(usage, True, delay, mouse), kc.MacroEvent(usage, False, delay, mouse)])

    def _move_event(self, step):
        macro = self._current_macro()
        row = self.event_table.currentRow()
        if not macro or row < 0 or not 0 <= row + step < len(macro.events):
            return
        ev = macro.events
        ev[row], ev[row + step] = ev[row + step], ev[row]
        self._mark_macros_dirty()
        self._refresh_events()
        self.event_table.selectRow(row + step)

    def _remove_event(self):
        macro = self._current_macro()
        rows = sorted({i.row() for i in self.event_table.selectedIndexes()}, reverse=True)
        if not macro or not rows:
            return
        for r in rows:
            del macro.events[r]
        self._mark_macros_dirty()
        self._refresh_events()

    def _clear_events(self):
        macro = self._current_macro()
        if macro and macro.events:
            macro.events.clear()
            self._mark_macros_dirty()
            self._refresh_events()

    def _on_delay_edited(self, item):
        macro = self._current_macro()
        if not macro or item.column() != 2:
            return
        try:
            value = max(0, min(int(item.text()), 65535))
        except ValueError:
            value = macro.events[item.row()].delay
        macro.events[item.row()].delay = value
        self.event_table.blockSignals(True)
        item.setText(str(value))
        self.event_table.blockSignals(False)
        self._mark_macros_dirty()

    def _on_record_toggled(self, on):
        if on:
            if self._current_macro() is None:
                if self._free_macro_id() is None:
                    self.record_btn.setChecked(False)
                    return
                self._new_macro(name=tr("Macro {}").format(self._free_macro_id() + 1))
            self._recording = True
            self._last_event_time = None
            self.record_btn.setText(tr("Stop recording"))
            self.setFocus()
            self.grabKeyboard()
        else:
            self._stop_recording()

    def _stop_recording(self):
        if self._recording:
            self._recording = False
            self.releaseKeyboard()
        self.record_btn.blockSignals(True)
        self.record_btn.setChecked(False)
        self.record_btn.setText(tr("Start recording"))
        self.record_btn.blockSignals(False)

    def _record_key(self, event, press):
        """Each action's delay is the pause after it. With real intervals the
        previous recorded action gets the time that passed until this one."""
        if event.isAutoRepeat():
            return
        usage = SCANCODE_TO_HID.get(event.nativeScanCode())
        macro = self._current_macro()
        if usage is None or macro is None:
            return
        now = time.monotonic()
        mode = self.delay_group.checkedId()
        delay = {0: 10, 1: 0}.get(mode, self.fixed_delay.value())
        row = self.event_table.currentRow()
        if mode == 0 and self._last_event_time is not None and 0 <= row < len(macro.events):
            macro.events[row].delay = min(int((now - self._last_event_time) * 1000), 65535)
        self._last_event_time = now
        self._insert_events([kc.MacroEvent(usage, press, delay)])

    def keyPressEvent(self, event):
        if self._recording:
            self._record_key(event, True)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self._recording:
            self._record_key(event, False)
        else:
            super().keyReleaseEvent(event)

    def _save_macros(self):
        self._stop_recording()
        macros = {mid: kc.Macro(mid, [kc.MacroEvent(**vars(e)) for e in m.events])
                  for mid, m in self.config.macros.items()}
        try:
            kc.encode_macros(macros)
        except ValueError as e:
            QMessageBox.warning(self, tr("Macros"), str(e))
            return

        def saved(result, error):
            self._done(tr("Macros"))(result, error)
            if not error:
                self._macros_dirty = False
                self.macro_dirty_label.setText("")

        self.bridge.submit(lambda s: kc.write_macros(s, macros), saved)

    # =================================================================== SOCD
    def _build_socd_tab(self):
        page = QWidget()
        row = QHBoxLayout(page)
        info, ibox = _card("SOCD")
        ibox.addWidget(_muted(tr(
            "SOCD watches two keys (e.g. A and D) and decides what is sent when both are held. "
            "Up to 40 pairs. A key can be in one pair only.")))
        form = QGridLayout()
        self.socd_key1 = QComboBox()
        self.socd_key2 = QComboBox()
        for v in sorted(layout.KEYS, key=layout.key_name):
            if layout.KEYS[v][1] and v != layout.FN_KEY:
                self.socd_key1.addItem(layout.key_name(v), v)
                self.socd_key2.addItem(layout.key_name(v), v)
        self.socd_key1.setCurrentIndex(self.socd_key1.findText("A"))
        self.socd_key2.setCurrentIndex(self.socd_key2.findText("D"))
        self.socd_mode = QComboBox()
        for mode, text in kc.SOCD_MODES:
            self.socd_mode.addItem(tr(text), mode)
        for r, (label, w) in enumerate(((tr("Key 1"), self.socd_key1), (tr("Key 2"), self.socd_key2),
                                        (tr("Mode"), self.socd_mode))):
            form.addWidget(QLabel(label), r, 0)
            form.addWidget(w, r, 1)
        ibox.addLayout(form)
        add = QPushButton(tr("Add pair"))
        add.clicked.connect(self._add_socd)
        ibox.addWidget(add)
        ibox.addStretch(1)
        row.addWidget(info, 1)

        lst, lbox = _card(tr("Current pairs"))
        self.socd_table = QTableWidget(0, 4)
        self.socd_table.setHorizontalHeaderLabels([tr("Key 1"), tr("Key 2"), tr("Mode"), ""])
        self.socd_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.socd_table.verticalHeader().setVisible(False)
        self.socd_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lbox.addWidget(self.socd_table, 1)
        row.addWidget(lst, 2)
        return page

    def _refresh_socd(self):
        if not self.config:
            return
        pairs = kc.socd_pairs(self.config.layers[kc.LAYER_NORMAL])
        self.socd_table.setRowCount(0)
        for mode, u1, u2, slots in pairs:
            r = self.socd_table.rowCount()
            self.socd_table.insertRow(r)
            self.socd_table.setItem(r, 0, QTableWidgetItem(layout.usage_name(u1)))
            self.socd_table.setItem(r, 1, QTableWidgetItem(layout.usage_name(u2)))
            combo = QComboBox()
            for m, text in kc.SOCD_MODES:
                combo.addItem(tr(text), m)
            combo.setCurrentIndex(max(0, combo.findData(mode)))
            combo.activated.connect(lambda _i, s=tuple(slots), c=combo, a=u1, b=u2:
                                    self._set_socd_slots(s, kc.KeyAction.socd(c.currentData(), a, b)))
            self.socd_table.setCellWidget(r, 2, combo)
            rm = QPushButton(tr("Remove"))
            rm.clicked.connect(lambda _=False, s=tuple(slots): self._remove_socd(s))
            self.socd_table.setCellWidget(r, 3, rm)

    def _set_socd_slots(self, slots, action):
        actions = list(self.config.layers[kc.LAYER_NORMAL])
        for v in slots:
            actions[v] = action
        self._write_layer(kc.LAYER_NORMAL, actions)

    def _remove_socd(self, slots):
        actions = list(self.config.layers[kc.LAYER_NORMAL])
        for v in slots:
            actions[v] = self._key_default(kc.LAYER_NORMAL, v)
        self._write_layer(kc.LAYER_NORMAL, actions)

    def _add_socd(self):
        v1, v2 = self.socd_key1.currentData(), self.socd_key2.currentData()
        if v1 == v2:
            QMessageBox.warning(self, "SOCD", tr("Choose two different keys."))
            return
        actions = list(self.config.layers[kc.LAYER_NORMAL])
        pairs = kc.socd_pairs(actions)
        if len(pairs) >= 40:
            QMessageBox.warning(self, "SOCD", tr("There are already 40 pairs."))
            return
        if any(actions[v].page == kc.PAGE_SOCD for v in (v1, v2)):
            QMessageBox.warning(self, "SOCD", tr("One of these keys is already in a SOCD pair. Remove it first."))
            return
        act = kc.KeyAction.socd(self.socd_mode.currentData(), layout.KEYS[v1][1], layout.KEYS[v2][1])
        self._set_socd_slots((v1, v2), act)

    # ============================================================== SETTINGS
    def _build_settings_tab(self):
        page = QWidget()
        self.settings_page = page
        row = QHBoxLayout(page)

        kb, kbox = _card(tr("Keyboard"))
        self.keyboard_settings_card = kb
        self.sleep_check = QCheckBox(tr("Sleep mode (turn the lights off and sleep when idle)"))
        self.sleep_check.toggled.connect(self._on_sleep_toggled)
        kbox.addWidget(self.sleep_check)
        srow = QHBoxLayout()
        self.sleep_slider = QSlider(Qt.Orientation.Horizontal)
        self.sleep_slider.setRange(*kc.SLEEP_RANGE)
        self.sleep_value = QLabel("")
        self.sleep_slider.valueChanged.connect(lambda v: self.sleep_value.setText(tr("{} min").format(v)))
        self.sleep_slider.valueChanged.connect(self._on_sleep_minutes)
        srow.addWidget(self.sleep_slider, 1)
        srow.addWidget(self.sleep_value)
        kbox.addLayout(srow)
        kbox.addSpacing(10)
        kbox.addWidget(QLabel(tr("Key response time")))
        kbox.addWidget(_muted(tr("A lower level reacts faster; if keys start repeating, raise it.")))
        rrow = QHBoxLayout()
        self.delay_level_group = QButtonGroup(page)
        for level in range(kc.KEY_DELAY_RANGE[0], kc.KEY_DELAY_RANGE[1] + 1):
            r = QRadioButton(tr("Level {}").format(level))
            self.delay_level_group.addButton(r, level)
            rrow.addWidget(r)
        rrow.addStretch(1)
        self.delay_level_group.idClicked.connect(self._on_key_delay)
        kbox.addLayout(rrow)
        kbox.addSpacing(10)
        self.device_info_label = _muted("")
        kbox.addWidget(self.device_info_label)
        kbox.addStretch(1)
        reset = QPushButton(tr("Reset all keyboard settings"))
        reset.setObjectName("danger")
        reset.clicked.connect(self._factory_reset)
        kbox.addWidget(reset)
        row.addWidget(kb, 1)

        appc, abox = _card("OnionTray")
        self.autostart_check = QCheckBox(tr("Start with Windows"))
        self.autostart_check.toggled.connect(lambda c: self._app_call(self.app.on_autostart_toggled, c))
        self.bluetooth_check = QCheckBox(tr("Check Bluetooth connection"))
        self.bluetooth_check.toggled.connect(lambda c: self._app_call(self.app.on_bluetooth_toggled, c))
        abox.addWidget(self.autostart_check)
        abox.addWidget(self.bluetooth_check)
        grid = QGridLayout()
        self.poll_combo = QComboBox()
        for seconds, label in app_settings.POLL_OPTIONS:
            self.poll_combo.addItem(label, seconds)
        self.poll_combo.activated.connect(lambda: self._app_call(self.app.on_poll_interval,
                                                                 self.poll_combo.currentData()))
        self.low_combo = QComboBox()
        for level, label in app_settings.LOW_BATTERY_OPTIONS:
            self.low_combo.addItem(tr(label), level)
        self.low_combo.activated.connect(lambda: self._app_call(self.app.on_low_battery,
                                                                self.low_combo.currentData()))
        grid.addWidget(QLabel(tr("Battery refresh")), 0, 0)
        grid.addWidget(self.poll_combo, 0, 1)
        grid.addWidget(QLabel(tr("Low battery warning")), 1, 0)
        grid.addWidget(self.low_combo, 1, 1)
        self.language_combo = QComboBox()
        for code, label in i18n.LANGUAGES:
            self.language_combo.addItem(tr(label) if code == i18n.AUTO else label, code)
        self.language_combo.activated.connect(self._on_language)
        grid.addWidget(QLabel(tr("Language")), 2, 0)
        grid.addWidget(self.language_combo, 2, 1)
        abox.addLayout(grid)
        abox.addStretch(1)
        row.addWidget(appc, 1)
        self._syncing_app = False
        self._loading_settings = False
        return page

    def _on_language(self):
        code = self.language_combo.currentData()
        if not self._syncing_app and code != self.app.settings.language:
            # Rebuilds this window, so let the combo box signal finish first.
            QTimer.singleShot(0, lambda: self.app.on_language(code))

    def _app_call(self, handler, value):
        if not self._syncing_app:
            handler(value)
            self.app.sync_menu_settings()

    def sync_app_settings(self):
        """Reflect the tray app settings (they can change from the tray menu too)."""
        self._syncing_app = True
        try:
            self.autostart_check.setChecked(app_settings.is_autostart_enabled())
            self.bluetooth_check.setChecked(self.app.settings.bluetooth)
            for combo, value in ((self.poll_combo, self.app.settings.poll_interval_s),
                                 (self.low_combo, self.app.settings.low_battery),
                                 (self.language_combo, self.app.settings.language)):
                combo.setCurrentIndex(combo.findData(value))
        finally:
            self._syncing_app = False

    def _refresh_keyboard_settings(self):
        if not self.config:
            return
        st = self.config.settings
        self._loading_settings = True
        try:
            minutes = st.sleep_minutes
            self.sleep_check.setChecked(minutes > 0)
            self.sleep_slider.setValue(minutes or kc.SLEEP_RANGE[0])
            self.sleep_value.setText(tr("{} min").format(self.sleep_slider.value()))
            self.sleep_slider.setEnabled(minutes > 0)
            b = self.delay_level_group.button(st.key_delay)
            if b:
                b.setChecked(True)
            info = self.config.info
            self.device_info_label.setText(
                tr("Device {} · firmware {}").format(f"{info.vid:04X}:{info.pid:04X}", info.firmware))
        finally:
            self._loading_settings = False

    def _on_sleep_toggled(self, on):
        self.sleep_slider.setEnabled(on)
        if self._loading_settings or not self.config:
            return
        self.config.settings.sleep_minutes = self.sleep_slider.value() if on else 0
        self._settings_timer.start()

    def _on_sleep_minutes(self, minutes):
        if self._loading_settings or not self.config or not self.sleep_check.isChecked():
            return
        self.config.settings.sleep_minutes = minutes
        self._settings_timer.start()

    def _on_key_delay(self, level):
        if not self.config:
            return
        self.config.settings.key_delay = level
        self._settings_timer.start()

    def _write_settings(self):
        st = kc.Settings(list(self.config.settings.raw))
        self.bridge.submit(lambda s: kc.write_settings(s, st), self._done(tr("Settings")))

    def _factory_reset(self):
        if QMessageBox.warning(
                self, tr("Reset keyboard"),
                tr("Reset all keyboard settings (keys, lighting, macros, SOCD) to the factory defaults?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
            return
        for timer in (self._led_timer, self._colors_timer, self._settings_timer):
            timer.stop()
        self.config = None
        self._set_enabled(False)

        def done(result, error):
            self._done(tr("Reset"))(result, error)
            QTimer.singleShot(1500, self.reload)

        self.bridge.submit(kc.factory_reset, done)
