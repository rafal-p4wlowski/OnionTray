"""HID protocol for the Dark Project ALU104A Onionite V2 Wireless keyboard.

The 2.4G receiver (and the keyboard itself on a USB cable) exposes a vendor
interface (usage page 0xFF60 / 0xFF68) that accepts 32-byte packets starting
with 0xAA and answers with packets starting with 0x55. After two
initialisation packets the status packet (0xAA 0x10 0x18 ...) returns:

    byte 24  connection mode (0/1 USB cable, 2 receiver 2.4G, 3 Bluetooth)
    byte 25  battery level in percent (0 = no data, e.g. the keyboard is asleep)

In Bluetooth mode the receiver is not used; Windows then reports the battery
level of the paired "ALU104 ..." device (see read_bluetooth_battery).
"""
import contextlib
import logging
import subprocess
import sys
import threading
import time

import hid

log = logging.getLogger(__name__)

VENDOR_ID = 0x0C45
USAGE_PAGES = (0xFF60, 0xFF68)
PACKET_SIZE = 32
REPORT_ID = 0x00

INIT_PACKETS = (
    (0xAA, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01),
    (0xAA, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01),
)
STATUS_PACKET = (0xAA, 0x10, 0x18, 0x00, 0x00, 0x00, 0x01)
ANSWER_MARKER = 0x55
CMD_STATUS = 0x10
MODE_BYTE = 24
BATTERY_BYTE = 25

ATTEMPTS = 2
WRITE_DELAY = 0.05          # seconds between a write and the first read
STATUS_TIMEOUT = 0.5        # seconds to wait for the status answer
READ_POLL_MS = 20

MODE_CABLE, MODE_RECEIVER, MODE_BLUETOOTH = "USB cable", "2.4G receiver", "Bluetooth"
MODES = {0: MODE_CABLE, 1: MODE_CABLE, 2: MODE_RECEIVER, 3: MODE_BLUETOOTH}

# Bluetooth name of the keyboard as Windows shows it, e.g. "ALU104 WL BT1".
BLUETOOTH_NAME_PATTERNS = ("ALU104*", "*Onionite*")
BT_TIMEOUT_S = 20
# DEVPKEY_Device_IsConnected / DEVPKEY_Bluetooth_Battery
_PS_BT_BATTERY = (
    "$names = @({names}); "
    "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
    "Where-Object {{ $n = $_.FriendlyName; $names | Where-Object {{ $n -like $_ }} }} | "
    "ForEach-Object {{ "
    "$conn = (Get-PnpDeviceProperty -InstanceId $_.InstanceId "
    "-KeyName '{{83DA6326-97A6-4088-9453-A1923F573B29}} 15' -ErrorAction SilentlyContinue).Data; "
    "$bat = (Get-PnpDeviceProperty -InstanceId $_.InstanceId "
    "-KeyName '{{104EA319-6EE2-4701-BD47-8DDBF425BBE5}} 2' -ErrorAction SilentlyContinue).Data; "
    "if ($conn -eq $true -and $bat -ne $null) {{ $bat }} }}"
)


class KeyboardError(Exception):
    """Communication with the receiver failed."""


def parse_status(report):
    """Return {"battery", "mode"} from a status answer, or None if the report
    is something else or carries no battery data."""
    if (len(report) <= BATTERY_BYTE or report[0] != ANSWER_MARKER
            or report[1] != CMD_STATUS or report[BATTERY_BYTE] == 0):
        return None
    mode = report[MODE_BYTE]
    return {"battery": min(report[BATTERY_BYTE], 100), "mode": MODES.get(mode, f"Mode {mode}")}


def _packet(payload):
    """Report ID followed by a zero-padded 32-byte payload."""
    return [REPORT_ID, *payload] + [0] * (PACKET_SIZE - len(payload))


class _Transport:
    """Thin wrapper over either HID binding that can be installed as `hid`:
    `hidapi` (cython-hidapi, has hid.device) or `hid` (ctypes, has hid.Device,
    needs hidapi.dll next to the program or on PATH)."""

    def __init__(self, path):
        try:
            if hasattr(hid, "device"):
                self._dev = hid.device()
                self._dev.open_path(path)
                self._as_bytes = False
            else:
                self._dev = hid.Device(path=path)
                self._as_bytes = True
        except Exception as e:
            raise KeyboardError(f"cannot open {path!r}: {e}") from e

    def write(self, packet):
        try:
            if self._dev.write(bytes(packet) if self._as_bytes else list(packet)) >= 0:
                return
            error = "device returned -1"
        except Exception as e:
            error = e
        raise KeyboardError(f"write failed: {error}")

    def read(self, timeout_ms):
        """Return one report as a list of ints, or None on timeout."""
        # cython-hidapi treats timeout 0 as "block forever", so never pass 0.
        try:
            data = self._dev.read(PACKET_SIZE, max(1, int(timeout_ms)))
        except Exception as e:
            raise KeyboardError(f"read failed: {e}") from e
        return list(data) if data else None

    def drain(self):
        while self.read(1):
            pass

    def close(self):
        try:
            self._dev.close()
        except Exception:
            pass


def find_interfaces():
    """Paths of the vendor interfaces of a connected receiver/keyboard."""
    try:
        devices = hid.enumerate(VENDOR_ID, 0)
    except Exception as e:
        log.warning("HID enumeration failed: %s", e)
        return []
    return [d["path"] for d in devices if d.get("usage_page") in USAGE_PAGES]


