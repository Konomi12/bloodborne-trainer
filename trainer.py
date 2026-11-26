#!/usr/bin/env python3
"""Practice trainer for Bloodborne on bbport (SilkySouls style). Usage: trainer.py [--play]"""
import glob
import json
import os
import select
import shutil
import struct
import subprocess
import sys
import time

import requirements

requirements.check()

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import bbport  # noqa: E402
import config  # noqa: E402
import engine  # noqa: E402
import gamedata  # noqa: E402
import i18n  # noqa: E402
from i18n import tr  # noqa: E402

STATE_DIR = config.DATA_HOME / "bb-trainer"
POSITIONS = STATE_DIR / "positions.json"
GAME_LOG = STATE_DIR / "game.log"

# SDL scancode, GTK key, label, description, action (descriptions are translated on screen)
HOTKEYS = [
    (62, Gdk.KEY_F5, "F5", "Save position", "save_position"),
    (63, Gdk.KEY_F6, "F6", "Load position", "load_position"),
    (64, Gdk.KEY_F7, "F7", "Full HP and stamina", "heal"),
    (65, Gdk.KEY_F8, "F8", "No death on/off", "toggle_no_dead"),
    (67, Gdk.KEY_F10, "F10", "Repeat last warp", "repeat_warp"),
]
PAD_ACTIONS = {"up": "save_position", "down": "load_position", "left": "heal", "right": "repeat_warp"}

PLAYER_TOGGLES = [
    ("no_dead", "No death", "HP never drops below 1"),
    ("one_hit", "One-hit kill", None),
    ("all_no_stamina", "Infinite stamina", "Game flag: applies to every character"),
    ("no_bullets", "Infinite bullets", "Shots do not use Quicksilver Bullets"),
    ("hidden", "Invisibility", "Enemies cannot see you"),
    ("silent", "Silence", "Enemies cannot hear you"),
]
ENEMY_TOGGLES = [
    ("all_no_ai", "Disable AI", "Enemies stand and do nothing"),
    ("all_no_attack", "Enemies do not attack", None),
    ("all_no_move", "Nobody moves", "Game flag: includes you"),
    ("all_no_damage", "Nobody takes damage", "Includes you"),
    ("all_no_hit", "No hits", "Includes you"),
    ("all_no_dead", "Nobody can die", "Everyone's HP stops at 1"),
]


