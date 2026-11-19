"""User preferences (QSettings, stored under HKCU\\Software\\OnionTray)
and the "Start with Windows" entry in the registry Run key."""
import logging
import os
import sys
import winreg

from PyQt6.QtCore import QSettings

log = logging.getLogger(__name__)

APP_NAME = "OnionTray"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
# Battery refresh choices: (seconds, menu label). A keyboard battery drains
# slowly, so there is no point in polling very often.
POLL_OPTIONS = (
    (10, "10 s"), (30, "30 s"), (60, "1 min"), (120, "2 min"),
    (300, "5 min"), (600, "10 min"),
)
POLL_INTERVALS = tuple(seconds for seconds, _ in POLL_OPTIONS)
DEFAULT_POLL_INTERVAL = 60
# Low battery warning thresholds (percent, menu label); 0 disables it.
LOW_BATTERY_OPTIONS = ((0, "Disabled"), (10, "10%"), (15, "15%"), (20, "20%"), (30, "30%"))
LOW_BATTERY_LEVELS = tuple(level for level, _ in LOW_BATTERY_OPTIONS)
DEFAULT_LOW_BATTERY = 15


def data_dir():
    r"""%APPDATA%\OnionTray (log file)."""
    path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


class AppSettings:
    def __init__(self):
        self._s = QSettings(APP_NAME, APP_NAME)

    def _choice(self, key, default, allowed):
        value = self._s.value(key, default, type=int)
        return value if value in allowed else default

    @property
    def poll_interval_s(self):
        return self._choice("poll_interval_s", DEFAULT_POLL_INTERVAL, POLL_INTERVALS)

    @poll_interval_s.setter
    def poll_interval_s(self, value):
        self._s.setValue("poll_interval_s", int(value))

    @property
    def low_battery(self):
        return self._choice("low_battery", DEFAULT_LOW_BATTERY, LOW_BATTERY_LEVELS)

    @low_battery.setter
    def low_battery(self, value):
        self._s.setValue("low_battery", int(value))

    @property
    def bluetooth(self):
        return self._s.value("bluetooth", True, type=bool)

    @bluetooth.setter
    def bluetooth(self, value):
        self._s.setValue("bluetooth", bool(value))

    @property
    def language(self):
        value = self._s.value("language", "auto", type=str)
        return value if value in ("auto", "en", "pl") else "auto"

    @language.setter
    def language(self, value):
        self._s.setValue("language", str(value))


class MacroNames:
    """Macro names live only on this computer: the keyboard stores the events,
    not the names (the vendor web driver keeps them in the browser too)."""

    GROUP = "macro_names"

    def __init__(self):
        self._s = QSettings(APP_NAME, APP_NAME)

    def all(self):
        self._s.beginGroup(self.GROUP)
        try:
            return {int(k): self._s.value(k, "", type=str) for k in self._s.childKeys() if k.isdigit()}
        finally:
            self._s.endGroup()

    def set(self, macro_id, name):
        self._s.setValue(f"{self.GROUP}/{int(macro_id)}", name)

    def remove(self, macro_id):
        self._s.remove(f"{self.GROUP}/{int(macro_id)}")


class LedColorMemory:
    """Last lighting colour set from this program. The keyboard does not
    report its colour back (it always answers FD FD FD)."""

    KEY = "led_color"

    def __init__(self):
        self._s = QSettings(APP_NAME, APP_NAME)

    def color(self):
        value = self._s.value(self.KEY, "", type=str)
        try:
            r, g, b = (int(x) for x in value.split(","))
        except ValueError:
            return None
        return (r, g, b)

    def set_color(self, rgb):
        self._s.setValue(self.KEY, ",".join(str(int(c)) for c in rgb))


def autostart_command():
    """Command line Windows should run at logon."""
    if getattr(sys, "frozen", False):  # PyInstaller build
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return f'"{pythonw}" "{script}"'


def _read_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, APP_NAME)[0]
    except FileNotFoundError:
        return None


def is_autostart_enabled():
    return _read_autostart() is not None


def set_autostart(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
    log.info("Start with Windows %s", "enabled" if enabled else "disabled")


def refresh_autostart():
    """If autostart is on but points elsewhere (program moved), fix the path."""
    current = _read_autostart()
    if current is not None and current.lower() != autostart_command().lower():
        log.info("Updating autostart path (was %s)", current)
        set_autostart(True)
