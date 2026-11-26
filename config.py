"""The trainer's own settings (~/.config/bb-trainer/config.json)."""
import json
import os
from pathlib import Path

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
CONFIG_FILE = CONFIG_HOME / "bb-trainer/config.json"


def read_json(path):
    """The object in a JSON file, or {} when it is missing or broken."""
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def get(key):
    return read_json(CONFIG_FILE).get(key)


def put(key, value):
    values = read_json(CONFIG_FILE)
    values[key] = value
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(values, indent=2))
