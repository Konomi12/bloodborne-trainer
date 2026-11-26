#!/usr/bin/env python3
"""Trainer do nauki Bloodborne na bbport (w stylu SilkySouls). Uruchom: trainer.py [--play]"""
import glob
import json
import os
import select
import struct
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import engine  # noqa: E402
import gamedata  # noqa: E402

STATE_DIR = Path.home() / ".local/share/bb-trainer"
POSITIONS = STATE_DIR / "positions.json"
GAME_LOG = STATE_DIR / "game.log"

# scancode SDL, klawisz GTK, opis, akcja
HOTKEYS = [
    (62, Gdk.KEY_F5, "F5", "Zapisz pozycję", "save_position"),
    (63, Gdk.KEY_F6, "F6", "Wczytaj pozycję", "load_position"),
    (64, Gdk.KEY_F7, "F7", "Pełne HP i stamina", "heal"),
    (65, Gdk.KEY_F8, "F8", "Nieśmiertelność wł./wył.", "toggle_no_dead"),
    (67, Gdk.KEY_F10, "F10", "Powtórz ostatni warp", "repeat_warp"),
]
PAD_ACTIONS = {"up": "save_position", "down": "load_position", "left": "heal", "right": "repeat_warp"}

PLAYER_TOGGLES = [
    ("no_dead", "Nieśmiertelność", "HP nie spadnie poniżej 1"),
    ("one_hit", "Zabijanie jednym ciosem", None),
    ("all_no_stamina", "Nieskończona stamina", "Flaga gry: działa na wszystkie postacie"),
    ("no_bullets", "Nieskończone kule", "Strzały nie zużywają Quicksilver Bullets"),
    ("hidden", "Niewidzialność", "Wrogowie cię nie widzą"),
    ("silent", "Cisza", "Wrogowie cię nie słyszą"),
]
ENEMY_TOGGLES = [
    ("all_no_ai", "Wyłącz AI", "Wrogowie stoją i nic nie robią"),
    ("all_no_attack", "Wrogowie nie atakują", None),
    ("all_no_move", "Nikt się nie rusza", "Flaga gry: obejmuje też ciebie"),
    ("all_no_damage", "Nikt nie dostaje obrażeń", "Obejmuje też ciebie"),
    ("all_no_hit", "Brak trafień", "Obejmuje też ciebie"),
    ("all_no_dead", "Nikt nie może zginąć", "HP wszystkich zatrzymuje się na 1"),
]


