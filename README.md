# Bloodborne Trainer for bbport (Linux)

A practice tool in the style of SilkySouls, for Bloodborne running on
[bbport](https://github.com/deadinside28/bloodborne_pc), the native PC port.
[Po polsku](README.pl.md).

## What you need
- 64-bit Linux.
- bbport (tested with 0.7): the AppImage, the folder package or the source tree. Start the game
  once from bbport's own launcher first, so the game folder is chosen.
- Your own dump of Bloodborne, version **1.09**. No game files are included.
- Python 3.9+, GTK 4 and libadwaita 1.5+ with Python bindings:

| Distribution | Command |
|---|---|
| Arch, CachyOS, EndeavourOS | `sudo pacman -S python python-gobject gtk4 libadwaita` |
| Fedora | `sudo dnf install python3-gobject gtk4 libadwaita` |
| Ubuntu 24.04+, Debian 13+ | `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` |
| openSUSE Tumbleweed | `sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1` |

Tested on CachyOS with bbport 0.7 (AppImage and source). Other distributions, SteamOS / Steam
Deck and the folder package are **untested**; reports are welcome.

## Install
### AppImage (easiest)
Download `bb-trainer-…-x86_64.AppImage` from
[Releases](https://github.com/Konomi12/bb-trainer/releases). It has its own Python, GTK 4 and
libadwaita, so the packages above are not needed. Then:

```bash
chmod +x bb-trainer-*-x86_64.AppImage
./bb-trainer-*-x86_64.AppImage --install
```

`--install` adds it to the application menu (`--install --desktop` also to the desktop,
`--uninstall` removes both); you can also just run the file. It draws in software; if you want
the GPU, start it with `BB_TRAINER_GL=1`.

### From source
Download or clone this repository to a place where it can stay, then in its folder:

```bash
./install.py
```

This adds "Bloodborne Trainer" to the application menu (`--desktop` also puts an icon on the
desktop, `--uninstall` removes both). Nothing is installed system-wide. You can also just run
`./trainer.py`.

## Use
1. Open the trainer.
2. Press **Start game**. `./trainer.py --play` does it right away.
3. Load your character.

**The game has to be started from the trainer.** Linux does not let a program touch the memory
of a game it did not start. Your bbport settings, patches, mods and saves are used as usual.

The trainer looks for bbport in your shortcuts, in `~/bbport` and in the usual folders
(Downloads, Applications, Games…). If it picks the wrong one or finds none, choose it in
**Game → Setup**. The interface language (English, Polish) is there too.

## Features
- **Player:** HP, healing, always full HP / stamina, no death, one-hit kill, infinite bullets
  and items, invisibility, silence.
- **Travel:** 5 position slots, move up/down, warp to any lamp, bosses (check, revive, mark as
  defeated, warp in front of the fight entrance, pin your own entrance). Gehrman and Moon
  Presence work early too: the trainer backs up your save, sets the story flags and restores
  them when you warp elsewhere. A real win ends the game (NG+); practice mode prevents it.
- **Enemies:** disable AI and attacks, damage flags, nearby list (kill, 1 HP, freeze).
- **Items:** grouped and searchable; weapons (upgrade level and variant), attire and
  consumables, with the in-game "acquired" popup.
- **Stats:** attributes, level, blood echoes, insight, NG+ cycle.
- **Game:** game speed, attack hitboxes, quit to the main menu, save backup.

Bosses of The Old Hunters are listed only when your game files contain the DLC maps.

## Shortcuts
| Key | Gamepad (hold Select/View) | Action |
|---|---|---|
| F5 | D-pad up | save position |
| F6 | D-pad down | load position |
| F7 | D-pad left | full heal |
| F8 | | no death on/off |
| F10 | D-pad right | repeat the last warp |

## Be careful
- Changes to stats, items and boss flags **stay in your save**. Use *Game → Save backup* first.
  Backups are in `~/.local/share/bb-trainer/saves`.
- **Do not use it in online play.**
- Closing the trainer turns its cheats off and gives the game its original code back. Until you
  use a feature, the game plays as it did before.
- If you close the trainer while the game runs, a new trainer window cannot attach to that game:
  restart the game from it.

## Troubleshooting
- **"Your system blocks access to game memory (ptrace_scope)"**: your system has
  `kernel.yama.ptrace_scope` set to 2 or 3. With 2 you can lower it to the common default until
  the next reboot: `sudo sysctl kernel.yama.ptrace_scope=1`. This relaxes a security setting;
  3 can only be changed in the system configuration and needs a reboot.
- **"Game files not found"**: open bbport's launcher and choose the game folder (the one with
  `eboot.bin`), then restart the trainer.
- **"Unexpected game version"**: the game needs update 1.09.
- **The game closes at once**: the trainer shows the last lines; the full log is
  `~/.local/share/bb-trainer/game.log`. Check that bbport's own launcher can start the game.
- **Gamepad shortcuts do nothing**: your user needs read access to `/dev/input/event*` for the
  pad (desktop sessions normally grant it).

## How it works
`engine.py` reads and writes the memory of the `bb-probe` process. A small stub (`stub.s`) in the
game's main loop scales the frame time and runs game functions on the game's thread. Lamps, item
names and groups are read from your game files by `gamedata.py`. The addresses are for version
1.09 only; before touching anything the trainer compares the bytes and leaves other versions
alone.

New interface languages go into `i18n.py`.

## Credits
- [bbport](https://github.com/deadinside28/bloodborne_pc) and its BBSC code, a source of
  offsets.
- Debug flag names from the game's own debug menu.
- Character data layout as in
  [Bloodborne-save-editor](https://github.com/Noxde/Bloodborne-save-editor) by Noxde.

Unofficial fan tool, not affiliated with FromSoftware or Sony.

## License
[GPL-2.0-or-later](LICENSE), the same as bbport. No warranty.
