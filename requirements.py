"""Checks that the system has what the trainer needs, with a readable message when not."""
import shutil
import subprocess
import sys

INSTALL = """Install the missing packages with your package manager:
  Arch, CachyOS, EndeavourOS:  sudo pacman -S python python-gobject gtk4 libadwaita
  Fedora:                      sudo dnf install python3-gobject gtk4 libadwaita
  Ubuntu 24.04+, Debian 13+:   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
  openSUSE Tumbleweed:         sudo zypper install python3-gobject typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1"""


def problem():
    """What is missing, or None when everything is there."""
    if sys.version_info < (3, 9):
        return "Python 3.9 or newer is required."
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw
    except (ImportError, ValueError) as error:
        return f"GTK 4 / libadwaita for Python is missing ({error}).\n\n{INSTALL}"
    version = (Adw.get_major_version(), Adw.get_minor_version())
    if version < (1, 5):
        return ("libadwaita 1.5 or newer is required, this system has "
                f"{version[0]}.{version[1]}. Use a newer release of your distribution.")
    return None


def check():
    """Exits with the explanation when something is missing."""
    message = problem()
    if not message:
        return
    print(f"Bloodborne Trainer: {message}", file=sys.stderr)
    if not sys.stderr.isatty() and shutil.which("notify-send"):  # started from the menu
        subprocess.run(["notify-send", "Bloodborne Trainer", message], check=False)
    raise SystemExit(1)
