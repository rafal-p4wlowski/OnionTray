"""Keyboard panel end to end: tray app + panel + device thread + fake receiver."""
from PyQt6.QtWidgets import QSystemTrayIcon

import keyboard_config as kc
from conftest import wait_idle, wait_until

CLICK = QSystemTrayIcon.ActivationReason.Trigger


def led_mode(receiver):
    return kc.LedEffect.decode(receiver.memory[0x13]).mode


def slot(receiver, cmd, value):
    return receiver.memory[cmd][value * 4:value * 4 + 4]


def test_left_click_opens_panel(app):
    assert app.panel is None
    app.on_tray_activated(CLICK)
    assert app.panel is not None and app.panel.isVisible()
    assert wait_until(lambda: app.panel.config is not None)
    app.on_tray_activated(CLICK)            # second click reuses the window
    assert app.panel.isVisible()


def test_menu_has_panel_entry(app):
    entry = app.menu.defaultAction()
    assert entry.text() == "Keyboard panel..."
    entry.trigger()
    assert app.panel.isVisible()


def test_panel_shows_device_state(panel):
    assert panel.config.info.firmware == "1.25"
    assert "firmware 1.25" in panel.subtitle.text() and "battery 80%" in panel.subtitle.text()
    assert panel.mode_group.checkedId() == 11
    assert panel.sleep_check.isChecked() and panel.sleep_slider.value() == 3
    assert panel.delay_level_group.checkedId() == 2


def test_remap_key(panel, receiver):
    panel._select_key(49)                                   # A
    panel._assign_action(kc.KeyAction.consumer(0xCD))       # Play/Pause
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 49) == [3, 0xCD, 0, 0]
    assert panel.keys_view.labels[49] == "Play / Pause" and 49 in panel.keys_view.marked
    panel._restore_key()
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 49) == [2, 0, 4, 0]


def test_fn_layer_is_separate(panel, receiver):
    panel.layer_group.button(1).click()
    assert set(range(1, 13)) <= panel.keys_view.disabled    # F1-F12 locked on the Fn layer
    panel._select_key(50)
    panel._assign_action(kc.KeyAction.function(17))         # turn off lights
    assert wait_idle(panel)
    assert slot(receiver, 0x16, 50) == [0x0D, 0, 0, 17]
    assert slot(receiver, 0x12, 50) == [2, 0, 22, 0]


def test_lighting_changes(panel, receiver):
    panel.mode_group.button(1).click()                     # Static Bright
    panel._set_color(panel.current_color.fromRgb(255, 0, 0))
    panel.brightness_slider.setValue(3)
    assert wait_idle(panel)
    led = kc.LedEffect.decode(receiver.memory[0x13])
    assert (led.mode, led.rainbow, led.brightness) == (1, False, 3)
    assert receiver.led_color == [255, 0, 0]
    assert panel.led_memory.color() == (255, 0, 0)
    panel.led_on.setChecked(False)
    assert wait_idle(panel)
    assert led_mode(receiver) == kc.LED_OFF
    panel.led_on.setChecked(True)
    assert wait_idle(panel)
    assert led_mode(receiver) == 1                         # previous effect comes back


def test_lighting_writes_are_debounced(panel, receiver):
    receiver.packets.clear()
    for v in (1, 2, 3, 4, 5):
        panel.speed_slider.setValue(v)
    assert wait_idle(panel)
    assert len(receiver.sets(0x13)) == 1


def test_custom_key_colours(panel, receiver):
    panel.mode_group.button(kc.LED_CUSTOM).click()
    assert not panel.color_view.isHidden()
    panel._set_color(panel.current_color.fromRgb(0, 255, 0))
    panel._paint_key(49)
    assert wait_idle(panel)
    assert led_mode(receiver) == kc.LED_CUSTOM
    assert slot(receiver, 0x14, 49) == [49, 0, 255, 0]


def test_custom_key_turn_off(panel, receiver):
    panel.mode_group.button(kc.LED_CUSTOM).click()
    panel._set_color(panel.current_color.fromRgb(255, 0, 0))
    panel._fill_all()
    assert wait_idle(panel)
    assert slot(receiver, 0x14, 50) == [50, 255, 0, 0]
    panel.color_view.key_right_clicked.emit(50)             # right click turns one key off
    assert wait_idle(panel)
    assert slot(receiver, 0x14, 50) == [50, 0, 0, 0] and slot(receiver, 0x14, 49) == [49, 255, 0, 0]
    panel.eraser_btn.setChecked(True)                       # eraser: left click turns keys off
    panel.color_view.key_clicked.emit(49)
    assert wait_idle(panel)
    assert slot(receiver, 0x14, 49) == [49, 0, 0, 0]
    panel.eraser_btn.setChecked(False)
    panel.all_off_btn.click()
    assert wait_idle(panel)
    assert all(receiver.memory[0x14][v * 4 + 1:v * 4 + 4] == [0, 0, 0] for v in range(111))


