"""Polish user interface."""
import ast
from pathlib import Path

import pytest

import i18n
import keyboard_config as kc
import keyboard_layout as layout
from conftest import wait_until

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    i18n.set_language(i18n.ENGLISH)


def test_every_translated_text_exists():
    """Each tr("...") literal in the code has a Polish translation."""
    missing = set()
    for name in ("panel.py", "tray_app.py", "keyboard_layout.py"):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                if node.args[0].value not in i18n.PL:
                    missing.add(node.args[0].value)
    assert not missing


def test_data_names_are_translated():
    names = [m.name for m in kc.LIGHTING_MODES] + [t for _, t in kc.SOCD_MODES + kc.MACRO_MODES]
    names += [label for _, entries in layout.PALETTES[2:] for label, _ in entries]
    names += list(kc.DIRECTION_NAMES.values()) + list(layout.MOUSE_BUTTON_NAMES.values())
    names += [title for title, _ in layout.PALETTES]
    assert [n for n in names if n not in i18n.PL] == []


def test_resolve_auto(monkeypatch):
    class Locale:
        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

    monkeypatch.setattr(i18n.QLocale, "system", staticmethod(lambda: Locale("pl_PL")))
    assert i18n.resolve(i18n.AUTO) == i18n.POLISH
    monkeypatch.setattr(i18n.QLocale, "system", staticmethod(lambda: Locale("de_DE")))
    assert i18n.resolve(i18n.AUTO) == i18n.ENGLISH


def test_polish_labels():
    i18n.set_language(i18n.POLISH)
    assert layout.action_label(kc.KeyAction.consumer(233)) == "Głośność+"
    assert layout.action_label(kc.KeyAction.function(22)) == "Zablokuj klawisz Win"
    assert layout.key_name(83) == "Spacja"
    assert layout.key_name(49) == "A"


def test_switch_language_rebuilds_menu_and_panel(app, panel):
    panel.tabs.setCurrentIndex(1)
    old_panel = panel
    app.on_language(i18n.POLISH)
    assert app.settings.language == "pl"
    assert app.menu.defaultAction().text() == "Panel klawiatury..."
    assert app.connection_info.text() == "Klawiatura połączona (Odbiornik 2,4 GHz)"
    new = app.panel
    assert new is not old_panel and new.isVisible()
    assert new.config is old_panel.config                 # no second read of the keyboard
    assert new.tabs.tabText(0) == "Klawisze" and new.tabs.currentIndex() == 1
    assert new.mode_group.button(1).text() == "Kolor statyczny"
    assert new.keys_view.labels[83] == "Spacja"
    app.on_language(i18n.ENGLISH)
    assert app.menu.defaultAction().text() == "Keyboard panel..."
    assert wait_until(lambda: app.panel.tabs.tabText(0) == "Keys")


def test_language_from_panel(app, panel):
    panel.language_combo.setCurrentIndex(panel.language_combo.findData("pl"))
    panel.language_combo.activated.emit(panel.language_combo.currentIndex())
    assert wait_until(lambda: app.panel is not panel)
    assert app.panel.tabs.tabText(4) == "Ustawienia"
    assert [a.data() for a in app.language_group.actions() if a.isChecked()] == ["pl"]