class Pad:
    """Gamepad shortcuts through evdev: hold Select/View and press a D-pad direction."""

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
        self.forced_spawn = None  # a dict while we wait for the load after "Go" to a boss
        self.story_flag = None    # the late-game fight prepared in this trainer session
        self.story_practice = True
        self.frozen = {}          # chr -> hp
        self.item_counts = {}
        self.slot = 0
        self.start_after_choice = False
        self.positions = self.load_positions()
        self.ticks = 0
        self.build()
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)
        self.connect("close-request", self.on_close)
        self.timer = GLib.timeout_add(30, self.tick)

    # ---------------------------------------------------------------- building the window
    def build(self):
        self.overlay = Adw.ToastOverlay()
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title="Bloodborne Trainer",
                                            subtitle=tr("Looking for the game…"))
        header.set_title_widget(self.title_widget)
        self.play_button = Gtk.Button(label=tr("Start game"), css_classes=["suggested-action"])
        self.play_button.connect("clicked", lambda *_: self.start_game())
        header.pack_start(self.play_button)
        view.add_top_bar(header)
        stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.NARROW)
        view.add_top_bar(switcher)
        for name, title, icon, builder in (
                ("player", "Player", "avatar-default-symbolic", self.page_player),
                ("travel", "Travel", "find-location-symbolic", self.page_travel),
                ("enemies", "Enemies", "view-reveal-symbolic", self.page_enemies),
                ("items", "Items", "view-grid-symbolic", self.page_items),
                ("stats", "Stats", "view-list-symbolic", self.page_stats),
                ("game", "Game", "preferences-system-symbolic", self.page_game)):
            page = Adw.PreferencesPage()
            builder(page)
            stack.add_titled_with_icon(page, name, tr(title), icon)
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
        row = Adw.SwitchRow(title=tr(title))
        if subtitle:
            row.set_subtitle(tr(subtitle))
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
        group = self.group(page, tr("Status"))
        self.hp_row = self.row(group, "HP / stamina", self.button(tr("Heal"), self.heal),
                               self.button(tr("Die"), lambda: self.game.kill_player()))
        self.hp_spin = self.spin(1, 99999, 100)
        self.row(group, tr("Set HP"), self.hp_spin, self.button(
            tr("Set"),
            lambda: self.game.set_hp(self.game.need_world(), self.hp_spin.get_value())))
        self.freeze_hp = Adw.SwitchRow(
            title=tr("Always full HP"), subtitle=tr("Only you; a heavy hit can still kill"))
        self.freeze_stamina = Adw.SwitchRow(title=tr("Always full stamina"),
                                            subtitle=tr("Only you"))
        group.add(self.freeze_hp)
        group.add(self.freeze_stamina)
        self.keep_items = Adw.SwitchRow(
            title=tr("Infinite items"),
            subtitle=tr("Vials, cocktails etc. come back after use (carry at least 2)"))
        group.add(self.keep_items)
        cheats = self.group(page, tr("Cheats"))
        for toggle in PLAYER_TOGGLES:
            self.switch(cheats, *toggle)

    def page_travel(self, page):
        group = self.group(page, tr("Saved position"),
                           tr("F5 saves, F6 loads (within the same map)"))
        self.slot_drop = Gtk.DropDown.new_from_strings(
            [tr("Slot {}").format(i) for i in range(1, 6)])
        self.slot_drop.set_valign(Gtk.Align.CENTER)
        self.slot_drop.connect("notify::selected", lambda *_: self.show_slot())
        self.position_row = self.row(group, tr("Now"), self.slot_drop)
        self.slot_row = self.row(group, tr("In slot"),
                                 self.button(tr("Save"), self.save_position),
                                 self.button(tr("Load"), self.load_position))
        self.with_hp = Adw.SwitchRow(title=tr("Restore HP and stamina too"), active=True)
        group.add(self.with_hp)
        self.step = self.spin(0.5, 100, 3, 0.5, 1)
        self.row(group, tr("Move by (metres)"), self.step,
                 self.button(tr("Up"), lambda: self.nudge(1)),
                 self.button(tr("Down"), lambda: self.nudge(-1)))
        self.show_slot()

        warp = self.group(page, tr("Warp to a lamp"),
                          tr("Unlit ones too. The target becomes your last lamp."))
        try:
            self.lamps = gamedata.lamps()
        except Exception as error:  # no game files: the rest should still work
            self.lamps = []
            warp.set_description(GLib.markup_escape_text(
                tr("Could not load the lamp list: {}").format(error)))
        for point, name in self.lamps:
            self.row(warp, name, self.button(tr("Go"), lambda p=point: self.warp(p)))

        bosses = self.group(page, tr("Bosses"), tr(
            "“Go” puts you in front of the fight entrance. “Revive” clears the defeat flag; the "
            "boss is back after “Go”. The pin saves your current spot as your own entrance. Back "
            "up your save in the Game tab before reviving."))
        for flag, name, entry in gamedata.bosses():
            row = self.row(bosses, name)
            row.add_suffix(self.button(tr("Check"), lambda f=flag, r=row: r.set_subtitle(
                tr("defeated") if self.game.get_event_flag(f) else tr("alive"))))
            row.add_suffix(self.button(
                tr("Revive"), lambda f=flag, r=row: self.set_boss(f, r, False)))
            row.add_suffix(self.button(
                tr("Defeated"), lambda f=flag, r=row: self.set_boss(f, r, True)))
            pin = Gtk.Button(valign=Gtk.Align.CENTER)
            self.show_pin(pin, flag)
            pin.connect("clicked", lambda b, f=flag: self.run(lambda: self.pin_entry(b, f)))
            row.add_suffix(pin)
            row.add_suffix(self.button(
                tr("Go"), lambda f=flag, e=entry: self.warp_boss(f, e)))

    def page_enemies(self, page):
        group = self.group(page, tr("Behaviour"))
        for toggle in ENEMY_TOGGLES:
            self.switch(group, *toggle)
        self.near_group = self.group(page, tr("Nearby (closest first)"),
                                     tr("Refreshes by itself while this tab is visible"))
        self.near_rows = []
        for index in range(10):
            row = Adw.ActionRow(title="—", visible=False)
            for label, action in ((tr("Kill"), lambda c: self.game.set_hp(c, 0)),
                                  ("1 HP", lambda c: self.game.set_hp(c, 1)),
                                  (tr("Full"), self.fill_enemy),
                                  (tr("Freeze HP"), self.freeze_enemy),
                                  (tr("Go to"), self.goto_enemy)):
                row.add_suffix(self.button(
                    label, lambda i=index, a=action: self.on_enemy(i, a)))
            self.near_group.add(row)
            self.near_rows.append([row, 0])

    def page_items(self, page):
        options = self.group(page, tr("Add an item"), tr(
            "Click a group to open it. Story items can break your save."))
        self.amount = self.spin(1, 999, 20)
        self.row(options, tr("Amount"), self.amount,
                 subtitle=tr("Weapons and attire are added one at a time"))
        self.upgrade = self.spin(0, 10, 0)
        self.row(options, tr("Weapon upgrade"), self.upgrade, subtitle=tr("+0 to +10"))
        self.variant = Gtk.DropDown.new_from_strings(
            [tr(n) for n, _ in gamedata.WEAPON_VARIANTS])
        self.variant.set_valign(Gtk.Align.CENTER)
        self.row(options, tr("Weapon variant"), self.variant,
                 subtitle=tr("Uncanny and Lost have different gem slots"))
        self.popup = Adw.SwitchRow(title=tr("Popup in game"), active=True,
                                   subtitle=tr("The game shows the item you received"))
        options.add(self.popup)
        search = Gtk.SearchEntry(placeholder_text=tr("Search by in-game name…"))
        options.add(search)
        results = self.group(page, "")
        try:
            catalog = gamedata.catalog()
        except Exception as error:
            catalog = []
            options.set_description(GLib.markup_escape_text(
                tr("Could not load the item list: {}").format(error)))
        groups = []
        for title, items in catalog:
            expander = Adw.ExpanderRow(title=GLib.markup_escape_text(tr(title)),
                                       subtitle=tr("Items: {}").format(len(items)))
            rows = []
            for item in items:
                row = Adw.ActionRow(title=GLib.markup_escape_text(item["name"]))
                row.add_suffix(self.button(tr("Add"), lambda i=item: self.give(i)))
                expander.add_row(row)
                rows.append((row, item["name"].casefold()))
            results.add(expander)
            groups.append((expander, rows))

        def filter_rows(entry):
            text = entry.get_text().strip().casefold()
            for expander, rows in groups:
                found = 0
                for row, key in rows:
                    row.set_visible(text in key)
                    found += text in key
                expander.set_visible(found > 0)
                expander.set_expanded(bool(text) and found > 0)

        search.connect("search-changed", filter_rows)

    def page_stats(self, page):
        group = self.group(page, tr("Character"), tr(
            "Changes are saved by the game. HP and stamina update after a reload."))
        self.stat_spins = {}
        for name in engine.STATS:
            high = 999_999_999 if name == "Blood echoes" else 999 if name == "Level" else 99
            spin = self.spin(0, high, 0)
            self.stat_spins[name] = spin
            self.row(group, tr(name), spin,
                     self.button(tr("Set"), lambda n=name: self.set_stat(n)))
        self.ng_spin = self.spin(0, 7, 0)
        self.row(group, tr("NG+ cycle"), self.ng_spin, self.button(tr("Set"), self.set_ng))
        self.row(group, tr("Values from the game"), self.button(tr("Read"), self.read_stats))

    def page_game(self, page):
        group = self.group(page, tr("Game"))
        self.speed = self.spin(0.1, 3.0, 1.0, 0.1, 2)
        self.speed.connect("value-changed", lambda s: self.game.set_speed(s.get_value()))
        self.row(group, tr("Game speed"), self.speed,
                 self.button("1×", lambda: self.speed.set_value(1.0)))
        self.row(group, tr("Quit to main menu"),
                 self.button(tr("Quit"), lambda: self.game.return_to_title()),
                 subtitle=tr("A quick reset"))
        self.row(group, tr("Restore story"), self.button(tr("Restore"), self.restore_story),
                 subtitle=tr("After a Gehrman / Moon Presence fight (a warp does it too)"))
        self.row(group, tr("Save backup"), self.button(tr("Back up"), self.backup_saves),
                 subtitle=tr("To {}").format(STATE_DIR / "saves"))
        view = self.group(page, tr("View"))
        self.hitboxes = Adw.SwitchRow(
            title=tr("Attack hitboxes"),
            subtitle=tr("A yellow mesh shows where and when a hit lands (yours and enemies')"))
        view.add(self.hitboxes)
        keys = self.group(page, tr("Shortcuts"))
        self.keyboard_on = Adw.SwitchRow(title=tr("Keyboard (in game and in the trainer)"),
                                         active=True)
        self.pad_on = Adw.SwitchRow(
            title=tr("Gamepad: hold Select/View + D-pad"), active=True,
            subtitle=tr("Up save, down load, left heal, right warp"))
        keys.add(self.keyboard_on)
        keys.add(self.pad_on)
        for _, _, key, text, _ in HOTKEYS:
            self.row(keys, tr(text), Gtk.Label(label=key))
        setup = self.group(page, tr("Setup"))
        self.bbport_row = self.row(
            setup, "bbport", self.button(tr("AppImage or script…"), self.pick_bbport_file),
            self.button(tr("Folder…"), self.pick_bbport_folder))
        self.show_bbport()
        codes = list(i18n.LANGUAGES)
        language = Gtk.DropDown.new_from_strings(list(i18n.LANGUAGES.values()))
        language.set_selected(codes.index(i18n.LANGUAGE))
        language.set_valign(Gtk.Align.CENTER)
        language.connect("notify::selected",
                         lambda drop, _: self.run(
                             lambda: self.set_language(codes[drop.get_selected()])))
        self.row(setup, "Language / Język", language)
        note = self.group(page, tr("Warning"))
        self.row(note, tr("Do not use in online co-op"),
                 subtitle=tr("Flags and speed changes ruin the other player's session"))

    # ---------------------------------------------------------------- setup
    def show_bbport(self):
        install = bbport.find()
        self.bbport_row.set_subtitle(GLib.markup_escape_text(
            str(install.path) if install else tr("not found: pick it with a button")))

    def pick_bbport_file(self):
        self.file_dialog(tr("bbport: the AppImage, Bloodborne.sh or bbport_launcher.py"),
                         "open", self.use_bbport)

    def pick_bbport_folder(self):
        self.file_dialog(tr("The bbport folder"), "select_folder", self.use_bbport)

    def file_dialog(self, title, method, then):
        dialog = Gtk.FileDialog(title=title)

        def done(dialog, result):
            try:
                chosen = getattr(dialog, method + "_finish")(result)
            except GLib.Error:      # cancelled
                self.start_after_choice = False
                return
            self.run(lambda: then(chosen.get_path()))

        getattr(dialog, method)(self, None, done)

    def use_bbport(self, path):
        start, self.start_after_choice = self.start_after_choice, False
        try:
            bbport.choose(path)
        except ValueError as error:
            raise engine.TrainerError(str(error)) from error
        self.show_bbport()
        if not self.lamps:      # no game files at startup; a restart reads them again
            self.toast(tr("Saved. Restart the trainer to load the lamp and item lists."))
            return
        self.toast(tr("Saved."))
        if start:
            self.start_game()

    def set_language(self, code):
        config.put("language", code)
        self.toast(i18n.translate("Restart the trainer to change the language.", code))

    # ---------------------------------------------------------------- actions
    def toast(self, text):
        toast = Adw.Toast(title=GLib.markup_escape_text(text), timeout=3)
        self.overlay.add_toast(toast)

    def run(self, action):
        try:
            action()
        except (engine.TrainerError, OSError, TypeError, struct.error) as error:
            self.toast(str(error) or tr("That did not work"))

    def heal(self):
        self.game.full_heal()

    def toggle_no_dead(self):
        row = self.toggles["no_dead"]
        row.set_active(not row.get_active())
        self.toast(tr("No death on") if row.get_active() else tr("No death off"))

    def load_positions(self):
        try:
            return json.loads(POSITIONS.read_text())
        except (OSError, ValueError):
            return {}

    def show_slot(self):
        self.slot = self.slot_drop.get_selected()
        saved = self.positions.get(str(self.slot))
        self.slot_row.set_subtitle(
            tr("empty") if not saved
            else "x {:.1f}  y {:.1f}  z {:.1f}".format(*saved["position"]))

    def save_position(self):
        player = self.game.need_world()
        where = self.game.position(player)
        if where is None:
            raise engine.TrainerError(tr("cannot read the position"))
        hp, _, stamina, _ = self.game.vitals(player)
        self.positions[str(self.slot)] = {"position": where[0], "rotation": where[1],
                                          "map": self.game.map_id(), "hp": hp, "stamina": stamina}
        self.write_positions()
        self.show_slot()
        self.toast(tr("Position saved in slot {}").format(self.slot + 1))

    def load_position(self):
        player = self.game.need_world()
        saved = self.positions.get(str(self.slot))
        if not saved:
            raise engine.TrainerError(tr("this slot is empty"))
        if saved["map"] != self.game.map_id():
            raise engine.TrainerError(tr("that position is on another map: warp there first"))
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
        if story:  # set again on every attempt: the game changes these flags after the fight
            for story_flag, value in story.items():
                self.game.set_event_flag(story_flag, value)
        self.game.warp_position(*target)
        self.forced_spawn = {"unloaded": False, "stable_since": None,
                             "deadline": time.monotonic() + 90}
        self.last_warp = lambda: self.warp_boss(flag, entry)

    # ---------------------------------------------------------------- late-game fights
    def ask_story(self, flag, entry):
        name = next(n for f, n, _ in gamedata.BOSSES if f == flag)
        dialog = Adw.AlertDialog(
            heading=name,
            body=tr("This is a late-game fight. The trainer backs up your save, sets the story "
                    "flags and restores them when you warp somewhere else.\n\n"
                    "A real win ends the game and starts NG+. In practice mode the boss "
                    "recovers its HP when it drops below 25% and one-hit kill is off."))
        dialog.add_response("cancel", tr("Cancel"))
        dialog.add_response("real", tr("Killable"))
        dialog.add_response("practice", tr("Practice"))
        dialog.set_response_appearance("real", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("practice", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("practice")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, answer: answer != "cancel" and self.run(
            lambda: self.start_story(flag, entry, answer == "practice")))
        dialog.present(self)

    def start_story(self, flag, entry, practice):
        self.game.need_world()
        self.backup_saves()  # no backup, no story changes
        if "story" not in self.positions:
            # store the originals once: the next fight must not overwrite them with changed ones
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
            self.toast(tr("Story state restored"))
        else:
            self.toast(tr("The game moved to a new cycle: not restoring old flags"))
        del self.positions["story"]
        self.story_flag = None
        self.write_positions()

    def guard_story_boss(self):
        """Practice mode: a boss in the Dream must not die, because that ends the game."""
        if not (self.story_flag and self.story_practice) or self.game.map_id() != 0x15000000:
            return
        self.toggles["one_hit"].set_active(False)
        self.game.set_flag("one_hit", False)
        for chr_ in self.game.characters():
            vitals = self.game.vitals(chr_)
            if vitals and vitals[1] >= 5000 and 0 < vitals[0] < vitals[1] * 0.25:
                self.game.set_i32(self.game.chr_data(chr_) + 0xF8, vitals[1])
                self.toast(tr("The boss recovered its HP (practice mode)"))

    def repeat_warp(self):
        if self.last_warp is None:
            raise engine.TrainerError(tr("no warp yet"))
        self.last_warp()

    def show_pin(self, button, flag):
        saved = f"boss:{flag}" in self.positions
        button.set_label("↺" if saved else "📌")  # theme icons can be hard to read
        button.set_tooltip_text(tr("Back to the default entrance") if saved
                                else tr("Save this spot as the entrance to this boss"))

    def pin_entry(self, button, flag):
        key = f"boss:{flag}"
        if self.positions.pop(key, None) is None:
            where = self.game.position(self.game.need_world())
            if where is None:
                raise engine.TrainerError(tr("cannot read the position"))
            self.positions[key] = {"position": where[0], "rotation": where[1],
                                   "map": self.game.map_id()}
            self.toast(tr("“Go” will now bring you to this spot"))
        else:
            self.toast(tr("Default entrance restored"))
        self.write_positions()
        self.show_pin(button, flag)

    def write_positions(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        POSITIONS.write_text(json.dumps(self.positions))

    def finish_forced_spawn(self, in_world):
        """Removes the forced spawn marker, but only once loading has surely finished: the game
        reads it late, and "in world" can flicker during a load."""
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
        row.set_subtitle(tr("defeated") if self.game.get_event_flag(flag) else tr("alive"))

    def on_enemy(self, index, action):
        self.game.need_world()
        chr_ = self.near_rows[index][1]
        if chr_ not in self.game.characters():
            raise engine.TrainerError(tr("that character is gone"))
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

    def give(self, item):
        name = item["name"]
        popup = self.popup.get_active()
        if item["kind"] == "goods":
            added = self.game.give_goods(item["id"], int(self.amount.get_value()), popup)
            self.toast(tr("Added {} × {}").format(added, name))
        elif item["kind"] == "armor":
            self.game.give_equipment(engine.CATEGORY_ARMOR, item["id"], popup)
            self.toast(tr("Added: {}").format(name))
        else:
            variant, offset = gamedata.WEAPON_VARIANTS[self.variant.get_selected()]
            note = ""
            if offset not in item["levels"]:  # e.g. firearms: normal only
                note = tr(" – there is no {} variant, gave the normal one").format(tr(variant))
                offset = 0
            levels = item["levels"][offset]
            level = min(int(self.upgrade.get_value()), max(levels))
            level = max(i for i in levels if i <= level)
            self.game.give_equipment(engine.CATEGORY_WEAPON, levels[level], popup)
            extra = f" ({variant})" if offset else ""
            self.toast(tr("Added: {}").format(f"{name} +{level}{extra}{note}"))

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
            raise engine.TrainerError(tr("press “Read” first, so you do not write zeros"))
        self.game.set_i32(self.game.game_data() + engine.STATS[name],
                          self.stat_spins[name].get_value())

    def set_ng(self):
        self.game.need_world()
        if not getattr(self, "stats_read", False):
            raise engine.TrainerError(tr("press “Read” first"))
        self.game.set_i32(self.game.ptr(engine.BASE + engine.GAME_DATA_MAN) + engine.NG_CYCLE,
                          self.ng_spin.get_value())

    def backup_saves(self):
        install = bbport.find()
        if not install:
            raise engine.TrainerError(tr("bbport not found: pick it in the Game tab"))
        source = bbport.user_dir(install) / "savedata"
        if not source.is_dir():
            raise engine.TrainerError(tr("no saves found in {}").format(source))
        target = STATE_DIR / "saves" / time.strftime("%Y-%m-%d_%H-%M-%S")
        shutil.copytree(source, target, dirs_exist_ok=True)
        self.toast(tr("Backup: {}").format(target))

    # ---------------------------------------------------------------- the game
    def start_game(self):
        if engine.find_game_pids():
            self.toast(tr("The game is already running."))
            return
        install = bbport.find()
        if not install:
            self.ask_bbport()
            return
        if install.kind == "appimage" and not os.access(install.path, os.X_OK):
            self.alert(tr("The AppImage is not executable"),
                       f"chmod +x \"{install.path}\"")
            return
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(GAME_LOG, "wb") as log:
                self.child = subprocess.Popen(install.command(), stdout=log,
                                              stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            self.alert(tr("Could not start the game"), str(error))
            return
        self.toast(tr("Starting the game…"))

    def alert(self, heading, body):
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.add_response("ok", "OK")
        dialog.present(self)

    def ask_bbport(self):
        dialog = Adw.AlertDialog(heading=tr("Where is bbport?"), body=tr(
            "The trainer could not find bbport. Pick its AppImage, Bloodborne.sh, or the "
            "folder with the source."))
        dialog.add_response("cancel", tr("Cancel"))
        dialog.add_response("folder", tr("Folder…"))
        dialog.add_response("file", tr("AppImage or script…"))
        dialog.set_response_appearance("file", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_close_response("cancel")

        def answered(_dialog, answer):
            if answer != "cancel":
                self.start_after_choice = True
                (self.pick_bbport_file if answer == "file" else self.pick_bbport_folder)()

        dialog.connect("response", answered)
        dialog.present(self)

    def report_start_failure(self):
        try:
            lines = GAME_LOG.read_text(errors="replace").strip().splitlines()
        except OSError:
            lines = []
        text = "\n".join(lines[-6:]) or tr("no message")
        if "cmake" in text:
            text += "\n\n" + tr("bbport built from source needs cmake: install it with your "
                                "package manager.")
        self.alert(tr("The game closed with an error"),
                   text + "\n\n" + tr("Full log: {}").format(GAME_LOG))

    def reap(self):
        if self.child and self.child.poll() is not None:
            if self.child.returncode > 0:
                self.report_start_failure()
            self.child = None
        elif not self.child:
            try:  # orphaned game processes (we are their subreaper)
                while os.waitpid(-1, os.WNOHANG)[0]:
                    pass
            except ChildProcessError:
                pass

    # ---------------------------------------------------------------- the loop
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
        if self.hitboxes.get_active() or self.game.hitboxes:
            self.game.set_hitboxes(self.hitboxes.get_active())
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
                self.hp_row.set_subtitle(tr("not in the game world"))
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
