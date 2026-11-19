"""Configuration protocol: codecs and the session against the fake receiver."""
import pytest

import keyboard_config as kc
import keyboard_layout as layout
import keyboard_logic as kl

# Real answers of an ALU104 Onionite BL 2.4G (firmware 1.25), data bytes only.
REAL_INFO = [0x40, 0, 0, 0x0C, 0x45, 0x0C, 0xCC, 0x80, 0x25, 0x01, 0xFF, 0xFF, 0x07, 0, 0x1B, 0,
             0x02, 0x49, 0, 0, 0, 0, 0, 0]
REAL_LED = [0x02, 0xFD, 0xFD, 0xFD, 0, 0, 0, 0, 0x01, 0x05, 0x04, 0, 0, 0, 0, 0]


def test_device_info_decodes_real_dump():
    info = kc.DeviceInfo.decode(REAL_INFO)
    assert (info.vid, info.pid, info.firmware, info.battery) == (0x0C45, 0x80CC, "1.25", 73)


def test_led_effect_round_trip():
    led = kc.LedEffect.decode(REAL_LED)
    assert (led.mode, led.color, led.rainbow, led.brightness, led.speed) == (2, (253, 253, 253), True, 5, 4)
    # SET carries 0xFF in byte 4 and the AA 55 check code, like the web driver.
    assert led.encode() == [2, 253, 253, 253, 0xFF, 0, 0, 0, 1, 5, 4, 0, 0, 0, 0xAA, 0x55]
    assert kc.LedEffect.decode(led.encode()) == led


def test_key_action_encoding():
    assert kc.KeyAction.key(4).encode() == [0x02, 0, 4, 0]
    assert kc.KeyAction.consumer(0x192).encode() == [0x03, 0x92, 0x01, 0]
    assert kc.KeyAction.mouse(kc.MOUSE_WHEEL, 255).encode() == [0x01, 3, 255, 0]
    assert kc.KeyAction.function(22).encode() == [0x0D, 0, 0, 22]
    assert kc.KeyAction.macro(5, kc.MACRO_REPEAT, 3).encode() == [0x06, 5, 1, 3]
    assert kc.KeyAction.macro(5, kc.MACRO_ONCE, 3).encode() == [0x06, 5, 0, 0]
    assert kc.KeyAction.socd(kc.SOCD_LAST, 4, 7).encode() == [0x0B, 3, 4, 7]


def test_table_round_trip_and_socd_pairs():
    actions = [kc.KeyAction()] * kc.SLOTS
    actions[49] = actions[51] = kc.KeyAction.socd(3, 4, 7)
    actions[0] = kc.KeyAction.key(41)
    data = kc.encode_table(actions)
    assert len(data) == 512 and data[49 * 4:49 * 4 + 4] == [0x0B, 3, 4, 7]
    assert kc.decode_table(data) == actions
    assert kc.socd_pairs(actions) == [(3, 4, 7, [49, 51])]


def test_macro_encoding_layout():
    a_down = kc.MacroEvent(4, True, 20)
    a_up = kc.MacroEvent(4, False, 30)
    click = kc.MacroEvent(1, True, 5, mouse=True)
    index, bodies = kc.encode_macros({3: kc.Macro(3, [a_down, a_up]), 0: kc.Macro(0, [click])})
    assert len(index) == 400
    assert index[0:4] == [144, 1, 0, 0]               # macro 0 at address 400
    assert index[12:16] == [152, 1, 0, 0]             # macro 3 at 400 + 8
    assert bodies[:8] == [2, 0, 0, 0, 5, 0, 1, 0x90]  # count*2, then delay, button, mouse press
    assert bodies[8:20] == [4, 0, 0, 0, 20, 0, 4, 0xB0, 30, 0, 4, 0x30]
    assert kc.MacroEvent.decode(a_down.encode()) == a_down
    assert kc.MacroEvent.decode(click.encode()) == click


def test_macro_space_is_checked():
    events = [kc.MacroEvent(4, i % 2 == 0) for i in range(700)]
    with pytest.raises(ValueError):
        kc.encode_macros({0: kc.Macro(0, events)})


def test_settings_fields():
    st = kc.Settings([0, 1, 2, 3, 2] + [9] * 51)
    st.sleep_minutes = 45
    st.key_delay = 9
    assert st.sleep_minutes == 30 and st.key_delay == 5
    assert st.encode()[:5] == [0, 1, 2, 30, 5] and st.encode()[5:] == [9] * 51   # unknown bytes kept


def test_write_block_chunks_and_last_flag(receiver):
    with kl.open_session() as s:
        receiver.packets.clear()
        s.write_block(0x22, list(range(256)) * 2)
        packets = receiver.sets(0x12)
        assert len(packets) == 22
        assert [p[3] | p[4] << 8 for p in packets] == list(range(0, 512, 24))
        assert [p[6] for p in packets] == [0] * 21 + [1]
        assert packets[-1][2] == 8                                   # last chunk is 8 bytes
        receiver.packets.clear()
        s.write_block(0x25, [0] * 400, final=False)
        assert all(p[6] == 0 for p in receiver.sets(0x15))


