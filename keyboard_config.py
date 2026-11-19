"""Keyboard configuration (lighting, keys, macros, SOCD, settings) over the
vendor HID interface, as done by the Dark Project web driver (app.darkproject.eu).

Every block is read and written whole: the device keeps 128 four-byte key
slots per layer, a 16-byte lighting record, a 56-byte settings record and a
macro area (100 pointers followed by the macro bodies). Writes always go
read -> patch -> write, so fields this program does not model are preserved.
"""
import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# --- commands ---
CMD_FACTORY_RESET = 0x0F
CMD_DEVICE_INFO = 0x10
CMD_SETTINGS = 0x11          # "game mode" block in the web driver
CMD_KEYS = 0x12
CMD_LED_EFFECT = 0x13
CMD_CUSTOM_LED = 0x14
CMD_MACRO = 0x15
CMD_FN_KEYS = 0x16
SET = 0x10                  # SET_x = GET_x + 0x10

INFO_SIZE = 24               # the fields we use are all in the first packet
SETTINGS_SIZE = 56
LED_SIZE = 16
TABLE_SIZE = 512             # 128 slots x 4 bytes (keys, Fn keys, per-key colours)
SLOTS = 128
MACRO_INDEX_SIZE = 400       # 100 x uint32 LE address, 0 = empty
MACRO_COUNT = 100
MACRO_SPACE = 3072           # what this keyboard reports; bodies start at 400

RESET_ALL = 0xFF

LAYER_NORMAL, LAYER_FN = "normal", "fn"
LAYER_COMMANDS = {LAYER_NORMAL: CMD_KEYS, LAYER_FN: CMD_FN_KEYS}

# --- key action pages (byte 0 of a key slot) ---
PAGE_DEFAULT, PAGE_MOUSE, PAGE_KEYBOARD, PAGE_CONSUMER = 0x00, 0x01, 0x02, 0x03
PAGE_MACRO, PAGE_SOCD, PAGE_FUNC = 0x06, 0x0B, 0x0D

MOUSE_BUTTON, MOUSE_WHEEL = 1, 3

MACRO_ONCE, MACRO_REPEAT, MACRO_TOGGLE = 0, 1, 2
MACRO_MODES = ((MACRO_ONCE, "Play once"), (MACRO_TOGGLE, "Press again to stop"),
               (MACRO_REPEAT, "Repeat N times"))

SOCD_KEY1, SOCD_KEY2, SOCD_LAST, SOCD_NEUTRAL = 1, 2, 3, 4
SOCD_MODES = (
    (SOCD_LAST, "Last input priority"),
    (SOCD_KEY1, "Key 1 priority"),
    (SOCD_KEY2, "Key 2 priority"),
    (SOCD_NEUTRAL, "Neutral (both pressed = none)"),
)

# --- lighting ---
LED_OFF = 0
LED_CUSTOM = 128
# The firmware stores "off" as 21 and "custom" as 20 and reports those back.
STORED_MODES = {21: LED_OFF, 20: LED_CUSTOM}
# It does not report the stored colour either: GET always answers FD FD FD,
# although the LEDs show the colour that was written (checked with 0x33).
REPORTED_COLOR = (253, 253, 253)
DIRECTION_RIGHT, DIRECTION_LEFT, DIRECTION_UP, DIRECTION_DOWN = 0, 1, 2, 3


@dataclass(frozen=True)
class LightingMode:
    id: int
    name: str
    speed: bool = True
    direction: tuple = ()          # direction values offered, first is the default
    color: bool = True             # single colour can be chosen (else rainbow only)


_HORIZONTAL = (DIRECTION_RIGHT, DIRECTION_LEFT)
LIGHTING_MODES = (
    LightingMode(1, "Static Bright", speed=False),
    LightingMode(2, "Single Point On"),
    LightingMode(3, "Single Point Off"),
    LightingMode(4, "Starry Sky"),
    LightingMode(5, "Snowfall"),
    LightingMode(6, "Floral Competition", color=False),
    LightingMode(7, "Dynamic Breathing"),
    LightingMode(8, "Spectrum Cycle", color=False),
    LightingMode(9, "Color Fountain"),
    LightingMode(10, "Colorful Interchange", direction=(DIRECTION_DOWN, DIRECTION_UP)),
    LightingMode(11, "Flowing with the Waves", direction=_HORIZONTAL),
    LightingMode(12, "Turning Peaks", direction=_HORIZONTAL),
    LightingMode(13, "One Touch to Fire"),
    LightingMode(14, "Two Birds with One Stone"),
    LightingMode(15, "Ripples Spread"),
    LightingMode(16, "Endless Flow", direction=_HORIZONTAL),
    LightingMode(17, "Layered Mountains"),
    LightingMode(18, "Gentle Rain and Wind", direction=_HORIZONTAL),
    LightingMode(19, "Back and Forth"),
    LightingMode(LED_CUSTOM, "Custom (per key)", speed=False),
)
LIGHTING_BY_ID = {m.id: m for m in LIGHTING_MODES}
DIRECTION_NAMES = {DIRECTION_RIGHT: "Right", DIRECTION_LEFT: "Left", DIRECTION_UP: "Up", DIRECTION_DOWN: "Down"}
BRIGHTNESS_RANGE = (1, 5)
SPEED_RANGE = (1, 5)

