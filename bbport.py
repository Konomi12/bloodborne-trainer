"""Finds the user's bbport and Bloodborne files: how to start the game and where its data lives.

bbport comes in three shapes: the AppImage, the "folder" package (Bloodborne.sh next to app/)
and the source tree. All three are started with --play, which skips the launcher window.
"""
import os
import shlex
import shutil
import sys
from pathlib import Path

import config
from i18n import tr

NAME_HINTS = ("bbport", "bloodborne")


class Install:
    def __init__(self, kind, path):
        self.kind = kind            # "appimage" | "folder" | "source"
        self.path = Path(path)      # the AppImage file, or the folder

    def __eq__(self, other):
        return isinstance(other, Install) and (self.kind, self.path) == (other.kind, other.path)

    def command(self):
        if self.kind == "appimage":
            return [str(self.path), "--play"]
        if self.kind == "folder":
            return [str(self.path / "Bloodborne.sh"), "--play"]
        return [python(), str(self.path / "launcher/bbport_launcher.py"), "--play"]

    def data_dir(self):
        """Where bbport keeps bbport.ini and (unless moved) the saves."""
        if os.environ.get("BB_DATA_DIR"):
            return Path(os.environ["BB_DATA_DIR"])
        return self.path if self.kind == "source" else config.DATA_HOME / "bbport"


def in_appimage():
    """True when the trainer runs from its AppImage (the bundled Python and GTK)."""
    return "BB_TRAINER_VARS" in os.environ


def python():
    """The Python for bbport's source tree: the system's, not the one bundled in the AppImage."""
    if in_appimage():
        return shutil.which("python3", path=child_env().get("PATH")) or "python3"
    return sys.executable


def child_env():
    """The environment for programs the trainer starts, without what its AppImage set up."""
    env = dict(os.environ)
    for name in env.pop("BB_TRAINER_VARS", "").split():
        saved = env.pop("BB_TRAINER_SAVED_" + name, None)
        if saved is None:
            env.pop(name, None)
        else:
            env[name] = saved
    for name in ("APPDIR", "APPIMAGE", "ARGV0", "OWD"):
        env.pop(name, None)
    return env


def identify(path):
    """The Install a file or folder belongs to, or None."""
    path = Path(path).expanduser()
    try:
        if path.is_file():
            if path.name.lower().endswith(".appimage"):
                return Install("appimage", path)
            if path.name == "Bloodborne.sh":
                return Install("folder", path.parent)
            if path.name == "bbport_launcher.py" and path.parent.name == "launcher":
                return Install("source", path.parent.parent)
            if path.name == "run.sh" and (path.parent / "launcher/bbport_launcher.py").is_file():
                return Install("source", path.parent)
        elif path.is_dir():
            if (path / "launcher/bbport_launcher.py").is_file():
                return Install("source", path)
            if (path / "Bloodborne.sh").is_file():
                return Install("folder", path)
    except OSError:
        pass
    return None


def _user_dir_named(key, fallback):
    """A localised user folder (Desktop, Downloads) from user-dirs.dirs."""
    try:
        for line in (config.CONFIG_HOME / "user-dirs.dirs").read_text().splitlines():
            if line.startswith(key + "="):
                value = line.split("=", 1)[1].strip().strip('"')
                return Path(value.replace("$HOME", str(Path.home())))
    except OSError:
        pass
    return Path.home() / fallback


def desktop_dir():
    return _user_dir_named("XDG_DESKTOP_DIR", "Desktop")


def _looks_like_bbport(path):
    text = str(path).lower()
    return any(hint in text for hint in NAME_HINTS)


def _from_shortcuts():
    """Installs named by menu and desktop entries, the ones that start the game first."""
    found = []
    for folder in (config.DATA_HOME / "applications", desktop_dir()):
        for entry in folder.glob("*.desktop"):
            try:
                lines = entry.read_text(errors="replace").splitlines()
                age = entry.stat().st_mtime
            except OSError:
                continue
            for line in lines:
                if not line.startswith("Exec="):
                    continue
                try:
                    words = shlex.split(line[5:])
                except ValueError:
                    continue
                for word in words:
                    if not word.startswith("/") or not _looks_like_bbport(word):
                        continue
                    install = identify(word)
                    if install:
                        found.append(("--play" not in words, -age, install))
    return [install for _, _, install in sorted(found, key=lambda e: e[:2])]


def _from_folders():
    """Installs lying in the usual places, newest first."""
    home = Path.home()
    places = [_user_dir_named("XDG_DOWNLOAD_DIR", "Downloads"), desktop_dir(), home,
              home / "Applications", home / "AppImages", home / "Games", home / ".local/bin"]
    found = {}
    for place in places:
        try:
            children = list(place.iterdir())
        except OSError:
            continue
        for child in children:
            candidates = [child]
            if child.is_dir() and _looks_like_bbport(child.name):
                try:
                    candidates += list(child.iterdir())
                except OSError:
                    pass
            for candidate in candidates:
                if candidate.is_file() and not (candidate.suffix.lower() == ".appimage"
                                                and _looks_like_bbport(candidate.name)):
                    continue
                install = identify(candidate)
                if install:
                    try:
                        found[str(install.path)] = (install.path.stat().st_mtime, install)
                    except OSError:
                        pass
    return [install for _, install in sorted(found.values(), key=lambda e: -e[0])]


def find():
    """The bbport to use: the chosen one, else the first one found. None when there is none."""
    saved = config.get("bbport")
    if saved:
        install = identify(saved)
        if install:
            return install
    for install in _from_shortcuts():
        return install
    source = identify(Path.home() / "bbport")
    if source:
        return source
    for install in _from_folders():
        return install
    return None


def choose(path):
    """Remembers the bbport the user picked. Raises ValueError for anything else."""
    install = identify(path)
    if not install:
        raise ValueError(tr("This is not bbport. Pick the AppImage, Bloodborne.sh or "
                            "launcher/bbport_launcher.py."))
    config.put("bbport", str(install.path))
    return install


# ---------------------------------------------------------------- the user's bbport settings
def launcher_settings():
    return config.read_json(config.CONFIG_HOME / "bbport-launcher/settings.json")


def game_dir(install=None):
    """The Bloodborne folder (the one with eboot.bin)."""
    value = launcher_settings().get("game_dir")
    if value:
        return Path(value).expanduser()
    if install and install.kind == "source":   # the launcher's default for a source tree
        return install.path.parent / "CUSA03173"
    return None


def user_dir(install):
    value = launcher_settings().get("user_dir") or os.environ.get("BB_USER_DIR")
    if value:
        path = Path(value).expanduser()
        return path if path.is_absolute() else install.data_dir() / path
    return install.data_dir() / "user"


def ini_value(install, key):
    if not install:
        return None
    ini = Path(os.environ.get("BB_CONFIG") or install.data_dir() / "bbport.ini")
    try:
        for line in ini.read_text(errors="replace").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None