def test_settings_tab_writes(panel, receiver):
    panel.sleep_slider.setValue(12)
    panel.delay_level_group.button(4).click()
    assert wait_idle(panel)
    assert receiver.memory[0x11][3:5] == [12, 4]
    panel.sleep_check.setChecked(False)
    assert wait_idle(panel)
    assert receiver.memory[0x11][3] == 0


def test_factory_socd_is_shown(panel):
    assert panel.socd_table.rowCount() == 1                 # A/D from the factory


def test_socd_add_change_remove(panel, receiver, no_modal_dialogs):
    panel._add_socd()                                       # A/D already paired: refused
    assert no_modal_dialogs and panel.socd_table.rowCount() == 1
    panel._remove_socd((49, 51))
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 49) == [2, 0, 4, 0] and slot(receiver, 0x12, 51) == [2, 0, 7, 0]
    panel.socd_key1.setCurrentIndex(panel.socd_key1.findText("A"))
    panel.socd_key2.setCurrentIndex(panel.socd_key2.findText("D"))
    panel.socd_mode.setCurrentIndex(panel.socd_mode.findData(kc.SOCD_NEUTRAL))
    panel._add_socd()
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 49) == slot(receiver, 0x12, 51) == [0x0B, 4, 4, 7]
    assert panel.socd_table.rowCount() == 1
    panel._set_socd_slots((49, 51), kc.KeyAction.socd(kc.SOCD_KEY1, 4, 7))
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 51) == [0x0B, 1, 4, 7]
    panel._remove_socd((49, 51))
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 49) == [2, 0, 4, 0] and slot(receiver, 0x12, 51) == [2, 0, 7, 0]
    assert panel.socd_table.rowCount() == 0


def test_replacing_a_socd_key_frees_its_partner(panel, receiver):
    panel._set_socd_slots((49, 51), kc.KeyAction.socd(3, 4, 7))
    panel._select_key(49)
    panel._assign_action(kc.KeyAction.key(20))
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 49) == [2, 0, 20, 0] and slot(receiver, 0x12, 51) == [2, 0, 7, 0]


def test_macro_create_save_and_assign(panel, receiver):
    panel._new_macro(name="Hello")
    panel.add_target.setCurrentIndex(panel.add_target.findText("H"))
    panel._add_manual_action()
    assert panel.event_table.rowCount() == 2
    panel._save_macros()
    assert wait_idle(panel)
    assert receiver.memory[0x15][0:4] == [144, 1, 0, 0]
    assert receiver.memory[0x15][400:412] == [4, 0, 0, 0, 10, 0, 11, 0xB0, 10, 0, 11, 0x30]
    assert panel.assign_macro_combo.currentText() == "Hello"
    panel._select_key(0)
    panel._assign_macro()
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 0) == [0x06, 0, 0, 0]
    assert panel.keys_view.labels[0] == "Macro: Hello"


def test_restore_layer_uses_factory_tables(panel, receiver):
    panel._select_key(0)
    panel._assign_action(kc.KeyAction.key(104))
    panel._remove_socd((49, 51))
    assert wait_idle(panel)
    panel._restore_layer()
    assert wait_idle(panel)
    assert slot(receiver, 0x12, 0) == [2, 0, 41, 0]
    assert slot(receiver, 0x12, 49) == [0x0B, 3, 4, 7]       # factory SOCD pair is back
    assert slot(receiver, 0x12, 112) == [2, 0, 133, 0]      # hidden slots kept


def test_remembered_colour_is_shown(app, monkeypatch):
    """The keyboard reports FD FD FD; the panel shows the colour it set last."""
    import app_settings
    monkeypatch.setattr(app_settings.LedColorMemory, "color", lambda self: (10, 20, 30))
    app.show_panel()
    assert wait_until(lambda: app.panel.config is not None)
    assert app.panel.config.led.color == (10, 20, 30)


def test_reload_reads_saved_macros(panel, receiver):
    panel._new_macro(name="Two")
    panel._add_manual_action()
    panel._save_macros()
    assert wait_idle(panel)
    panel.config = None
    panel.reload()
    assert wait_until(lambda: panel.config is not None)
    assert len(panel.config.macros[0].events) == 2


def test_app_settings_sync_both_ways(app, panel):
    panel.poll_combo.setCurrentIndex(panel.poll_combo.findData(300))
    panel.poll_combo.activated.emit(panel.poll_combo.currentIndex())
    assert app.settings.poll_interval_s == 300
    assert [a.data() for a in app.poll_group.actions() if a.isChecked()] == [300]
    next(a for a in app.low_group.actions() if a.data() == 30).trigger()
    assert panel.low_combo.currentData() == 30


def test_asleep_keyboard_shows_error(app, receiver):
    receiver.awake = False
    app.show_panel()
    assert wait_until(lambda: app.panel.error_label.isVisibleTo(app.panel), timeout=15)
    assert "Wake it up" in app.panel.error_label.text()
    assert not app.panel.tabs.widget(0).isEnabled()
    receiver.awake = True
    app.panel.reload()
    assert wait_until(lambda: app.panel.config is not None, timeout=10)
    assert app.panel.tabs.widget(0).isEnabled()
