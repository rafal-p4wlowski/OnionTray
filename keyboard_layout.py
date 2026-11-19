"""Physical layout of the ALU104 Onionite (104 keys + 4 media keys) and the
actions that can be assigned to a key, named as in the vendor web driver.

A key's `value` is its slot in the key tables (offset value * 4) and its LED id.
"""
import keyboard_config as kc
from i18n import tr

# (value, label, default HID usage). Usage 0 = not a plain keyboard key.
KEYS = {
    0: ("Esc", 41), 1: ("F1", 58), 2: ("F2", 59), 3: ("F3", 60), 4: ("F4", 61), 5: ("F5", 62),
    6: ("F6", 63), 7: ("F7", 64), 8: ("F8", 65), 9: ("F9", 66), 10: ("F10", 67), 11: ("F11", 68),
    12: ("F12", 69), 99: ("Print", 70), 100: ("Scroll", 71), 102: ("Pause", 72),
    96: ("Calc", 0), 15: ("Mute", 0), 14: ("Vol -", 0), 13: ("Vol +", 0),
    16: ("` ~", 53), 17: ("1 !", 30), 18: ("2 @", 31), 19: ("3 #", 32), 20: ("4 $", 33), 21: ("5 %", 34),
    22: ("6 ^", 35), 23: ("7 &", 36), 24: ("8 *", 37), 25: ("9 (", 38), 26: ("0 )", 39), 27: ("- _", 45),
    28: ("= +", 46), 92: ("Backspace", 42), 103: ("Ins", 73), 104: ("Home", 74), 105: ("PgUp", 75),
    29: ("Num Lock", 83), 30: ("Num /", 84), 31: ("Num *", 85), 109: ("Num -", 86),
    32: ("Tab", 43), 33: ("Q", 20), 34: ("W", 26), 35: ("E", 8), 36: ("R", 21), 37: ("T", 23),
    38: ("Y", 28), 39: ("U", 24), 40: ("I", 12), 41: ("O", 18), 42: ("P", 19), 43: ("[ {", 47),
    44: ("] }", 48), 60: ("\\ |", 49), 106: ("Del", 76), 107: ("End", 77), 108: ("PgDn", 78),
    45: ("Num 7", 95), 46: ("Num 8", 96), 47: ("Num 9", 97), 110: ("Num +", 87),
    48: ("Caps", 57), 49: ("A", 4), 50: ("S", 22), 51: ("D", 7), 52: ("F", 9), 53: ("G", 10),
    54: ("H", 11), 55: ("J", 13), 56: ("K", 14), 57: ("L", 15), 58: ("; :", 51), 59: ("' \"", 52),
    76: ("Enter", 40), 61: ("Num 4", 92), 62: ("Num 5", 93), 63: ("Num 6", 94),
    64: ("L-Shift", 225), 65: ("Z", 29), 66: ("X", 27), 67: ("C", 6), 68: ("V", 25), 69: ("B", 5),
    70: ("N", 17), 71: ("M", 16), 72: (", <", 54), 73: (". >", 55), 74: ("/ ?", 56),
    75: ("R-Shift", 229), 90: ("↑", 82), 77: ("Num 1", 89), 78: ("Num 2", 90), 79: ("Num 3", 91),
    95: ("Num Enter", 88),
    80: ("L-Ctrl", 224), 81: ("L-Win", 227), 82: ("L-Alt", 226), 83: ("Space", 44), 84: ("R-Alt", 230),
    85: ("Fn", 175), 86: ("Menu", 101), 87: ("R-Ctrl", 228), 88: ("←", 80), 89: ("↓", 81),
    91: ("→", 79), 93: ("Num 0", 98), 94: ("Num .", 99),
}

FN_LOCKED = frozenset(range(1, 13))     # F1-F12 carry factory Fn functions
FN_KEY = 85                              # the Fn key itself is never remapped


def _row(y, *items, x=0.0):
    """items: (value, width) or (None, gap). Returns [(value, x, y, w, h)]."""
    out = []
    for value, width, *h in items:
        if value is not None:
            out.append((value, x, y, width, h[0] if h else 1.0))
        x += width
    return out