def test_read_config_from_fake(receiver):
    with kl.open_session() as s:
        cfg = kc.read_config(s)
    assert cfg.info.firmware == "1.25" and cfg.info.battery == 80
    assert cfg.settings.sleep_minutes == 3 and cfg.settings.key_delay == 2
    assert cfg.led.mode == 11 and cfg.led.rainbow            # factory effect
    assert cfg.layers[kc.LAYER_NORMAL][49] == kc.KeyAction.socd(3, 4, 7)   # factory SOCD A/D
    assert cfg.layers[kc.LAYER_FN][81] == kc.KeyAction.function(22)
    assert cfg.macros == {}


def test_writes_reach_the_device(receiver):
    with kl.open_session() as s:
        cfg = kc.read_config(s)
        cfg.led.mode, cfg.led.color, cfg.led.rainbow = 1, (255, 0, 0), False
        kc.write_led(s, cfg.led)
        cfg.settings.sleep_minutes = 10
        kc.write_settings(s, cfg.settings)
        cfg.layers[kc.LAYER_NORMAL][0] = kc.KeyAction.consumer(0xE9)
        kc.write_layer(s, kc.LAYER_NORMAL, cfg.layers[kc.LAYER_NORMAL])
        macros = {7: kc.Macro(7, [kc.MacroEvent(4, True, 15), kc.MacroEvent(4, False, 0)])}
        kc.write_macros(s, macros)
        again = kc.read_config(s)
    assert again.led.mode == 1 and not again.led.rainbow
    assert again.led.color == kc.REPORTED_COLOR and receiver.led_color == [255, 0, 0]
    assert again.settings.sleep_minutes == 10 and again.settings.key_delay == 2
    assert again.layers[kc.LAYER_NORMAL][0] == kc.KeyAction.consumer(0xE9)
    assert again.layers[kc.LAYER_NORMAL][49] == kc.KeyAction.socd(3, 4, 7)
    assert again.macros == macros


def test_stored_led_modes_are_mapped(receiver):
    """The firmware keeps "off" as 21 and "custom" as 20."""
    with kl.open_session() as s:
        for mode in (kc.LED_OFF, kc.LED_CUSTOM, 5):
            kc.write_led(s, kc.LedEffect(mode=mode))
            assert kc.LedEffect.decode(s.request(kc.CMD_LED_EFFECT, kc.LED_SIZE)).mode == mode
    assert kc.LedEffect.decode([21] + [0] * 15).mode == kc.LED_OFF


def test_direction_survives_one_bit_storage(receiver):
    with kl.open_session() as s:
        for mode, direction in ((10, kc.DIRECTION_UP), (10, kc.DIRECTION_DOWN),
                                (11, kc.DIRECTION_LEFT), (11, kc.DIRECTION_RIGHT)):
            kc.write_led(s, kc.LedEffect(mode=mode, direction=direction))
            assert kc.LedEffect.decode(s.request(kc.CMD_LED_EFFECT, kc.LED_SIZE)).direction == direction


def test_factory_reset(receiver):
    with kl.open_session() as s:
        cfg = kc.read_config(s)
        cfg.settings.sleep_minutes = 20
        kc.write_settings(s, cfg.settings)
        kc.factory_reset(s)
        assert kc.read_config(s).settings.sleep_minutes == 3
    assert receiver.factory_resets == 1
    assert any(p[:3] == [0xAA, 0x0F, 0xFF] for p in receiver.packets)


def test_asleep_keyboard_raises(receiver):
    receiver.awake = False
    with pytest.raises(kl.KeyboardError):
        with kl.open_session() as s:
            kc.read_config(s)


def test_no_receiver_raises(receiver):
    receiver.present = False
    with pytest.raises(kl.KeyboardError):
        with kl.open_session():
            pass


def test_layout_covers_every_key():
    values = [g[0] for g in layout.GEOMETRY]
    assert sorted(values) == sorted(layout.KEYS) and len(values) == 108
    assert all(layout.default_action(v).page in (kc.PAGE_KEYBOARD, kc.PAGE_CONSUMER) for v in layout.KEYS)


def test_action_labels():
    assert layout.action_label(kc.KeyAction.key(4)) == "A"
    assert layout.action_label(kc.KeyAction.consumer(233)) == "Volume +"
    assert layout.action_label(kc.KeyAction.function(22)) == "Lock Win"
    assert layout.action_label(kc.KeyAction.macro(2), {2: "Build"}) == "Macro: Build"
    assert layout.action_label(kc.KeyAction.socd(3, 4, 7)) == "SOCD"
    assert layout.action_label(kc.KeyAction()) == ""
