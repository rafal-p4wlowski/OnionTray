"""In-memory stand-in for the cython-hidapi `hid` module that simulates the
Onionite V2 2.4G receiver. conftest.py installs it as `hid` before
keyboard_logic is imported.

Like the real receiver it exposes several interfaces; only the vendor one
(usage page 0xFF60) answers packets.
"""
import collections
import threading
import time

PACKET_SIZE = 32


class Receiver:
    def __init__(self):
        self.reset()

    def reset(self):
        self.present = True
        self.awake = True
        self.battery = 80
        self.mode = 2               # 2.4G receiver
        self.initialised = set()
        self.writes = []
        self.read_timeouts = []
        self._queue = collections.deque()
        self._lock = threading.Lock()

    def push(self, *data):
        report = list(data) + [0] * (PACKET_SIZE - len(data))
        with self._lock:
            self._queue.append(report)

    def pop(self):
        with self._lock:
            return self._queue.popleft() if self._queue else None

    def handle(self, packet):
        assert packet[0] == 0x00 and len(packet) == PACKET_SIZE + 1, "bad report id / length"
        payload = packet[1:]
        self.writes.append(tuple(payload[:3]))
        if payload[0] != 0xAA:
            return
        cmd = payload[1]
        if cmd in (0x00, 0x01):
            self.initialised.add(cmd)
            self.push(0x55, cmd, 0, 0, 0, 0, 1)
        elif cmd == 0x10:
            report = [0x55, 0x10, 0x18, 0, 0, 0, 1] + [0] * 25
            if self.awake and self.initialised == {0x00, 0x01}:
                report[24], report[25] = self.mode, self.battery
            self.push(*report)


RECEIVER = Receiver()


def enumerate(vendor_id=0, product_id=0):
    if not RECEIVER.present:
        return []
    common = {"vendor_id": 0x0C45, "product_id": 0xFEFE}
    return [
        {**common, "path": b"kbd", "usage_page": 0x0001, "interface_number": 0},
        {**common, "path": b"ff59", "usage_page": 0xFF59, "interface_number": 4},
        {**common, "path": b"ff60", "usage_page": 0xFF60, "interface_number": 3},
    ]


class device:
    def open_path(self, path):
        if not RECEIVER.present:
            raise OSError("open failed")
        self.path = path

    def write(self, data):
        if not RECEIVER.present:
            raise OSError("write error")
        if self.path != b"ff60":
            return -1
        RECEIVER.handle(list(data))
        return len(data)

    def read(self, size, timeout_ms=0):
        RECEIVER.read_timeouts.append(timeout_ms)
        if timeout_ms <= 0:
            raise RuntimeError("blocking read (timeout 0) would hang the worker")
        if not RECEIVER.present:
            raise OSError("read error")
        end = time.monotonic() + timeout_ms / 1000
        while True:
            report = RECEIVER.pop()
            if report is not None:
                return report[:size]
            if time.monotonic() >= end:
                return []
            time.sleep(0.002)

    def close(self):
        pass