_NAV, _PAD = 15.25, 18.5
GEOMETRY = (
    _row(0, (0, 1), (None, 1), (1, 1), (2, 1), (3, 1), (4, 1), (None, .5), (5, 1), (6, 1), (7, 1), (8, 1),
         (None, .5), (9, 1), (10, 1), (11, 1), (12, 1), (None, .25), (99, 1), (100, 1), (102, 1),
         (None, .25), (96, 1), (15, 1), (14, 1), (13, 1))
    + _row(1.25, *[(v, 1) for v in range(16, 29)], (92, 2))
    + _row(1.25, (103, 1), (104, 1), (105, 1), x=_NAV)
    + _row(1.25, (29, 1), (30, 1), (31, 1), (109, 1), x=_PAD)
    + _row(2.25, (32, 1.5), *[(v, 1) for v in range(33, 45)], (60, 1.5))
    + _row(2.25, (106, 1), (107, 1), (108, 1), x=_NAV)
    + _row(2.25, (45, 1), (46, 1), (47, 1), (110, 1, 2.0), x=_PAD)
    + _row(3.25, (48, 1.75), *[(v, 1) for v in range(49, 60)], (76, 2.25))
    + _row(3.25, (61, 1), (62, 1), (63, 1), x=_PAD)
    + _row(4.25, (64, 2.25), *[(v, 1) for v in range(65, 75)], (75, 2.75))
    + _row(4.25, (90, 1), x=_NAV + 1)
    + _row(4.25, (77, 1), (78, 1), (79, 1), (95, 1, 2.0), x=_PAD)
    + _row(5.25, (80, 1.25), (81, 1.25), (82, 1.25), (83, 6.25), (84, 1.25), (85, 1.25), (86, 1.25), (87, 1.25))
    + _row(5.25, (88, 1), (89, 1), (91, 1), x=_NAV)
    + _row(5.25, (93, 2), (94, 1), x=_PAD)
)
LAYOUT_SIZE = (22.5, 6.25)

# --------------------------------------------------------------- actions
# Each palette entry: (label, KeyAction)

_K = kc.KeyAction.key
_C = kc.KeyAction.consumer
_M = kc.KeyAction.mouse
_F = kc.KeyAction.function

BASIC = (
    [(chr(ord("A") + i), _K(4 + i)) for i in range(26)]
    + [(s, _K(30 + i)) for i, s in enumerate(("1 !", "2 @", "3 #", "4 $", "5 %", "6 ^", "7 &", "8 *", "9 (", "0 )"))]
    + [("- _", _K(45)), ("= +", _K(46)), ("[ {", _K(47)), ("] }", _K(48)), ("\\ |", _K(49)),
       ("; :", _K(51)), ("' \"", _K(52)), ("` ~", _K(53)), (", <", _K(54)), (". >", _K(55)),
       ("/ ?", _K(56)), ("# ~ (ISO)", _K(50)), ("\\ | (ISO)", _K(100))]
)

EXTENDED = (
    [("Esc", _K(41)), ("Tab", _K(43)), ("Caps", _K(57)), ("Backspace", _K(42)), ("Enter", _K(40)),
     ("Space", _K(44)), ("L-Ctrl", _K(224)), ("R-Ctrl", _K(228)), ("L-Shift", _K(225)), ("R-Shift", _K(229)),
     ("L-Alt", _K(226)), ("R-Alt", _K(230)), ("L-Win", _K(227)), ("Menu", _K(101)),
     ("↑", _K(82)), ("↓", _K(81)), ("→", _K(79)), ("←", _K(80)),
     ("Home", _K(74)), ("End", _K(77)), ("Ins", _K(73)), ("Del", _K(76)), ("PgUp", _K(75)), ("PgDn", _K(78)),
     ("Print", _K(70)), ("Scroll", _K(71)), ("Pause", _K(72))]
    + [(f"F{i + 1}", _K(58 + i)) for i in range(12)]
    # F13-F24 exist in HID but not on the keyboard: free keys for app shortcuts (e.g. Discord mute).
    + [(f"F{i + 13}", _K(104 + i)) for i in range(12)]
    + [("Num Lock", _K(83))] + [(f"Num {i + 1}", _K(89 + i)) for i in range(9)]
    + [("Num 0", _K(98)), ("Num /", _K(84)), ("Num .", _K(99)), ("Num *", _K(85)), ("Num -", _K(86)),
       ("Num +", _K(87)), ("Num Enter", _K(88)), ("Disabled key", _K(111))]
)

