import logging
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger("oniontray")

INITIAL_STATE = {
    "receiver": False,     # vendor HID interface found (receiver or USB cable)
    "awake": False,        # the keyboard answered the last poll
    "battery": None,       # last known level; kept while the keyboard sleeps
    "mode": None,          # connection mode of the last answer
    "last_seen": None,     # time.time() of the last answer
}


class KeyboardWorker(QThread):
    """Polls the keyboard in the background. The device is opened only for the
    duration of each poll, so the vendor software can still use it."""

    state_changed = pyqtSignal(dict)

    def __init__(self, protocol, poll_interval_s=60, bluetooth=True):
        super().__init__()
        self.kl = protocol
        # Plain attributes: written by the GUI thread, read here.
        self.poll_interval_s = poll_interval_s
        self.bluetooth = bluetooth
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.state = dict(INITIAL_STATE)

    # Called from the GUI thread.
    def refresh_now(self):
        self._wake.set()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self._apply(self.poll())
            except Exception:
                log.exception("Poll failed")
            self._wake.wait(self.poll_interval_s)
            self._wake.clear()

    def poll(self):
        receiver, status = self.kl.read_hid_status()
        if status is None and self.bluetooth and not self._stop.is_set():
            level = self.kl.read_bluetooth_battery()
            if level is not None:
                status = {"battery": level, "mode": self.kl.MODE_BLUETOOTH}
        update = {"receiver": receiver, "awake": status is not None}
        if status:
            update.update(status, last_seen=time.time())
        elif not receiver and self.state["mode"] != self.kl.MODE_BLUETOOTH:
            # Receiver unplugged: the old reading no longer belongs to anything.
            update.update(battery=None, mode=None, last_seen=None)
        return update

    def _apply(self, update):
        new = dict(self.state)
        new.update(update)
        if new == self.state:
            return
        if new["awake"] != self.state["awake"] or new["mode"] != self.state["mode"]:
            log.info("Keyboard %s (%s, battery %s%%)",
                     "answering" if new["awake"] else "not answering", new["mode"], new["battery"])
        self.state = new
        self.state_changed.emit(dict(new))