class Pad:
    """Skróty z pada przez evdev: przytrzymaj Select/View i wciśnij kierunek na krzyżaku."""

    EVENT = struct.Struct("llHHi")

    def __init__(self):
        self.devices = {}
        self.select_held = set()
        self.scan_in = 0

    def scan(self):
        for node in glob.glob("/sys/class/input/event*"):
            path = "/dev/input/" + os.path.basename(node)
            if path in self.devices or not glob.glob(node + "/device/js*"):
                continue
            try:
                self.devices[path] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                pass

    def poll(self):
        if self.scan_in <= 0:
            self.scan()
            self.scan_in = 100
        self.scan_in -= 1
        actions = []
        if not self.devices:
            return actions
        ready = select.select(list(self.devices.values()), [], [], 0)[0]
        for path, fd in list(self.devices.items()):
            if fd not in ready:
                continue
            try:
                data = os.read(fd, self.EVENT.size * 64)
            except OSError:
                os.close(fd)
                del self.devices[path]
                continue
            for _, _, kind, code, value in self.EVENT.iter_unpack(
                    data[:len(data) - len(data) % self.EVENT.size]):
                if kind == 1 and code == 0x13A:  # BTN_SELECT
                    self.select_held.add(path) if value else self.select_held.discard(path)
                elif kind == 3 and code in (16, 17) and value and path in self.select_held:
                    direction = (("left", "right") if code == 16 else ("up", "down"))[value > 0]
                    actions.append(PAD_ACTIONS[direction])
        return actions


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Bloodborne Trainer",
                         default_width=620, default_height=760)
        self.game = engine.Game()
        self.pad = Pad()
        self.child = None
        self.toggles = {}
        self.keys_down = set()
        self.last_warp = None
        self.forced_spawn = None  # słownik, dopóki czekamy na wczytanie po „Leć” do bossa
        self.story_flag = None    # walka z końca gry przygotowana w tej sesji trainera
        self.story_practice = True
        self.frozen = {}          # chr -> hp
        self.item_counts = {}
        self.slot = 0
        self.positions = self.load_positions()
        self.ticks = 0
        self.build()
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.connect("close-request", self.on_close)
        self.timer = GLib.timeout_add(30, self.tick)

    # ---------------------------------------------------------------- budowa okna
    def build(self):
        self.overlay = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title="Bloodborne Trainer", subtitle="Szukam gry…")
        header.set_title_widget(self.title_widget)
        self.play_button = Gtk.Button(label="Uruchom grę", css_classes=["suggested-action"])
        self.play_button.connect("clicked", lambda *_: self.start_game())
        header.pack_start(self.play_button)
        view.add_top_bar(header)
        stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.NARROW)
        view.add_top_bar(switcher)
        for name, title, icon, builder in (
                ("player", "Gracz", "avatar-default-symbolic", self.page_player),
                ("travel", "Podróż", "find-location-symbolic", self.page_travel),
                ("enemies", "Wrogowie", "view-reveal-symbolic", self.page_enemies),
                ("items", "Itemy", "view-grid-symbolic", self.page_items),
                ("stats", "Staty", "view-list-symbolic", self.page_stats),
                ("game", "Gra", "preferences-system-symbolic", self.page_game)):
            page = Adw.PreferencesPage()
            builder(page)
            stack.add_titled_with_icon(page, name, title, icon)
        view.set_content(stack)
        self.overlay.set_child(view)
        self.set_content(self.overlay)

    def group(self, page, title, description=None):
        group = Adw.PreferencesGroup(title=title)
        if description:
            group.set_description(description)
        page.add(group)
        return group

    def button(self, label, action, **extra):
        button = Gtk.Button(label=label, valign=Gtk.Align.CENTER, **extra)
        button.connect("clicked", lambda *_: self.run(action))
        return button

    def row(self, group, title, *widgets, subtitle=None):
        row = Adw.ActionRow(title=GLib.markup_escape_text(title))
        if subtitle:
            row.set_subtitle(GLib.markup_escape_text(subtitle))
        for widget in widgets:
            row.add_suffix(widget)
        group.add(row)
        return row

    def switch(self, group, key, title, subtitle):
        row = Adw.SwitchRow(title=title)
        if subtitle:
            row.set_subtitle(subtitle)
        self.toggles[key] = row
        group.add(row)
        return row

    def spin(self, low, high, value, step=1, digits=0):
        spin = Gtk.SpinButton.new_with_range(low, high, step)
        spin.set_digits(digits)
        spin.set_value(value)
        spin.set_valign(Gtk.Align.CENTER)
        return spin

    def page_player(self, page):
        group = self.group(page, "Stan")
        self.hp_row = self.row(group, "HP / stamina", self.button("Ulecz", self.heal),
                               self.button("Zgiń", lambda: self.game.kill_player()))
        self.hp_spin = self.spin(1, 99999, 100)
        self.row(group, "Ustaw HP", self.hp_spin, self.button(
            "Ustaw", lambda: self.game.set_hp(self.game.need_world(), self.hp_spin.get_value())))
        self.freeze_hp = Adw.SwitchRow(title="Zawsze pełne HP",
                                       subtitle="Tylko ty; mocny cios nadal może zabić")
        self.freeze_stamina = Adw.SwitchRow(title="Zawsze pełna stamina", subtitle="Tylko ty")
        group.add(self.freeze_hp)
        group.add(self.freeze_stamina)
        self.keep_items = Adw.SwitchRow(
            title="Nieskończone przedmioty",
            subtitle="Fiolki, koktajle itd. wracają po użyciu (miej min. 2 sztuki)")
        group.add(self.keep_items)
        cheats = self.group(page, "Ułatwienia")
        for toggle in PLAYER_TOGGLES:
            self.switch(cheats, *toggle)

    def page_travel(self, page):
        group = self.group(page, "Zapisana pozycja", "F5 zapisuje, F6 wczytuje (w tej samej mapie)")
        self.slot_drop = Gtk.DropDown.new_from_strings([f"Slot {i}" for i in range(1, 6)])
        self.slot_drop.set_valign(Gtk.Align.CENTER)
        self.slot_drop.connect("notify::selected", lambda *_: self.show_slot())
        self.position_row = self.row(group, "Teraz", self.slot_drop)
        self.slot_row = self.row(group, "W slocie",
                                 self.button("Zapisz", self.save_position),
                                 self.button("Wczytaj", self.load_position))
        self.with_hp = Adw.SwitchRow(title="Wczytuj razem z HP i staminą", active=True)
        group.add(self.with_hp)
        self.step = self.spin(0.5, 100, 3, 0.5, 1)
        self.row(group, "Przesuń o (metry)", self.step,
                 self.button("Góra", lambda: self.nudge(1)),
                 self.button("Dół", lambda: self.nudge(-1)))
        self.show_slot()

        warp = self.group(page, "Warp do lampy",
                          "Także do niezapalonych. Cel staje się twoją ostatnią lampą.")
        try:
            self.lamps = gamedata.lamps()
        except Exception as error:  # brak plików gry: reszta ma działać
            self.lamps = []
            warp.set_description(f"Nie wczytałem listy lamp: {error}")
        for point, name in self.lamps:
            self.row(warp, name, self.button("Leć", lambda p=point: self.warp(p)))

        bosses = self.group(page, "Bossowie",
                            "„Leć” stawia cię przed wejściem do walki. „Wskrześ” kasuje flagę "
                            "pokonania; boss wraca po „Leć”. Pinezka zapisuje twoje obecne "
                            "miejsce jako własne wejście. Przed wskrzeszaniem zrób kopię "
                            "zapisu w zakładce Gra.")
        for flag, name, entry in gamedata.BOSSES:
            row = self.row(bosses, name)
            row.add_suffix(self.button("Stan", lambda f=flag, r=row: r.set_subtitle(
                "pokonany" if self.game.get_event_flag(f) else "żyje")))
            row.add_suffix(self.button("Wskrześ", lambda f=flag, r=row: self.set_boss(f, r, False)))
            row.add_suffix(self.button("Pokonany", lambda f=flag, r=row: self.set_boss(f, r, True)))
            pin = Gtk.Button(valign=Gtk.Align.CENTER)
            self.show_pin(pin, flag)
            pin.connect("clicked", lambda b, f=flag: self.run(lambda: self.pin_entry(b, f)))
            row.add_suffix(pin)
            row.add_suffix(self.button("Leć", lambda f=flag, e=entry: self.warp_boss(f, e)))

    def page_enemies(self, page):
        group = self.group(page, "Zachowanie")
        for toggle in ENEMY_TOGGLES:
            self.switch(group, *toggle)
        self.near_group = self.group(page, "W pobliżu (od najbliższego)",
                                     "Odświeża się samo, gdy zakładka jest widoczna")
        self.near_rows = []
        for index in range(10):
            row = Adw.ActionRow(title="—", visible=False)
            for label, action in (("Zabij", lambda c: self.game.set_hp(c, 0)),
                                  ("1 HP", lambda c: self.game.set_hp(c, 1)),
                                  ("Pełne", self.fill_enemy),
                                  ("Zamroź HP", self.freeze_enemy),
                                  ("Do niego", self.goto_enemy)):
                row.add_suffix(self.button(
                    label, lambda i=index, a=action: self.on_enemy(i, a)))
            self.near_group.add(row)
            self.near_rows.append([row, 0])

    def page_items(self, page):
        group = self.group(page, "Dodaj przedmiot",
                           "Zwykłe przedmioty (bez broni i strojów). Przedmioty fabularne "
                           "mogą popsuć zapis.")
        self.amount = self.spin(1, 999, 20)
        self.row(group, "Ile", self.amount)
        search = Gtk.SearchEntry(placeholder_text="Szukaj po nazwie z gry…")
        group.add(search)
        results = self.group(page, "")
        try:
            items = gamedata.goods()
        except Exception as error:
            items = []
            group.set_description(f"Nie wczytałem listy przedmiotów: {error}")
        rows = []
        for ident, name in items:
            row = self.row(results, name, self.button(
                "Dodaj", lambda i=ident, n=name: self.give(i, n)), subtitle=f"id {ident}")
            rows.append((row, f"{name} {ident}".casefold()))

        def filter_rows(entry):
            text = entry.get_text().casefold()
            for row, key in rows:
                row.set_visible(text in key)

        search.connect("search-changed", filter_rows)

    def page_stats(self, page):
        group = self.group(page, "Postać",
                           "Zmiany zapisują się w grze. HP i stamina przeliczą się po "
                           "przeładowaniu.")
        self.stat_spins = {}
        for name in engine.STATS:
            high = 999_999_999 if name == "Echa krwi" else 999 if name in ("Poziom",) else 99
            spin = self.spin(0, high, 0)
            self.stat_spins[name] = spin
            self.row(group, name, spin, self.button("Ustaw", lambda n=name: self.set_stat(n)))
        self.ng_spin = self.spin(0, 7, 0)
        self.row(group, "Cykl NG+", self.ng_spin, self.button("Ustaw", self.set_ng))
        self.row(group, "Wartości z gry", self.button("Odczytaj", self.read_stats))

    def page_game(self, page):
        group = self.group(page, "Gra")
        self.speed = self.spin(0.1, 3.0, 1.0, 0.1, 2)
        self.speed.connect("value-changed", lambda s: self.game.set_speed(s.get_value()))
        self.row(group, "Prędkość gry", self.speed,
                 self.button("1×", lambda: self.speed.set_value(1.0)))
        self.row(group, "Wyjdź do menu głównego",
                 self.button("Wyjdź", lambda: self.game.return_to_title()),
                 subtitle="Szybki reset sytuacji")
        self.row(group, "Przywróć fabułę", self.button("Przywróć", self.restore_story),
                 subtitle="Po walce z Gehrmanem / Moon Presence (zadziała po warpie)")
        self.row(group, "Kopia zapisów", self.button("Zrób kopię", self.backup_saves),
                 subtitle="Do ~/.local/share/bb-trainer/saves")
        keys = self.group(page, "Skróty")
        self.keyboard_on = Adw.SwitchRow(title="Klawiatura (w grze i w trainerze)", active=True)
        self.pad_on = Adw.SwitchRow(title="Pad: trzymaj Select/View + krzyżak", active=True,
                                    subtitle="Góra zapisz, dół wczytaj, lewo ulecz, prawo warp")
        keys.add(self.keyboard_on)
        keys.add(self.pad_on)
        for _, _, key, text, _ in HOTKEYS:
            self.row(keys, text, Gtk.Label(label=key))
        note = self.group(page, "Uwaga")
        self.row(note, "Nie używaj w co-opie online",
                 subtitle="Flagi i prędkość psują sesję drugiej osobie")

    # ---------------------------------------------------------------- akcje
    def toast(self, text):
        toast = Adw.Toast(title=GLib.markup_escape_text(text), timeout=3)
        self.overlay.add_toast(toast)

    def run(self, action):
        try:
            action()
        except (engine.TrainerError, OSError, TypeError, struct.error) as error:
            self.toast(str(error) or "Nie udało się")

    def heal(self):
        self.game.full_heal()

    def toggle_no_dead(self):
        row = self.toggles["no_dead"]
        row.set_active(not row.get_active())
        self.toast("Nieśmiertelność " + ("włączona" if row.get_active() else "wyłączona"))

    def load_positions(self):
        try:
            return json.loads(POSITIONS.read_text())
        except (OSError, ValueError):
            return {}

    def show_slot(self):
        self.slot = self.slot_drop.get_selected()
        saved = self.positions.get(str(self.slot))
        self.slot_row.set_subtitle(
            "pusty" if not saved else "x {:.1f}  y {:.1f}  z {:.1f}".format(*saved["position"]))

    def save_position(self):
        player = self.game.need_world()
        where = self.game.position(player)
        if where is None:
            raise engine.TrainerError("nie mogę odczytać pozycji")
        hp, _, stamina, _ = self.game.vitals(player)
        self.positions[str(self.slot)] = {"position": where[0], "rotation": where[1],
                                          "map": self.game.map_id(), "hp": hp, "stamina": stamina}
        self.write_positions()
        self.show_slot()
        self.toast(f"Zapisano pozycję w slocie {self.slot + 1}")

    def load_position(self):
        player = self.game.need_world()
        saved = self.positions.get(str(self.slot))
        if not saved:
            raise engine.TrainerError("ten slot jest pusty")
        if saved["map"] != self.game.map_id():
            raise engine.TrainerError("pozycja jest z innej mapy: najpierw zrób warp")
        self.game.teleport(saved["position"], saved["rotation"])
        if self.with_hp.get_active():
            self.game.set_hp(player, saved["hp"])
            self.game.set_i32(self.game.chr_data(player) + 0x134, saved["stamina"])

    def nudge(self, direction):
        where = self.game.position(self.game.need_world())
        position = where[0]
        position[1] += direction * self.step.get_value()
        self.game.teleport(position, where[1])

    def warp(self, point):
        self.restore_story()
        self.game.warp_lamp(point)
        self.last_warp = lambda: self.warp(point)

    def warp_boss(self, flag, entry):
        story = gamedata.STORY_FIGHTS.get(flag)
        if story and self.story_flag != flag:
            self.game.need_world()
            self.ask_story(flag, entry)
            return
        if not story:
            self.restore_story()
        self.fly_to_boss(flag, entry)

    def fly_to_boss(self, flag, entry):
        saved = self.positions.get(f"boss:{flag}")
        if saved:
            target = saved["map"], saved["position"], saved["rotation"][1]
        else:
            target = gamedata.boss_entry(entry)
        story = gamedata.STORY_FIGHTS.get(flag)
        if story:  # przy każdym podejściu od nowa: po walce gra zmienia te flagi
            for story_flag, value in story.items():
                self.game.set_event_flag(story_flag, value)
        self.game.warp_position(*target)
        self.forced_spawn = {"unloaded": False, "stable_since": None,
                             "deadline": time.monotonic() + 90}
        self.last_warp = lambda: self.warp_boss(flag, entry)

    # ---------------------------------------------------------------- walki z końca gry
    def ask_story(self, flag, entry):
        name = next(n for f, n, _ in gamedata.BOSSES if f == flag)
        dialog = Adw.AlertDialog(
            heading=name,
            body="To walka z końca gry. Trainer zrobi kopię zapisu, ustawi flagi fabuły i "
                 "przywróci je, gdy polecisz gdzie indziej.\n\n"
                 "Prawdziwa wygrana kończy grę i zaczyna NG+. W trybie treningowym boss "
                 "odzyskuje HP, gdy spadnie poniżej 25%, a one-shot jest wyłączony.")
        dialog.add_response("cancel", "Anuluj")
        dialog.add_response("real", "Można go zabić")
        dialog.add_response("practice", "Trening")
        dialog.set_response_appearance("real", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("practice", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("practice")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, answer: answer != "cancel" and self.run(
            lambda: self.start_story(flag, entry, answer == "practice")))
        dialog.present(self)

    def start_story(self, flag, entry, practice):
        self.game.need_world()
        self.backup_saves()  # bez kopii nie ruszamy fabuły
        if "story" not in self.positions:
            # oryginały zapisujemy raz: kolejna walka nie może ich nadpisać zmienionymi
            wanted = sorted({f for flags in gamedata.STORY_FIGHTS.values() for f in flags})
            self.positions["story"] = {
                "ng": self.ng_cycle(),
                "flags": {str(f): self.game.get_event_flag(f) for f in wanted}}
            self.write_positions()
        self.story_flag, self.story_practice = flag, practice
        self.fly_to_boss(flag, entry)
        self.last_warp = lambda: self.warp_boss(flag, entry)

    def ng_cycle(self):
        return self.game.i32(self.game.ptr(engine.BASE + engine.GAME_DATA_MAN) + engine.NG_CYCLE)

    def restore_story(self):
        saved = self.positions.get("story")
        if not saved:
            return
        self.game.need_world()
        if saved["ng"] == self.ng_cycle():
            for flag, value in saved["flags"].items():
                self.game.set_event_flag(int(flag), value)
            self.toast("Przywrócono stan fabuły")
        else:
            self.toast("Gra przeszła do nowego cyklu: starych flag nie przywracam")
        del self.positions["story"]
        self.story_flag = None
        self.write_positions()

    def guard_story_boss(self):
        """Tryb treningowy: boss we Śnie nie może zginąć, bo to kończy grę."""
        if not (self.story_flag and self.story_practice) or self.game.map_id() != 0x15000000:
            return
        self.toggles["one_hit"].set_active(False)
        self.game.set_flag("one_hit", False)
        for chr_ in self.game.characters():
            vitals = self.game.vitals(chr_)
            if vitals and vitals[1] >= 5000 and 0 < vitals[0] < vitals[1] * 0.25:
                self.game.set_i32(self.game.chr_data(chr_) + 0xF8, vitals[1])
                self.toast("Boss odzyskał HP (tryb treningowy)")

    def repeat_warp(self):
        if self.last_warp is None:
            raise engine.TrainerError("nie było jeszcze warpu")
        self.last_warp()

    def show_pin(self, button, flag):
        saved = f"boss:{flag}" in self.positions
        button.set_label("↺" if saved else "📌")  # ikony motywu bywają nieczytelne
        button.set_tooltip_text("Wróć do domyślnego wejścia" if saved
                                else "Zapisz obecne miejsce jako wejście do tego bossa")

    def pin_entry(self, button, flag):
        key = f"boss:{flag}"
        if self.positions.pop(key, None) is None:
            where = self.game.position(self.game.need_world())
            if where is None:
                raise engine.TrainerError("nie mogę odczytać pozycji")
            self.positions[key] = {"position": where[0], "rotation": where[1],
                                   "map": self.game.map_id()}
            self.toast("„Leć” będzie teraz wracać w to miejsce")
        else:
            self.toast("Przywrócono domyślne wejście")
        self.write_positions()
        self.show_pin(button, flag)

    def write_positions(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        POSITIONS.write_text(json.dumps(self.positions))

    def finish_forced_spawn(self, in_world):
        """Zdejmuje znacznik wymuszonego miejsca, ale dopiero gdy wczytanie na pewno się
        skończyło: gra czyta go późno, a „w świecie” potrafi mrugnąć w trakcie ładowania."""
        spawn = self.forced_spawn
        if not spawn:
            return
        now = time.monotonic()
        if not in_world:
            spawn["unloaded"], spawn["stable_since"] = True, None
        elif spawn["stable_since"] is None:
            spawn["stable_since"] = now
        loaded = (spawn["unloaded"] and spawn["stable_since"] is not None
                  and now - spawn["stable_since"] >= 6)
        if loaded or (in_world and now > spawn["deadline"]):
            self.game.clear_forced_spawn()
            self.forced_spawn = None

    def set_boss(self, flag, row, dead):
        self.game.set_event_flag(flag, dead)
        row.set_subtitle("pokonany" if self.game.get_event_flag(flag) else "żyje")

    def on_enemy(self, index, action):
        self.game.need_world()
        chr_ = self.near_rows[index][1]
        if chr_ not in self.game.characters():
            raise engine.TrainerError("tej postaci już nie ma")
        action(chr_)

    def fill_enemy(self, chr_):
        self.frozen.pop(chr_, None)
        self.game.set_hp(chr_, self.game.vitals(chr_)[1])

    def freeze_enemy(self, chr_):
        if self.frozen.pop(chr_, None) is None:
            self.frozen[chr_] = self.game.vitals(chr_)[0]

    def goto_enemy(self, chr_):
        where = self.game.position(chr_)
        self.game.teleport([where[0][0] + 1.5, where[0][1] + 0.3, where[0][2]])

    def give(self, ident, name):
        added = self.game.give_goods(ident, int(self.amount.get_value()))
        self.toast(f"Dodano {added} × {name}")

    def read_stats(self):
        self.game.need_world()
        data = self.game.game_data()
        for name, offset in engine.STATS.items():
            self.stat_spins[name].set_value(self.game.i32(data + offset))
        self.ng_spin.set_value(self.game.i32(self.game.ptr(engine.BASE + engine.GAME_DATA_MAN)
                                             + engine.NG_CYCLE))
        self.stats_read = True

    def set_stat(self, name):
        self.game.need_world()
        if not getattr(self, "stats_read", False):
            raise engine.TrainerError("najpierw „Odczytaj”, żeby nie wpisać zer")
        self.game.set_i32(self.game.game_data() + engine.STATS[name],
                          self.stat_spins[name].get_value())

    def set_ng(self):
        self.game.need_world()
        if not getattr(self, "stats_read", False):
            raise engine.TrainerError("najpierw „Odczytaj”")
        self.game.set_i32(self.game.ptr(engine.BASE + engine.GAME_DATA_MAN) + engine.NG_CYCLE,
                          self.ng_spin.get_value())

    def backup_saves(self):
        import shutil
        source = gamedata.BBPORT / "user/savedata"
        if not source.is_dir():
            raise engine.TrainerError(f"nie widzę zapisów w {source}")
        target = STATE_DIR / "saves" / time.strftime("%Y-%m-%d_%H-%M-%S")
        shutil.copytree(source, target)
        self.toast(f"Kopia: {target}")

    # ---------------------------------------------------------------- gra
    def start_game(self):
        if engine.find_game_pids():
            self.toast("Gra już działa. Trainer widzi tylko grę uruchomioną stąd.")
            return
        launcher = gamedata.BBPORT / "launcher/bbport_launcher.py"
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(GAME_LOG, "wb") as log:
            self.child = subprocess.Popen([sys.executable, str(launcher), "--play"],
                                          stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True)
        self.toast("Uruchamiam grę…")

    def report_start_failure(self):
        try:
            lines = GAME_LOG.read_text(errors="replace").strip().splitlines()
        except OSError:
            lines = []
        text = "\n".join(lines[-6:]) or "brak komunikatu"
        if "cmake" in text:
            text += "\n\nBrakuje programu cmake. Zainstaluj go:  sudo pacman -S cmake"
        dialog = Adw.AlertDialog(heading="Gra się zamknęła z błędem",
                                 body=f"{text}\n\nPełny log: {GAME_LOG}")
        dialog.add_response("ok", "OK")
        dialog.present(self)

    def reap(self):
        if self.child and self.child.poll() is not None:
            if self.child.returncode > 0:
                self.report_start_failure()
            self.child = None
        elif not self.child:
            try:  # osierocone procesy gry (jesteśmy ich subreaperem)
                while os.waitpid(-1, os.WNOHANG)[0]:
                    pass
            except ChildProcessError:
                pass

    # ---------------------------------------------------------------- pętla
    def fire(self, name):
        self.run(getattr(self, name))

    def on_key(self, _controller, keyval, _code, _state):
        for _, key, _, _, name in HOTKEYS:
            if keyval == key and self.keyboard_on.get_active():
                self.fire(name)
                return True
        return False

    def tick(self):
        try:
            self.update()
        except (engine.TrainerError, OSError, TypeError, struct.error) as error:
            self.title_widget.set_subtitle(str(error))
        return True

    def update(self):
        self.ticks += 1
        slow = self.ticks % 10 == 0
        if self.ticks % 30 == 1:
            self.reap()
            status = self.game.attach()
            self.title_widget.set_subtitle(status)
            self.play_button.set_visible(not engine.find_game_pids())
        pad_actions = self.pad.poll()
        if not self.game.hooked:
            return
        if self.game.pid is None or not os.path.exists(f"/proc/{self.game.pid}/maps"):
            self.game.detach(restore=False)
            return
        for key, row in self.toggles.items():
            if row.get_active():
                if self.game.read(engine.BASE + engine.FLAGS[key], 1) != b"\x01" \
                        or key not in self.game.forced:
                    self.game.set_flag(key, True)
            elif key in self.game.forced:
                self.game.set_flag(key, False)
        self.game.set_speed(self.speed.get_value())
        in_world = self.game.in_world()
        self.finish_forced_spawn(in_world)

        if self.keyboard_on.get_active():
            keys = self.game.keyboard_state() if in_world else None
            if keys:
                down = {name for code, _, _, _, name in HOTKEYS if keys[code]}
                for name in down - self.keys_down:
                    self.fire(name)
                self.keys_down = down
        if self.pad_on.get_active() and in_world:
            for name in pad_actions:
                self.fire(name)

        if not in_world:
            self.frozen.clear()
            self.item_counts.clear()
            if slow:
                self.hp_row.set_subtitle("poza światem gry")
            return
        player = self.game.player()
        data = self.game.chr_data(player)
        vitals = self.game.vitals(player)
        if not vitals:
            return
        hp, max_hp, stamina, max_stamina = vitals
        if self.freeze_hp.get_active() and 0 < hp < max_hp:
            self.game.set_i32(data + 0xF8, max_hp)
        if self.freeze_stamina.get_active() and stamina < max_stamina:
            self.game.set_i32(data + 0x134, max_stamina)
        if self.keep_items.get_active():
            self.game.keep_items(self.item_counts)
        else:
            self.item_counts.clear()
        if self.frozen:
            alive = set(self.game.characters())
            for chr_, value in list(self.frozen.items()):
                if chr_ in alive:
                    self.game.set_i32(self.game.chr_data(chr_) + 0xF8, value)
                else:
                    del self.frozen[chr_]
        self.guard_story_boss()
        if not slow:
            return
        self.hp_row.set_subtitle(f"{hp} / {max_hp}   •   {stamina} / {max_stamina}")
        where = self.game.position(player)
        if where:
            self.position_row.set_subtitle("x {:.1f}  y {:.1f}  z {:.1f}".format(*where[0]))
        if self.near_group.get_mapped():
            near = self.game.nearby(limit=len(self.near_rows))
            for index, entry in enumerate(self.near_rows):
                row = entry[0]
                row.set_visible(index < len(near))
                if index < len(near):
                    distance, chr_, e_hp, e_max, _ = near[index]
                    entry[1] = chr_
                    row.set_title(f"{e_hp} / {e_max} HP" + ("  ❄" if chr_ in self.frozen else ""))
                    row.set_subtitle(f"{distance:.1f} m")

    def on_close(self, *_):
        GLib.source_remove(self.timer)
        if self.game.hooked and self.positions.get("story"):
            self.run(self.restore_story)
        self.game.detach(restore=True)
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.bbtrainer",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None

    def do_command_line(self, command_line):
        play = "--play" in command_line.get_arguments()
        if not self.window:
            self.window = Window(self)
        self.window.present()
        if play:
            self.window.start_game()
        return 0


def main():
    engine.become_subreaper()
    return App().run(sys.argv)

if __name__ == "__main__":
    raise SystemExit(main())
