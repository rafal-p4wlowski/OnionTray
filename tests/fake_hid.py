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
HEADER = 8

# Like the real firmware: "off" (0) is stored as 21, "custom" (128) as 20, and
# the lighting colour is applied but never reported (GET answers FD FD FD).
LED_STORED_MODES = {0: 21, 128: 20}
REPORTED_COLOR = [253, 253, 253]


def factory_memory():
    # Imported here: keyboard_defaults imports keyboard_logic, which imports `hid`
    # (this module) only after conftest has installed it.
    import keyboard_config as kc
    import keyboard_defaults as defaults

    settings = list(defaults.SETTINGS)
    led = defaults.LED.encode()
    led[1:4] = REPORTED_COLOR
    led[4], led[14], led[15] = 0, 0, 0
    led[0] = LED_STORED_MODES.get(led[0], led[0])
    normal = kc.encode_table(defaults.NORMAL_LAYER)
    fn = kc.encode_table(defaults.FN_LAYER)
    return {
        0x11: settings, 0x12: normal, 0x13: led, 0x14: [0] * 512,
        0x15: [0] * 3072, 0x16: fn,
    }


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
        self.packets = []           # full payloads of every packet
        self.read_timeouts = []
        self._memory = None         # created on first use, see factory_memory()
        self.factory_resets = 0
        self.led_color = None       # colour the "LEDs" show (not readable over GET)
        self._queue = collections.deque()
        self._lock = threading.Lock()

    @property
    def memory(self):
        if self._memory is None:
            self._memory = factory_memory()
        return self._memory

    def sets(self, cmd):
        """Payloads of all SET packets for a GET command."""
        return [p for p in self.packets if p[1] == cmd + 0x10]

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
        self.packets.append(list(payload))
        if payload[0] != 0xAA:
            return
        cmd, length, addr, last = payload[1], payload[2], payload[3] | payload[4] << 8, payload[6]
        if cmd in (0x00, 0x01):
            self.initialised.add(cmd)
            self.push(0x55, cmd, 0, 0, 0, 0, 1)
        elif cmd == 0x10:
            report = [0x55, 0x10, 0x18, 0, 0, 0, 1] + [0] * 25
            report[8:16] = [0x40, 0, 0, 0x0C, 0x45, 0x0C, 0xCC, 0x80]
            report[16], report[17] = 0x25, 0x01                 # firmware 1.25
            if self.awake and self.initialised == {0x00, 0x01}:
                report[24], report[25] = self.mode, self.battery
            self.push(*report)
        elif cmd == 0x0F:                                       # factory reset: no answer
            self.factory_resets += 1
            self._memory = None
        elif not self.awake:
            return                                              # asleep: config commands time out
        elif cmd in self.memory:
            data = self.memory[cmd][addr:addr + length]
            self.push(0x55, cmd, length, addr & 0xFF, addr >> 8, 0, last, 0, *data)
        elif cmd - 0x10 in self.memory:
            mem = self.memory[cmd - 0x10]
            data = payload[HEADER:HEADER + length]
            if cmd == 0x23:                                     # SET_LED_EFFECT
                self.led_color = data[1:4]
                data = list(data)
                data[0] = LED_STORED_MODES.get(data[0], data[0])
                data[1:4] = REPORTED_COLOR
                data[4], data[14], data[15] = 0, 0, 0
                data[11] = int(data[11] in (1, 2))              # direction is stored as one bit
            mem[addr:addr + length] = data
            self.push(0x55, cmd, length, addr & 0xFF, addr >> 8, 0, last, 0)


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