SPECIAL = (
    ("Left mouse button", _M(kc.MOUSE_BUTTON, 1)), ("Middle mouse button", _M(kc.MOUSE_BUTTON, 4)),
    ("Right mouse button", _M(kc.MOUSE_BUTTON, 2)), ("Mouse scroll up", _M(kc.MOUSE_WHEEL, 1)),
    ("Mouse scroll down", _M(kc.MOUSE_WHEEL, 255)), ("Mouse forward", _M(kc.MOUSE_BUTTON, 16)),
    ("Mouse back", _M(kc.MOUSE_BUTTON, 8)),
    ("My Computer", _C(404)), ("Calculator", _C(402)), ("Email", _C(394)), ("Media player", _C(387)),
    ("Play / Pause", _C(205)), ("Stop", _C(183)), ("Previous track", _C(182)), ("Next track", _C(181)),
    ("Volume +", _C(233)), ("Volume -", _C(234)), ("Mute", _C(226)),
    ("Browser home", _C(547)), ("Browser refresh", _C(551)), ("Browser forward", _C(549)),
    ("Browser back", _C(548)), ("Favorites", _C(554)), ("Search", _C(545)),
)

FUNCTIONS = (
    ("Restore factory settings", _F(1)), ("Bluetooth channel 1", _F(2)), ("Bluetooth channel 2", _F(3)),
    ("Bluetooth channel 3", _F(4)), ("Wireless reconnect", _F(5)), ("Check battery", _F(7)),
    ("Light effect switch", _F(11)), ("Light color switch", _F(12)), ("Brightness +", _F(13)),
    ("Brightness -", _F(14)), ("Light speed +", _F(15)), ("Light speed -", _F(16)),
    ("Turn off lights", _F(17)), ("Lock Win", _F(22)), ("Open driver", _F(75)),
    ("SOCD on/off", _F(102)), ("CMD lock", _F(158)),
)

PALETTES = (("Basic", BASIC), ("Extended", EXTENDED), ("Special", SPECIAL), ("Functions", FUNCTIONS))

USAGE_NAMES = {}
for _label, _act in BASIC + EXTENDED:
    USAGE_NAMES.setdefault(_act.b2, _label)
USAGE_NAMES[175] = "Fn"
_CONSUMER_NAMES = {a.consumer_usage: label for label, a in SPECIAL if a.page == kc.PAGE_CONSUMER}
_MOUSE_NAMES = {(a.b1, a.b2): label for label, a in SPECIAL if a.page == kc.PAGE_MOUSE}
_FUNC_NAMES = {a.func_id: label for label, a in FUNCTIONS}
_FUNC_NAMES.update({6: "F-key switch", 8: "Windows mode", 9: "Mac mode", 10: "Android mode",
                    31: "USB mode", 32: "Light direction"})
MOUSE_BUTTON_NAMES = {1: "Left button", 2: "Right button", 4: "Middle button", 8: "Back button", 16: "Forward button"}


def key_name(value):
    """Keycap label of a physical key."""
    return tr(KEYS[value][0])


def usage_name(usage):
    name = USAGE_NAMES.get(usage)
    return tr(name) if name else tr("Key 0x{:02X}").format(usage)


def action_label(action, macro_names=None):
    """Short text for a key slot, as shown on the keycap."""
    p = action.page
    if p == kc.PAGE_DEFAULT:
        return ""
    if p == kc.PAGE_KEYBOARD:
        return usage_name(action.b2)
    if p == kc.PAGE_CONSUMER:
        name = _CONSUMER_NAMES.get(action.consumer_usage)
        return tr(name) if name else tr("Media 0x{:X}").format(action.consumer_usage)
    if p == kc.PAGE_MOUSE:
        return tr(_MOUSE_NAMES.get((action.b1, action.b2), "Mouse"))
    if p == kc.PAGE_FUNC:
        name = _FUNC_NAMES.get(action.func_id)
        return tr(name) if name else tr("Function {}").format(action.func_id)
    if p == kc.PAGE_MACRO:
        name = (macro_names or {}).get(action.b1) or f"M{action.b1 + 1}"
        return tr("Macro: {}").format(name)
    if p == kc.PAGE_SOCD:
        return "SOCD"
    return f"Action {p:02X}"


def default_action(value):
    """What the key does out of the box (used when a slot is restored)."""
    usage = KEYS[value][1]
    if usage:
        return _K(usage)
    return {96: _C(402), 15: _C(226), 14: _C(234), 13: _C(233)}[value]
