import logging
import os
import signal
import sys
from logging.handlers import RotatingFileHandler

from PyQt6.QtCore import QDir, QLockFile, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

import app_settings
from version import __version__

log = logging.getLogger("oniontray")


def setup_logging():
    handlers = [RotatingFileHandler(os.path.join(app_settings.data_dir(), "oniontray.log"),
                                    maxBytes=512 * 1024, backupCount=2, encoding="utf-8")]
    if sys.stderr is not None:  # None in a --noconsole build
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("ONIONTRAY_DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    sys.excepthook = lambda *exc: log.critical("Unhandled exception", exc_info=exc)


def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("OnionTray")
    # In a PyInstaller build data files live under sys._MEIPASS.
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app.setWindowIcon(QIcon(os.path.join(base, "assets", "icon.ico")))
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(os.path.join(QDir.tempPath(), "OnionTray.lock"))
    if not lock.tryLock(100):
        log.info("Another instance is already running, exiting")
        QMessageBox.information(None, "OnionTray", "OnionTray is already running.\n"
                                "Look for its icon in the system tray.")
        return 0

    try:
        import keyboard_logic
    except ImportError as e:
        log.critical("No HID backend available: %s", e)
        QMessageBox.critical(None, "OnionTray",
                             "Cannot load the HID library.\n\nInstall 'hidapi' "
                             "(pip install hidapi), or the 'hid' package together with hidapi.dll.\n\n"
                             f"{e}")
        return 1

    from tray_app import KeyboardApp

    log.info("Starting OnionTray %s", __version__)
    try:
        app_settings.refresh_autostart()
    except OSError as e:
        log.warning("Cannot check autostart entry: %s", e)

    tray = KeyboardApp(keyboard_logic, app_settings.AppSettings())

    # Periodic timer so Python gets a chance to handle Ctrl+C.
    interrupt_timer = QTimer()
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start(500)
    signal.signal(signal.SIGINT, lambda sig, frame: tray.on_quit())

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
