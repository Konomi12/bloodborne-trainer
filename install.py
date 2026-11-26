#!/usr/bin/env python3
"""Adds "Bloodborne Trainer" to the application menu. No root needed.

    ./install.py              menu entry
    ./install.py --desktop    also an icon on the desktop
    ./install.py --uninstall  removes both
"""
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import bbport  # noqa: E402
import config  # noqa: E402
import requirements  # noqa: E402

NAME = "bloodborne-trainer.desktop"
HERE = Path(__file__).resolve().parent


def quote(argument):
    """One argument of a desktop entry's Exec line."""
    escaped = re.sub(r'(["`$\\])', r"\\\1", argument)
    return '"' + escaped.replace("\\", "\\\\").replace("%", "%%") + '"'


def entry():
    icon = config.DATA_HOME / "icons/hicolor/256x256/apps/bbport.png"
    return ("[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Bloodborne Trainer\n"
            "Comment=Practice trainer for Bloodborne (bbport)\n"
            "Comment[pl]=Trainer do ćwiczenia w Bloodborne (bbport)\n"
            f"Exec={quote(sys.executable)} {quote(str(HERE / 'trainer.py'))}\n"
            f"Icon={icon if icon.is_file() else 'applications-games'}\n"
            "Terminal=false\n"
            "Categories=Game;\n"
            "StartupWMClass=io.github.bbtrainer\n")


def main(arguments):
    unknown = set(arguments) - {"--desktop", "--uninstall"}
    if unknown:
        print(__doc__)
        return 0 if unknown <= {"-h", "--help"} else 2
    menu = config.DATA_HOME / "applications" / NAME
    desktop = bbport.desktop_dir() / NAME
    if "--uninstall" in arguments:
        for path in (menu, desktop):
            if path.is_file():
                path.unlink()
                print("Removed", path)
        print(f"Your saved positions and save backups stay in {config.DATA_HOME / 'bb-trainer'}")
        return 0
    requirements.check()
    targets = [menu]
    if "--desktop" in arguments:
        if desktop.parent.is_dir() and desktop.parent != Path.home():
            targets.append(desktop)
        else:
            print("No desktop folder found: only the menu entry is created.")
    for path in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry())
        path.chmod(0o755)   # some desktops only start executable entries
        print("Created", path)
    found = bbport.find()
    print(f"bbport found: {found.path}" if found
          else "bbport not found yet: the trainer asks for it when you press Start game.")
    print("Keep this folder where it is: the shortcut points to it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