def _query_path(path):
    with IO_LOCK:
        return _query_path_locked(path)


def _query_path_locked(path):
    t = _Transport(path)
    try:
        t.drain()
        for _ in range(ATTEMPTS):
            for pkt in INIT_PACKETS:
                t.write(_packet(pkt))
                time.sleep(WRITE_DELAY)
                t.drain()
            t.write(_packet(STATUS_PACKET))
            end = time.monotonic() + STATUS_TIMEOUT
            while time.monotonic() < end:
                report = t.read(READ_POLL_MS)
                if report:
                    log.debug("Report: %s", " ".join(f"{x:02X}" for x in report))
                    status = parse_status(report)
                    if status:
                        return status
        return None
    finally:
        t.close()


def read_hid_status():
    """Ask the receiver for the keyboard status.

    Returns (receiver_found, status) where status is {"battery", "mode"} or
    None when the keyboard does not answer (asleep, switched off, or in
    Bluetooth mode while the receiver stays plugged in).
    """
    paths = find_interfaces()
    for path in paths:
        try:
            status = _query_path(path)
        except KeyboardError as e:
            log.debug("Interface %r: %s", path, e)
            continue
        if status:
            return True, status
    return bool(paths), None


# --- configuration session (settings panel) ---
#
# Packet layout used by the vendor web driver (app.darkproject.eu):
#   0 0xAA | 1 cmd | 2 length | 3-4 address LE | 5 0 | 6 last-packet flag | 7 0 | 8.. data
# Answers carry 0x55 in byte 0 and the same command; their data starts at byte 8.
# Blocks longer than one packet are sent/read in 24-byte chunks, the address
# advancing by 24 and the last flag set on the final chunk only.

IO_LOCK = threading.RLock()     # one conversation with the device at a time
HEADER_SIZE = 8
CHUNK_SIZE = PACKET_SIZE - HEADER_SIZE
REQUEST_TIMEOUT = 0.6
REQUEST_ATTEMPTS = 3


class Session:
    """An open vendor interface for a series of configuration commands.
    Use open_session(); every call must run while IO_LOCK is held."""

    def __init__(self, transport):
        self.t = transport

    def request(self, cmd, length=0, addr=0, data=None, last=True, timeout=REQUEST_TIMEOUT):
        """Send one packet and return the answer's data bytes (24 of them)."""
        payload = [0xAA, cmd, length, addr & 0xFF, (addr >> 8) & 0xFF, 0, int(bool(last)), 0]
        payload += list(data or [])[:CHUNK_SIZE]
        error = None
        for _ in range(REQUEST_ATTEMPTS):
            self.t.drain()
            self.t.write(_packet(payload))
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                report = self.t.read(READ_POLL_MS)
                if report and len(report) >= HEADER_SIZE and report[0] == ANSWER_MARKER and report[1] == cmd:
                    log.debug("Answer %02X: %s", cmd, " ".join(f"{x:02X}" for x in report))
                    return report[HEADER_SIZE:PACKET_SIZE]
            error = f"no answer to command 0x{cmd:02X} (addr {addr})"
        raise KeyboardError(error)

    def read_block(self, cmd, size, addr=0):
        out = []
        offset = 0
        while offset < size:
            n = min(CHUNK_SIZE, size - offset)
            out += self.request(cmd, n, addr + offset, last=offset + n >= size)[:n]
            offset += n
        return out

    def write_block(self, cmd, data, addr=0, final=True):
        """Write data in chunks; `final` sets the last-packet flag on the last
        chunk (the macro index is written without it, the bodies follow)."""
        data = list(data)
        offset = 0
        while True:
            chunk = data[offset:offset + CHUNK_SIZE]
            last = final and offset + len(chunk) >= len(data)
            self.request(cmd, len(chunk), addr + offset, chunk, last=last)
            offset += len(chunk)
            if offset >= len(data):
                return

    def send_raw(self, payload):
        """Send a packet without waiting for an answer."""
        self.t.drain()
        self.t.write(_packet(payload))


@contextlib.contextmanager
def open_session():
    """Open the first vendor interface that answers, run the init handshake
    and yield a Session. Raises KeyboardError when nothing answers."""
    with IO_LOCK:
        paths = find_interfaces()
        if not paths:
            raise KeyboardError("keyboard / receiver not found")
        last_error = None
        for path in paths:
            try:
                t = _Transport(path)
            except KeyboardError as e:
                last_error = e
                continue
            try:
                session = Session(t)
                for pkt in INIT_PACKETS:
                    session.request(pkt[1])
            except KeyboardError as e:
                last_error = e
                t.close()
                continue
            try:
                yield session
            finally:
                t.close()
            return
        raise KeyboardError(f"no vendor interface answered: {last_error}")


def read_bluetooth_battery(patterns=BLUETOOTH_NAME_PATTERNS):
    """Battery level Windows reports for the keyboard connected over
    Bluetooth, or None."""
    names = ", ".join("'" + p.replace("'", "''") + "'" for p in patterns)
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_BT_BATTERY.format(names=names)]
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=BT_TIMEOUT_S,
                             creationflags=flags).stdout
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("Bluetooth battery query failed: %s", e)
        return None
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            return min(int(line), 100)
    return None