# --- settings ---
SLEEP_RANGE = (1, 30)        # minutes; 0 = sleep disabled
KEY_DELAY_RANGE = (1, 5)     # "Key Response Time" level


# ---------------------------------------------------------------- data model

@dataclass
class DeviceInfo:
    vid: int = 0
    pid: int = 0
    firmware: str = ""
    battery: int = 0

    @classmethod
    def decode(cls, data):
        return cls(vid=data[4] | data[5] << 8, pid=data[6] | data[7] << 8,
                   firmware=f"{data[9]:x}.{data[8]:02x}", battery=min(data[17], 100))


@dataclass
class Settings:
    raw: list = field(default_factory=lambda: [0] * SETTINGS_SIZE)

    @property
    def sleep_minutes(self):
        return self.raw[3]

    @sleep_minutes.setter
    def sleep_minutes(self, value):
        self.raw[3] = max(0, min(int(value), SLEEP_RANGE[1]))

    @property
    def key_delay(self):
        return self.raw[4] or 3

    @key_delay.setter
    def key_delay(self, value):
        self.raw[4] = max(KEY_DELAY_RANGE[0], min(int(value), KEY_DELAY_RANGE[1]))

    def encode(self):
        return list(self.raw[:SETTINGS_SIZE]) + [0] * (SETTINGS_SIZE - len(self.raw))


@dataclass
class LedEffect:
    mode: int = 1
    color: tuple = (255, 255, 255)
    rainbow: bool = False
    brightness: int = 5
    speed: int = 3
    direction: int = 0
    extra: list = field(default_factory=lambda: [0] * 4)   # bytes 5-7 and 12, kept as read

    @classmethod
    def decode(cls, d):
        mode = STORED_MODES.get(d[0], d[0])
        direction = d[11]
        info = LIGHTING_BY_ID.get(mode)
        if info and DIRECTION_UP in info.direction:
            # The direction is stored as one bit: up (2) reads back as 1, down (3) as 0.
            direction = DIRECTION_UP if direction == 1 else DIRECTION_DOWN
        return cls(mode=mode, color=(d[1], d[2], d[3]), rainbow=bool(d[8]),
                   brightness=d[9] or 5, speed=d[10] or 3, direction=direction,
                   extra=[d[5], d[6], d[7], d[12]])

    def encode(self):
        r, g, b = self.color
        e = self.extra
        return [self.mode, r, g, b, 0xFF, e[0], e[1], e[2], int(self.rainbow),
                self.brightness, self.speed, self.direction, e[3], 0, 0xAA, 0x55]

    @property
    def on(self):
        return self.mode != LED_OFF


@dataclass(frozen=True)
class KeyAction:
    """One 4-byte key slot."""
    page: int = 0
    b1: int = 0
    b2: int = 0
    b3: int = 0

    @classmethod
    def decode(cls, data):
        return cls(*data[:4])

    def encode(self):
        return [self.page, self.b1, self.b2, self.b3]

    # constructors
    @classmethod
    def key(cls, usage):
        return cls(PAGE_KEYBOARD, 0, usage, 0)

    @classmethod
    def consumer(cls, usage):
        return cls(PAGE_CONSUMER, usage & 0xFF, usage >> 8 & 0xFF, 0)

    @classmethod
    def mouse(cls, kind, value):
        return cls(PAGE_MOUSE, kind, value, 0)

    @classmethod
    def function(cls, func_id):
        return cls(PAGE_FUNC, func_id >> 16 & 0xFF, func_id >> 8 & 0xFF, func_id & 0xFF)

    @classmethod
    def macro(cls, macro_id, mode=MACRO_ONCE, count=1):
        return cls(PAGE_MACRO, macro_id, mode, count if mode == MACRO_REPEAT else 0)

    @classmethod
    def socd(cls, mode, usage1, usage2):
        return cls(PAGE_SOCD, mode, usage1, usage2)

    @property
    def consumer_usage(self):
        return self.b1 | self.b2 << 8

    @property
    def func_id(self):
        return self.b1 << 16 | self.b2 << 8 | self.b3


@dataclass
class MacroEvent:
    usage: int                 # HID usage (keyboard) or button mask (mouse)
    press: bool
    delay: int = 10            # ms
    mouse: bool = False

    def encode(self):
        flags = (0x90 if self.press else 0x10) if self.mouse else (0xB0 if self.press else 0x30)
        delay = max(0, min(int(self.delay), 0xFFFF))
        return [delay & 0xFF, delay >> 8, self.usage & 0xFF, flags]

    @classmethod
    def decode(cls, data):
        flags = data[3]
        action_type = flags >> 4 & 7
        return cls(usage=data[2], press=bool(flags & 0x80), delay=data[0] | data[1] << 8,
                   mouse=action_type in (1, 2))


