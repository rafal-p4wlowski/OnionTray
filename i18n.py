"""User interface language. English texts are the keys; tr() returns the
translation for the current language. Polish names of effects, functions and
keys follow the Polish version of the vendor web driver (app.darkproject.eu).
"""
from PyQt6.QtCore import QLocale

AUTO, ENGLISH, POLISH = "auto", "en", "pl"
LANGUAGES = ((AUTO, "System"), (ENGLISH, "English"), (POLISH, "Polski"))

_current = ENGLISH


def resolve(code):
    if code == AUTO:
        return POLISH if QLocale.system().name().lower().startswith("pl") else ENGLISH
    return code if code in (ENGLISH, POLISH) else ENGLISH


def set_language(code):
    global _current
    _current = resolve(code)


def current():
    return _current


def tr(text):
    if _current == POLISH:
        return PL.get(text, text)
    return text


PL = {
    # --- tray ---
    "Looking for keyboard...": "Szukam klawiatury...",
    "Keyboard panel...": "Panel klawiatury...",
    "Refresh now": "Odśwież teraz",
    "Quit": "Zakończ",
    "Settings": "Ustawienia",
    "Start with Windows": "Uruchamiaj z systemem Windows",
    "Check Bluetooth connection": "Sprawdzaj połączenie Bluetooth",
    "Battery refresh": "Odświeżanie baterii",
    "Low battery warning": "Ostrzeżenie o niskiej baterii",
    "Language": "Język",
    "System": "Systemowy",
    "Disabled": "Wyłączone",
    "Version {}": "Wersja {}",
    "Keyboard connected ({})": "Klawiatura połączona ({})",
    "Keyboard asleep / not responding": "Klawiatura uśpiona / nie odpowiada",
    "Keyboard off / out of range": "Klawiatura wyłączona / poza zasięgiem",
    "Keyboard not found": "Nie znaleziono klawiatury",
    "Battery level: {}": "Poziom baterii: {}",
    "Charging status: {}": "Ładowanie: {}",
    "Last reading: {}": "Ostatni odczyt: {}",
    "Keyboard battery: {}%": "Bateria klawiatury: {}%",
    "Keyboard battery low": "Niski poziom baterii klawiatury",
    "Battery level: {}%. Connect the USB cable.": "Poziom baterii: {}%. Podłącz kabel USB.",
    "Charging": "Ładuje się",
    "Not charging": "Nie ładuje się",
    "Fully charged": "Naładowana",
    "USB cable": "Kabel USB",
    "2.4G receiver": "Odbiornik 2,4 GHz",
    "Bluetooth": "Bluetooth",

    # --- panel: general ---
    "OnionTray - Keyboard": "OnionTray - Klawiatura",
    "Keys": "Klawisze",
    "Lighting": "Podświetlenie",
    "Macros": "Makra",
    "Reload": "Odczytaj ponownie",
    "Reading keyboard settings...": "Odczytuję ustawienia klawiatury...",
    "Cannot read the keyboard: {}.\nWake it up by pressing a key, then click Reload.":
        "Nie można odczytać klawiatury: {}.\nWybudź ją dowolnym klawiszem i kliknij Odczytaj ponownie.",
    "Settings read at {}": "Ustawienia odczytane o {}",
    "Working...": "Zapisuję...",
    "{} failed: {}": "{} - błąd: {}",
    "{} saved at {}": "{} - zapisano o {}",
    "not connected": "nie połączono",
    "battery {}%": "bateria {}%",
    "asleep": "uśpiona",
    "firmware {}": "firmware {}",

    # --- panel: keys ---
    "Normal layer": "Warstwa bazowa",
    "Fn layer": "Warstwa Fn",
    "Click a key, then pick what it should do.": "Kliknij klawisz, a potem wybierz, co ma robić.",
    "Restore key": "Przywróć klawisz",
    "Restore layer": "Przywróć warstwę",
    "Restore every key of the {} layer to its default?":
        "Przywrócić domyślne działanie wszystkich klawiszy warstwy {}?",
    "normal": "bazowej",
    "Fn": "Fn",
    "default": "domyślny",
    "Basic": "Znaki podstawowe",
    "Extended": "Znaki rozszerzone",
    "Special": "Znaki specjalne",
    "Functions": "Klawisze funkcyjne",
    "Macro": "Makro",
    "Playback": "Odtwarzanie",
    "Times": "Razy",
    "Assign macro": "Przypisz makro",
    "Record macros on the Macros tab first.": "Najpierw nagraj makra w zakładce Makra.",
    "Select a key on the keyboard first.": "Najpierw wybierz klawisz na klawiaturze.",
    "There are no macros yet.": "Nie ma jeszcze żadnych makr.",
    "Key assignment": "Przypisanie klawisza",
    "Macro: {}": "Makro: {}",

    # --- panel: lighting ---
    "Lighting effects": "Efekty podświetlenia",
    "Lights on": "Podświetlenie włączone",
    "Effect": "Edycja efektu",
    "Colour mode": "Tryb kolorów",
    "Single colour": "Pojedynczy kolor",
    "RGB (rainbow)": "RGB",
    "Brightness": "Jasność podświetlenia",
    "Speed": "Prędkość podświetlenia",
    "Direction": "Kierunek podświetlenia",
    "Colour": "Ustawienia kolorów",
    "Pick...": "Wybierz...",
    "Lighting colour": "Kolor podświetlenia",
    "Custom mode: click keys on the keyboard above to paint them with this colour. "
    "Right-click a key to turn it off.":
        "Tryb własny: klikaj klawisze na klawiaturze powyżej, aby nadać im ten kolor. "
        "Prawy klik wyłącza podświetlenie klawisza.",
    "Eraser (turn keys off)": "Gumka (wyłącz klawisze)",
    "Fill all keys": "Wypełnij wszystkie",
    "Turn all keys off": "Wyłącz wszystkie",
    "Key colours": "Kolory klawiszy",
    "Right": "W prawo",
    "Left": "W lewo",
    "Up": "W górę",
    "Down": "W dół",
    "Static Bright": "Kolor statyczny",
    "Single Point On": "Włączenie pojedynczego klawisza",
    "Single Point Off": "Wyłączenie pojedynczego klawisza",
    "Starry Sky": "Gwiaździste niebo",
    "Snowfall": "Śnieżyca",
    "Floral Competition": "Kwiatowy blask",
    "Dynamic Breathing": "Dynamiczne oddychanie",
    "Spectrum Cycle": "Cykl kolorów spektrum",
    "Color Fountain": "Kolorowa fontanna",
    "Colorful Interchange": "Wielokolorowe fale",
    "Flowing with the Waves": "Przepływ fal",
    "Turning Peaks": "Wężykowe góry",
    "One Touch to Fire": "Jeden dotyk – ogień",
    "Two Birds with One Stone": "Dwa ptaki jednym strzałem",
    "Ripples Spread": "Rozchodzące się fale",
    "Endless Flow": "Ciągły przepływ",
    "Layered Mountains": "Warstwowe góry",
    "Gentle Rain and Wind": "Mżawka",
    "Back and Forth": "Tam i z powrotem",
    "Custom (per key)": "Własny (każdy klawisz)",

    # --- panel: macros ---
    "New": "Nowe",
    "Rename": "Zmień nazwę",
    "Copy": "Kopiuj",
    "Delete": "Usuń",
    "Record": "Nagrywanie",
    "Record real intervals": "Nagrywaj odstępy czasu",
    "No delay between actions": "Bez odstępów między akcjami",
    "Fixed delay": "Stały odstęp",
    "Start recording": "Rozpocznij nagrywanie",
    "Stop recording": "Zatrzymaj nagrywanie",
    "While recording, press keys on the keyboard; the panel window must have focus. "
    "Recorded actions are added at the selected row.":
        "Podczas nagrywania naciskaj klawisze; okno panelu musi być aktywne. "
        "Nagrane akcje są wstawiane za zaznaczonym wierszem.",
    "Add action": "Dodaj akcję",
    "Key": "Klawisz",
    "Mouse button": "Przycisk myszy",
    "Add press + release": "Dodaj wciśnięcie + zwolnienie",
    "Actions": "Nagrane akcje",
    "Action": "Akcja",
    "Delay (ms)": "Opóźnienie (ms)",
    "Move up": "W górę",
    "Move down": "W dół",
    "Remove": "Usuń",
    "Clear": "Wyczyść",
    "Save macros to keyboard": "Zapisz makra w klawiaturze",
    "Unsaved changes": "Niezapisane zmiany",
    "Save the macro changes to the keyboard before closing?": "Zapisać zmiany makr w klawiaturze przed zamknięciem?",
    "Macro {}": "Makro {}",
    "Press": "Klawisz wciśnięty",
    "Release": "Klawisz zwolniony",
    "Mouse": "Mysz",
    "All 100 macro slots are used.": "Wszystkie 100 miejsc na makra jest zajętych.",
    "New macro": "Nowe makro",
    "Rename macro": "Zmień nazwę makra",
    "Name:": "Nazwa:",
    "{} (copy)": "{} (kopia)",
    "Delete macro": "Usuń makro",
    "Delete this macro?": "Usunąć to makro?",
    "\nIt is assigned to {} key(s); they will be restored to their defaults.":
        "\nJest przypisane do klawiszy: {}; przywrócę ich domyślne działanie.",
    "Play once": "Odtwórz raz",
    "Press again to stop": "Przełącz odtwarzanie",
    "Repeat N times": "Powtórz N razy",
    "Left button": "Lewy przycisk",
    "Right button": "Prawy przycisk",
    "Middle button": "Środkowy przycisk",
    "Back button": "Przycisk wstecz",
    "Forward button": "Przycisk dalej",

    # --- panel: SOCD ---
    "SOCD watches two keys (e.g. A and D) and decides what is sent when both are held. "
    "Up to 40 pairs. A key can be in one pair only.":
        "SOCD monitoruje dwa klawisze (np. A i D) i decyduje, co zostanie wysłane, gdy oba są wciśnięte. "
        "Maksymalnie 40 par. Klawisz może należeć tylko do jednej pary.",
    "Key 1": "Klawisz 1",
    "Key 2": "Klawisz 2",
    "Mode": "Tryb działania",
    "Add pair": "Dodaj parę",
    "Current pairs": "Aktualne przypisania",
    "Choose two different keys.": "Wybierz dwa różne klawisze.",
    "There are already 40 pairs.": "Jest już 40 par.",
    "One of these keys is already in a SOCD pair. Remove it first.":
        "Jeden z tych klawiszy jest już w parze SOCD. Najpierw ją usuń.",
    "Last input priority": "Priorytet ostatniego wejścia",
    "Key 1 priority": "Priorytet klawisza 1",
    "Key 2 priority": "Priorytet klawisza 2",
    "Neutral (both pressed = none)": "Tryb anulowania (oba = żaden)",

    # --- panel: settings ---
    "Keyboard": "Klawiatura",
    "Sleep mode (turn the lights off and sleep when idle)":
        "Tryb uśpienia (wyłącz podświetlenie i uśpij przy bezczynności)",
    "{} min": "{} min",
    "Key response time": "Czas debouncingu",
    "A lower level reacts faster; if keys start repeating, raise it.":
        "Niższy poziom reaguje szybciej; jeśli klawisze zaczną się powtarzać, zwiększ go.",
    "Level {}": "Poziom {}",
    "Device {} · firmware {}": "Urządzenie {} · firmware {}",
    "Reset all keyboard settings": "Zresetuj wszystkie ustawienia klawiatury",
    "Reset keyboard": "Reset klawiatury",
    "Reset all keyboard settings (keys, lighting, macros, SOCD) to the factory defaults?":
        "Zresetować wszystkie ustawienia klawiatury (klawisze, podświetlenie, makra, SOCD) do fabrycznych?",
    "Reset": "Reset",

    # --- palette / key names ---
    "Space": "Spacja",
    "Calc": "Kalk.",
    "Vol -": "Głośn. -",
    "Vol +": "Głośn. +",
    "Disabled key": "Wyłączony",
    "Left mouse button": "Lewy przycisk myszy",
    "Middle mouse button": "Środkowy przycisk myszy",
    "Right mouse button": "Prawy przycisk myszy",
    "Mouse scroll up": "Przewijanie myszy w górę",
    "Mouse scroll down": "Przewijanie myszy w dół",
    "Mouse forward": "Przycisk myszy – do przodu",
    "Mouse back": "Przycisk myszy – do tyłu",
    "My Computer": "Mój komputer",
    "Calculator": "Kalkulator",
    "Email": "E-mail",
    "Media player": "Multimedia",
    "Play / Pause": "Odtwórz/Pauza",
    "Stop": "Zatrzymaj odtwarzanie",
    "Previous track": "Poprzedni utwór",
    "Next track": "Następny utwór",
    "Volume +": "Głośność+",
    "Volume -": "Głośność-",
    "Mute": "Wyciszenie",
    "Browser home": "Strona główna",
    "Browser refresh": "Odśwież",
    "Browser forward": "Dalej",
    "Browser back": "Wstecz",
    "Favorites": "Ulubione",
    "Search": "Szukaj",
    "Restore factory settings": "Przywróć ustawienia fabryczne",
    "Bluetooth channel 1": "Kanał Bluetooth 1",
    "Bluetooth channel 2": "Kanał Bluetooth 2",
    "Bluetooth channel 3": "Kanał Bluetooth 3",
    "Wireless reconnect": "Parowanie 2,4 GHz (przytrzymaj)",
    "Check battery": "Sprawdź poziom baterii",
    "Light effect switch": "Przełącznik efektu podświetlenia",
    "Light color switch": "Zmiana koloru podświetlenia",
    "Brightness +": "Zwiększ jasność podświetlenia",
    "Brightness -": "Zmniejsz jasność podświetlenia",
    "Light speed +": "Zwiększ prędkość podświetlenia",
    "Light speed -": "Zmniejsz prędkość podświetlenia",
    "Turn off lights": "Wyłącz podświetlenie",
    "Lock Win": "Zablokuj klawisz Win",
    "Open driver": "Otwórz sterownik",
    "SOCD on/off": "Włącz/wyłącz SOCD",
    "CMD lock": "Blokada CMD",
    "F-key switch": "Przełącznik trybu klawiszy F",
    "Windows mode": "Tryb Windows",
    "Mac mode": "Tryb Mac",
    "Android mode": "Tryb Android",
    "USB mode": "Tryb USB",
    "Light direction": "Kierunek podświetlenia",
    "Function {}": "Funkcja {}",
    "Media 0x{:X}": "Multimedia 0x{:X}",
    "Key 0x{:02X}": "Klawisz 0x{:02X}",
}
