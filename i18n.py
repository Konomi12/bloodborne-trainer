"""Interface languages. The texts in the code are English; other languages translate them here.

The language is the one chosen in the Game tab, otherwise the system's (English if unknown).
"""
import os

import config

LANGUAGES = {"en": "English", "pl": "Polski"}

POLISH = {
    # shortcuts and toggles
    "Save position": "Zapisz pozycję",
    "Load position": "Wczytaj pozycję",
    "Full HP and stamina": "Pełne HP i stamina",
    "No death on/off": "Nieśmiertelność wł./wył.",
    "Repeat last warp": "Powtórz ostatni warp",
    "No death": "Nieśmiertelność",
    "HP never drops below 1": "HP nie spadnie poniżej 1",
    "One-hit kill": "Zabijanie jednym ciosem",
    "Infinite stamina": "Nieskończona stamina",
    "Game flag: applies to every character": "Flaga gry: działa na wszystkie postacie",
    "Infinite bullets": "Nieskończone kule",
    "Shots do not use Quicksilver Bullets": "Strzały nie zużywają Quicksilver Bullets",
    "Invisibility": "Niewidzialność",
    "Enemies cannot see you": "Wrogowie cię nie widzą",
    "Silence": "Cisza",
    "Enemies cannot hear you": "Wrogowie cię nie słyszą",
    "Disable AI": "Wyłącz AI",
    "Enemies stand and do nothing": "Wrogowie stoją i nic nie robią",
    "Enemies do not attack": "Wrogowie nie atakują",
    "Nobody moves": "Nikt się nie rusza",
    "Game flag: includes you": "Flaga gry: obejmuje też ciebie",
    "Nobody takes damage": "Nikt nie dostaje obrażeń",
    "Includes you": "Obejmuje też ciebie",
    "No hits": "Brak trafień",
    "Nobody can die": "Nikt nie może zginąć",
    "Everyone's HP stops at 1": "HP wszystkich zatrzymuje się na 1",
    # window and tabs
    "Looking for the game…": "Szukam gry…",
    "Start game": "Uruchom grę",
    "Player": "Gracz",
    "Travel": "Podróż",
    "Enemies": "Wrogowie",
    "Items": "Itemy",
    "Stats": "Staty",
    "Game": "Gra",
    # player
    "Status": "Stan",
    "Heal": "Ulecz",
    "Die": "Zgiń",
    "Set HP": "Ustaw HP",
    "Set": "Ustaw",
    "Always full HP": "Zawsze pełne HP",
    "Only you; a heavy hit can still kill": "Tylko ty; mocny cios nadal może zabić",
    "Always full stamina": "Zawsze pełna stamina",
    "Only you": "Tylko ty",
    "Infinite items": "Nieskończone przedmioty",
    "Vials, cocktails etc. come back after use (carry at least 2)":
        "Fiolki, koktajle itd. wracają po użyciu (miej min. 2 sztuki)",
    "Cheats": "Ułatwienia",
    # travel
    "Saved position": "Zapisana pozycja",
    "F5 saves, F6 loads (within the same map)": "F5 zapisuje, F6 wczytuje (w tej samej mapie)",
    "Slot {}": "Slot {}",
    "Now": "Teraz",
    "In slot": "W slocie",
    "Save": "Zapisz",
    "Load": "Wczytaj",
    "Restore HP and stamina too": "Wczytuj razem z HP i staminą",
    "Move by (metres)": "Przesuń o (metry)",
    "Up": "Góra",
    "Down": "Dół",
    "Warp to a lamp": "Warp do lampy",
    "Unlit ones too. The target becomes your last lamp.":
        "Także do niezapalonych. Cel staje się twoją ostatnią lampą.",
    "Could not load the lamp list: {}": "Nie wczytałem listy lamp: {}",
    "Go": "Leć",
    "Bosses": "Bossowie",
    "“Go” puts you in front of the fight entrance. “Revive” clears the defeat flag; the boss is "
    "back after “Go”. The pin saves your current spot as your own entrance. Back up your save in "
    "the Game tab before reviving.":
        "„Leć” stawia cię przed wejściem do walki. „Wskrześ” kasuje flagę pokonania; boss wraca "
        "po „Leć”. Pinezka zapisuje twoje obecne miejsce jako własne wejście. Przed "
        "wskrzeszaniem zrób kopię zapisu w zakładce Gra.",
    "Check": "Stan",
    "Revive": "Wskrześ",
    "Defeated": "Pokonany",
    "defeated": "pokonany",
    "alive": "żyje",
    # enemies
    "Behaviour": "Zachowanie",
    "Nearby (closest first)": "W pobliżu (od najbliższego)",
    "Refreshes by itself while this tab is visible":
        "Odświeża się samo, gdy zakładka jest widoczna",
    "Kill": "Zabij",
    "Full": "Pełne",
    "Freeze HP": "Zamroź HP",
    "Go to": "Do niego",
    # items
    "Add an item": "Dodaj przedmiot",
    "Click a group to open it. Story items can break your save.":
        "Kliknij grupę, żeby ją rozwinąć. Przedmioty fabularne mogą popsuć zapis.",
    "Amount": "Ile",
    "Weapons and attire are added one at a time": "Broń i stroje dodają się po jednej sztuce",
    "Weapon upgrade": "Ulepszenie broni",
    "+0 to +10": "+0 do +10",
    "Weapon variant": "Wariant broni",
    "Uncanny and Lost have different gem slots":
        "Uncanny i Lost różnią się miejscami na klejnoty",
    "Popup in game": "Okienko w grze",
    "The game shows the item you received": "Gra pokazuje zdobyty przedmiot",
    "Search by in-game name…": "Szukaj po nazwie z gry…",
    "Could not load the item list: {}": "Nie wczytałem listy przedmiotów: {}",
    "Items: {}": "Pozycje: {}",
    "Add": "Dodaj",
    "Normal": "Zwykła",
    "Uncanny": "Uncanny",
    "Lost": "Lost",
    "Weapons (right hand)": "Broń (prawa ręka)",
    "Firearms, shields and torches (left hand)": "Broń palna, tarcze i pochodnie (lewa ręka)",
    "Attire: head": "Stroje: głowa",
    "Attire: chest": "Stroje: tułów",
    "Attire: arms": "Stroje: ręce",
    "Attire: legs": "Stroje: nogi",
    "Healing and bullets": "Leczenie i kule",
    "Throwables and buffs": "Do rzucania i wzmocnienia",
    "Hunter tools": "Narzędzia łowcy",
    "Upgrade and ritual materials": "Materiały do ulepszeń i rytuałów",
    "Echoes and insight": "Echa i wgląd",
    "Chalices": "Kielichy",
    "Keys and story items (careful)": "Klucze i fabularne (ostrożnie)",
    "Bells and miscellaneous": "Dzwonki i różne",
    "Gestures": "Gesty",
    "Other (may not work)": "Inne (mogą nie działać)",
    # stats
    "Character": "Postać",
    "Changes are saved by the game. HP and stamina update after a reload.":
        "Zmiany zapisują się w grze. HP i stamina przeliczą się po przeładowaniu.",
    "Vitality": "Witalność",
    "Endurance": "Wytrzymałość",
    "Strength": "Siła",
    "Skill": "Zręczność",
    "Bloodtinge": "Skażenie krwi",
    "Arcane": "Wiedza tajemna",
    "Level": "Poziom",
    "Insight": "Wgląd",
    "Blood echoes": "Echa krwi",
    "NG+ cycle": "Cykl NG+",
    "Values from the game": "Wartości z gry",
    "Read": "Odczytaj",
    # game tab
    "Game speed": "Prędkość gry",
    "Quit to main menu": "Wyjdź do menu głównego",
    "Quit": "Wyjdź",
    "A quick reset": "Szybki reset sytuacji",
    "Restore story": "Przywróć fabułę",
    "Restore": "Przywróć",
    "After a Gehrman / Moon Presence fight (a warp does it too)":
        "Po walce z Gehrmanem / Moon Presence (warp też to robi)",
    "Save backup": "Kopia zapisów",
    "Back up": "Zrób kopię",
    "To {}": "Do {}",
    "View": "Widok",
    "Attack hitboxes": "Hitboxy ataków",
    "A yellow mesh shows where and when a hit lands (yours and enemies')":
        "Żółta siatka pokazuje, gdzie i kiedy cios trafia (twój i wrogów)",
    "Shortcuts": "Skróty",
    "Keyboard (in game and in the trainer)": "Klawiatura (w grze i w trainerze)",
    "Gamepad: hold Select/View + D-pad": "Pad: trzymaj Select/View + krzyżak",
    "Up save, down load, left heal, right warp":
        "Góra zapisz, dół wczytaj, lewo ulecz, prawo warp",
    "Setup": "Ustawienia",
    "AppImage or script…": "AppImage lub skrypt…",
    "Folder…": "Folder…",
    "not found: pick it with a button": "nie znalazłem: wskaż przyciskiem",
    "bbport: the AppImage, Bloodborne.sh or bbport_launcher.py":
        "bbport: AppImage, Bloodborne.sh albo bbport_launcher.py",
    "The bbport folder": "Folder bbporta",
    "Saved. Restart the trainer to load the lamp and item lists.":
        "Zapisane. Uruchom trainer ponownie, żeby wczytać listy lamp i przedmiotów.",
    "Saved.": "Zapisane.",
    "Restart the trainer to change the language.":
        "Uruchom trainer ponownie, żeby zmienić język.",
    "Warning": "Uwaga",
    "Do not use in online co-op": "Nie używaj w co-opie online",
    "Flags and speed changes ruin the other player's session":
        "Flagi i prędkość psują sesję drugiej osobie",
    # messages
    "That did not work": "Nie udało się",
    "No death on": "Nieśmiertelność włączona",
    "No death off": "Nieśmiertelność wyłączona",
    "empty": "pusty",
    "cannot read the position": "nie mogę odczytać pozycji",
    "Position saved in slot {}": "Zapisano pozycję w slocie {}",
    "this slot is empty": "ten slot jest pusty",
    "that position is on another map: warp there first":
        "pozycja jest z innej mapy: najpierw zrób warp",
    "This is a late-game fight. The trainer backs up your save, sets the story flags and "
    "restores them when you warp somewhere else.\n\nA real win ends the game and starts NG+. In "
    "practice mode the boss recovers its HP when it drops below 25% and one-hit kill is off.":
        "To walka z końca gry. Trainer zrobi kopię zapisu, ustawi flagi fabuły i przywróci je, "
        "gdy polecisz gdzie indziej.\n\nPrawdziwa wygrana kończy grę i zaczyna NG+. W trybie "
        "treningowym boss odzyskuje HP, gdy spadnie poniżej 25%, a one-shot jest wyłączony.",
    "Cancel": "Anuluj",
    "Killable": "Można go zabić",
    "Practice": "Trening",
    "Story state restored": "Przywrócono stan fabuły",
    "The game moved to a new cycle: not restoring old flags":
        "Gra przeszła do nowego cyklu: starych flag nie przywracam",
    "The boss recovered its HP (practice mode)": "Boss odzyskał HP (tryb treningowy)",
    "no warp yet": "nie było jeszcze warpu",
    "Back to the default entrance": "Wróć do domyślnego wejścia",
    "Save this spot as the entrance to this boss":
        "Zapisz obecne miejsce jako wejście do tego bossa",
    "“Go” will now bring you to this spot": "„Leć” będzie teraz wracać w to miejsce",
    "Default entrance restored": "Przywrócono domyślne wejście",
    "that character is gone": "tej postaci już nie ma",
    "Added {} × {}": "Dodano {} × {}",
    "Added: {}": "Dodano: {}",
    " – there is no {} variant, gave the normal one": " – nie ma wariantu {}, dałem zwykłą",
    "press “Read” first, so you do not write zeros":
        "najpierw „Odczytaj”, żeby nie wpisać zer",
    "press “Read” first": "najpierw „Odczytaj”",
    "bbport not found: pick it in the Game tab": "nie znalazłem bbporta: wskaż go w zakładce Gra",
    "no saves found in {}": "nie widzę zapisów w {}",
    "Backup: {}": "Kopia: {}",
    "The game is already running.": "Gra już działa.",
    "The AppImage is not executable": "AppImage nie ma prawa uruchamiania",
    "Could not start the game": "Nie udało się uruchomić gry",
    "Starting the game…": "Uruchamiam grę…",
    "Where is bbport?": "Gdzie jest bbport?",
    "The trainer could not find bbport. Pick its AppImage, Bloodborne.sh, or the folder with "
    "the source.":
        "Trainer nie znalazł bbporta. Wskaż jego AppImage, Bloodborne.sh albo folder ze "
        "źródłami.",
    "no message": "brak komunikatu",
    "bbport built from source needs cmake: install it with your package manager.":
        "bbport budowany ze źródeł potrzebuje cmake: zainstaluj go menedżerem pakietów.",
    "The game closed with an error": "Gra się zamknęła z błędem",
    "Full log: {}": "Pełny log: {}",
    "not in the game world": "poza światem gry",
    # engine
    "The game is not running.": "Gra nie jest uruchomiona.",
    "Your system blocks access to game memory (ptrace_scope). See the README.":
        "System blokuje dostęp do pamięci gry (ptrace_scope). Zobacz README.",
    "No access to the game. Close it and start it from the trainer.":
        "Brak dostępu do gry. Zamknij ją i uruchom przyciskiem w trainerze.",
    "The game is starting…": "Gra się uruchamia…",
    "Connected.": "Połączono.",
    "Waiting for the game to start…": "Czekam, aż gra wystartuje…",
    "Unexpected game version (1.09 is required): leaving it alone.":
        "To nie jest oczekiwana wersja gry (potrzebna 1.09): nie ruszam jej.",
    "The space for the trainer's stub is taken: leaving the game alone.":
        "Miejsce na wstawkę trainera jest zajęte: nie ruszam gry.",
    "bad address": "zły adres",
    "writing to the game failed": "zapis do gry się nie udał",
    "the trainer is not connected to the game": "trainer nie jest połączony z grą",
    "load a character first": "najpierw wczytaj postać",
    "the game is still running the previous command":
        "gra jeszcze wykonuje poprzednie polecenie",
    "the game is not responding (loading or paused?)":
        "gra nie odpowiada (wczytywanie albo pauza okna?)",
    "game function {} does not look like 1.09": "funkcja gry {} wygląda inaczej niż w 1.09",
    "unexpected teleport function": "nieoczekiwana funkcja teleportu",
    "the game refused this warp": "gra odrzuciła ten warp",
    "the game's event manager is missing": "brak menedżera zdarzeń gry",
    "event flags are not ready yet": "flagi zdarzeń nie są jeszcze gotowe",
    "character data is missing": "brak danych postaci",
    "no room for more (inventory limit)": "nie wejdzie więcej (limit w ekwipunku)",
    "the game refused the item": "gra odrzuciła przedmiot",
    "the game did not create the item": "gra nie utworzyła przedmiotu",
    "the game did not accept the item (inventory full?)":
        "gra nie przyjęła przedmiotu (pełny ekwipunek?)",
    # files
    "Game files not found. Choose the game folder in the bbport launcher, then restart the "
    "trainer.":
        "Nie widzę plików gry. Wskaż folder gry w launcherze bbporta i uruchom trainer ponownie.",
    "No game texts found in {}": "Nie ma tekstów gry w {}",
    "Lamp {}": "Lampa {}",
    "This is not bbport. Pick the AppImage, Bloodborne.sh or launcher/bbport_launcher.py.":
        "To nie jest bbport. Wskaż AppImage, Bloodborne.sh albo launcher/bbport_launcher.py.",
}

TABLES = {"pl": POLISH}


def system_language():
    for variable in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(variable)
        if value:
            code = value[:2].lower()
            return code if code in LANGUAGES else "en"
    return "en"


LANGUAGE = config.get("language")
if LANGUAGE not in LANGUAGES:
    LANGUAGE = system_language()


def translate(text, code):
    return TABLES.get(code, {}).get(text, text)


def tr(text):
    """The text in the interface language."""
    return translate(text, LANGUAGE)
