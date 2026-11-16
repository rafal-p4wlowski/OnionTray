import logging
import time

from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import app_settings
from ui_components import DARK_MENU_STYLE, create_tray_icon, taskbar_is_light
from version import __version__
from worker import INITIAL_STATE, KeyboardWorker

log = logging.getLogger("oniontray")

LOW_BATTERY_HYSTERESIS = 5   # warn again only after the level rose this much above the threshold
THEME_CHECK_MS = 2000        # how often to check whether the taskbar switched light/dark


def charging_state(state):
    """Charging status derived from the connection mode: the keyboard charges
    while it is connected with the USB cable."""
    if state["battery"] is None:
        return None
    if state["mode"] != "USB cable":
        return "Not charging"
    return "Fully charged" if state["battery"] >= 100 else "Charging"


def format_last_seen(timestamp):
    return time.strftime("%H:%M", time.localtime(timestamp)) if timestamp else "---"


class KeyboardApp(QObject):
    """Tray icon and menu. Talks to the keyboard only through KeyboardWorker."""

    def __init__(self, protocol, settings):
        super().__init__()
        self.settings = settings
        self.state = dict(INITIAL_STATE)
        self._low_warned = False

        self.worker = KeyboardWorker(protocol, settings.poll_interval_s, settings.bluetooth)
        self.worker.state_changed.connect(self.sync_state)

        self.tray = QSystemTrayIcon(self)
        self._light_taskbar = taskbar_is_light()
        self.tray.setToolTip("Looking for keyboard...")
        self.tray.activated.connect(self.on_tray_activated)
        self.menu = self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.sync_state(self.state)
        self.tray.show()
        self.worker.start()

        # The ring and glyph follow the taskbar colour, which can change at any time.
        self.theme_timer = QTimer(self)
        self.theme_timer.timeout.connect(self._check_taskbar_theme)
        self.theme_timer.start(THEME_CHECK_MS)

    # --- menu construction ---
    @staticmethod
    def _info_action(menu, text=""):
        act = QAction(text, menu)
        act.setEnabled(False)
        menu.addAction(act)
        return act

    @staticmethod
    def _toggle_action(menu, text, handler):
        act = QAction(text, menu)
        act.setCheckable(True)
        act.triggered.connect(handler)
        menu.addAction(act)
        return act

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet(DARK_MENU_STYLE)

        self.connection_info = self._info_action(menu)
        self.battery_info = self._info_action(menu)
        self.charging_info = self._info_action(menu)
        self.last_seen_info = self._info_action(menu)
        menu.addSeparator()

        refresh_act = QAction("Refresh now", menu)
        refresh_act.triggered.connect(self.worker.refresh_now)
        menu.addAction(refresh_act)
        menu.addSeparator()

        self._build_settings_menu(menu)
        menu.addSeparator()

        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self.on_quit)
        menu.addAction(quit_act)
        return menu

    def _build_settings_menu(self, parent):
        sub = parent.addMenu("Settings")
        sub.setStyleSheet(DARK_MENU_STYLE)

        self.autostart_act = self._toggle_action(sub, "Start with Windows", self.on_autostart_toggled)
        self.autostart_act.setChecked(app_settings.is_autostart_enabled())

        self.bluetooth_act = self._toggle_action(sub, "Check Bluetooth connection", self.on_bluetooth_toggled)
        self.bluetooth_act.setChecked(self.settings.bluetooth)

        _, self.poll_group = self._choice_menu(
            sub, "Battery refresh", app_settings.POLL_OPTIONS, self.on_poll_interval)
        self._check_choice(self.poll_group, self.settings.poll_interval_s)

        _, self.low_group = self._choice_menu(
            sub, "Low battery warning", app_settings.LOW_BATTERY_OPTIONS, self.on_low_battery)
        self._check_choice(self.low_group, self.settings.low_battery)

        sub.addSeparator()
        self._info_action(sub, f"Version {__version__}")

    def _choice_menu(self, parent, title, options, handler):
        sub = parent.addMenu(title)
        sub.setStyleSheet(DARK_MENU_STYLE)
        group = QActionGroup(sub)
        group.setExclusive(True)
        for value, label in options:
            act = QAction(label, group)
            act.setCheckable(True)
            act.setData(value)
            sub.addAction(act)
        group.triggered.connect(lambda act: handler(act.data()))
        return sub, group

    @staticmethod
    def _check_choice(group, value):
        match = next((act for act in group.actions() if act.data() == value), None)
        if match is not None:
            match.setChecked(True)
            return
        group.setExclusive(False)
        for act in group.actions():
            act.setChecked(False)
        group.setExclusive(True)

    # --- handlers ---
    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.worker.refresh_now()

    def on_autostart_toggled(self, checked):
        try:
            app_settings.set_autostart(checked)
        except OSError as e:
            log.error("Cannot change autostart: %s", e)
        self.autostart_act.setChecked(app_settings.is_autostart_enabled())

    def on_bluetooth_toggled(self, checked):
        self.settings.bluetooth = checked
        self.worker.bluetooth = checked
        self.worker.refresh_now()

    def on_poll_interval(self, seconds):
        self.settings.poll_interval_s = seconds
        self.worker.poll_interval_s = seconds
        self.worker.refresh_now()  # restart the wait with the new interval

    def on_low_battery(self, level):
        self.settings.low_battery = level
        self._low_warned = False
        self._update_icon()  # the arc turns amber/red relative to the threshold
        self._check_low_battery()

    def on_quit(self):
        self.worker.stop()
        if not self.worker.wait(5000):
            log.warning("Worker did not stop in time")
        self.tray.hide()
        QApplication.quit()

    # --- state ---
    def _status_text(self):
        state = self.state
        if state["awake"]:
            return f"Keyboard connected ({state['mode']})"
        if state["battery"] is not None:
            return "Keyboard asleep / not responding"
        if state["receiver"]:
            return "Keyboard off / out of range"
        return "Keyboard not found"

    def sync_state(self, state):
        self.state = state
        bat = state["battery"]
        charging = charging_state(state)

        self.connection_info.setText(self._status_text())
        self.battery_info.setText(f"Battery level: {bat}%" if bat is not None else "Battery level: ---")
        self.charging_info.setText(f"Charging status: {charging or '---'}")
        self.last_seen_info.setText(f"Last reading: {format_last_seen(state['last_seen'])}")
        self.last_seen_info.setVisible(bat is not None and not state["awake"])

        self._update_icon()
        self._check_low_battery()
        self._refresh_tooltip(charging)

    def _update_icon(self):
        state = self.state
        self.tray.setIcon(create_tray_icon(
            state["battery"], charging=charging_state(state) == "Charging", active=state["awake"],
            low=self.settings.low_battery, light_taskbar=self._light_taskbar))

    def _check_taskbar_theme(self):
        light = taskbar_is_light()
        if light != self._light_taskbar:
            self._light_taskbar = light
            self._update_icon()

    def _check_low_battery(self):
        bat, threshold = self.state["battery"], self.settings.low_battery
        if bat is None or not self.state["awake"] or not threshold:
            return
        if charging_state(self.state) != "Not charging" or bat > threshold + LOW_BATTERY_HYSTERESIS:
            self._low_warned = False
        elif bat <= threshold and not self._low_warned:
            self._low_warned = True
            log.info("Low battery warning at %s%%", bat)
            self.tray.showMessage("Keyboard battery low", f"Battery level: {bat}%. Connect the USB cable.",
                                  QSystemTrayIcon.MessageIcon.Warning, 10_000)

    def _refresh_tooltip(self, charging):
        state = self.state
        bat = state["battery"]
        if bat is None:
            self.tray.setToolTip(self.connection_info.text())
            return
        lines = [f"Keyboard battery: {bat}%", self.connection_info.text()]
        if not state["awake"]:
            lines.append(f"Last reading: {format_last_seen(state['last_seen'])}")
        elif charging != "Not charging":
            lines.append(f"Charging status: {charging}")
        self.tray.setToolTip("\n".join(lines))