@dataclass
class Macro:
    id: int
    events: list = field(default_factory=list)

    def encode_body(self):
        n = len(self.events)
        body = [(n * 2) & 0xFF, (n * 2) >> 8, 0, 0]
        for ev in self.events:
            body += ev.encode()
        return body


@dataclass
class KeyboardConfig:
    info: DeviceInfo
    settings: Settings
    led: LedEffect
    layers: dict               # layer -> list[KeyAction] (128)
    custom_colors: list        # 128 x (r, g, b)
    macros: dict               # macro id -> Macro


# ------------------------------------------------------------------ codecs

def decode_table(data):
    return [KeyAction.decode(data[i * 4:i * 4 + 4]) for i in range(SLOTS)]


def encode_table(actions):
    out = []
    for i in range(SLOTS):
        out += (actions[i] if i < len(actions) else KeyAction()).encode()
    return out


def decode_colors(data):
    return [tuple(data[i * 4 + 1:i * 4 + 4]) for i in range(SLOTS)]


def encode_colors(colors):
    out = []
    for i in range(SLOTS):
        r, g, b = colors[i] if i < len(colors) else (0, 0, 0)
        out += [i, r, g, b]
    return out


def encode_macros(macros):
    """Return (index, bodies) for SET_MACRO. Raises ValueError if they don't fit."""
    index = [0] * MACRO_INDEX_SIZE
    bodies = []
    addr = MACRO_INDEX_SIZE
    for macro in sorted(macros.values(), key=lambda m: m.id):
        if not macro.events:
            continue
        if not 0 <= macro.id < MACRO_COUNT:
            raise ValueError(f"macro id {macro.id} out of range")
        body = macro.encode_body()
        index[macro.id * 4:macro.id * 4 + 4] = [addr & 0xFF, addr >> 8 & 0xFF, addr >> 16 & 0xFF, addr >> 24 & 0xFF]
        bodies += body
        addr += len(body)
    if addr > MACRO_SPACE:
        raise ValueError(f"macros need {addr - MACRO_INDEX_SIZE} bytes, only "
                         f"{MACRO_SPACE - MACRO_INDEX_SIZE} available")
    return index, bodies


def socd_pairs(actions):
    """[(mode, usage1, usage2, [slot values])] found in a key table."""
    pairs = {}
    for value, act in enumerate(actions):
        if act.page == PAGE_SOCD:
            pairs.setdefault((act.b1, act.b2, act.b3), []).append(value)
    return [(m, u1, u2, slots) for (m, u1, u2), slots in pairs.items()]


# ---------------------------------------------------------- device access

def read_config(session):
    info = DeviceInfo.decode(session.request(CMD_DEVICE_INFO, INFO_SIZE))
    settings = Settings(session.read_block(CMD_SETTINGS, SETTINGS_SIZE))
    led = LedEffect.decode(session.request(CMD_LED_EFFECT, LED_SIZE))
    layers = {layer: decode_table(session.read_block(cmd, TABLE_SIZE)) for layer, cmd in LAYER_COMMANDS.items()}
    colors = decode_colors(session.read_block(CMD_CUSTOM_LED, TABLE_SIZE))
    macros = read_macros(session)
    return KeyboardConfig(info, settings, led, layers, colors, macros)


def read_macros(session):
    index = session.read_block(CMD_MACRO, MACRO_INDEX_SIZE)
    macros = {}
    for mid in range(MACRO_COUNT):
        addr = int.from_bytes(bytes(index[mid * 4:mid * 4 + 4]), "little")
        if not addr:
            continue
        if not MACRO_INDEX_SIZE <= addr < MACRO_SPACE:
            log.warning("Macro %d points outside the macro area (%d), ignored", mid, addr)
            continue
        header = session.read_block(CMD_MACRO, 4, addr)
        count = (header[0] | header[1] << 8) // 2
        data = session.read_block(CMD_MACRO, count * 4, addr + 4) if count else []
        macros[mid] = Macro(mid, [MacroEvent.decode(data[i * 4:i * 4 + 4]) for i in range(count)])
    return macros


def write_settings(session, settings):
    session.write_block(CMD_SETTINGS + SET, settings.encode())


def write_led(session, led):
    session.request(CMD_LED_EFFECT + SET, LED_SIZE, data=led.encode())


def write_layer(session, layer, actions):
    session.write_block(LAYER_COMMANDS[layer] + SET, encode_table(actions))


def write_custom_colors(session, colors):
    session.write_block(CMD_CUSTOM_LED + SET, encode_colors(colors))


def write_macros(session, macros):
    index, bodies = encode_macros(macros)
    session.write_block(CMD_MACRO + SET, index, final=not bodies)
    if bodies:
        session.write_block(CMD_MACRO + SET, bodies, addr=MACRO_INDEX_SIZE)


def factory_reset(session, kind=RESET_ALL):
    """No answer comes back; the keyboard reports 55 FC 05 when done."""
    session.send_raw([0xAA, CMD_FACTORY_RESET, kind])
    time.sleep(0.5)
