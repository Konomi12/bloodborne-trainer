"""Listy lamp i przedmiotów czytane z plików gry użytkownika (DCX / BND4 / FMG / EMEVD)."""
import glob
import json
import math
import os
import struct
import zlib
from pathlib import Path

LAUNCHER_CONFIG = Path.home() / ".config/bbport-launcher"
BBPORT = Path.home() / "bbport"

# (flaga pokonania, nazwa, wejście)
# Wejście z plików map (MSB): (mapa, punkt bramy mgły, punkt po wewnętrznej stronie, odstęp).
# Trainer stawia gracza `odstęp` metrów przed bramą, twarzą do areny. None: walka zaczyna się
# od rozmowy we Śnie, więc wystarczy lampa.
BOSSES = [
    (12411700, "Cleric Beast",
     ("m24_01", (-154.14, -27.02, 35.16), (-123.5, -27.02, 65.7), 2.5)),
    (12411800, "Father Gascoigne",
     ("m24_01", (-50.18, -40.82, 71.02), (-36.14, -40.9, 89.36), 2.5)),
    (12301800, "Blood-starved Beast",
     ("m23_00", (-87.65, -126.44, 13.51), (-88.33, -126.48, 14.02), 2.5)),
    (12301700, "Darkbeast Paarl",
     ("m23_00", (135.45, -120.3, -85.78), (134.63, -120.12, -85.41), 2.5)),
    (12401800, "Vicar Amelia",
     ("m24_00", (51.51, 35.71, 311.57), (68.84, 35.71, 341.47), 2.5)),
    (12201800, "Witch of Hemwick",
     ("m22_00", (-329.8, 2.5, 698.3), (-329.75, 1.6, 699.3), 1.3)),
    (12701800, "Shadow of Yharnam",
     ("m27_00", (-322.92, -185.87, 494.39), (-327.27, -186.07, 489.79), 2.5)),
    (13201800, "Rom, the Vacuous Spider",
     ("m32_00", (-452.87, -175.03, 392.65), (-487.0, -175.0, 379.0), 2.5)),
    (12801800, "The One Reborn",
     ("m28_00", (381.0, -122.9, -215.6), (381.64, -122.49, -216.24), 1.2)),
    (12421700, "Celestial Emissary",
     ("m24_02", (-5.47, 55.34, 293.41), (-4.84, 55.34, 292.98), 2.5)),
    (12421800, "Ebrietas",
     ("m24_02", (94.0, 4.17, 387.0), (94.4, 4.17, 387.68), 2.5)),
    (12501800, "Martyr Logarius",
     ("m25_00", (33.93, 112.32, -330.56), (47.83, 111.87, -350.42), 2.5)),
    (13301800, "Amygdala",
     ("m33_00", (-47.18, 1461.0, -69.05), (-48.22, 1461.0, -68.64), 2.5)),
    (12601850, "Micolash",
     ("m26_00", (145.88, 1032.98, -14.74), (164.86, 1032.98, -14.67), 2.5)),
    (12601800, "Mergo's Wet Nurse",
     ("m26_00", (122.14, 1125.18, -37.84), (141.97, 1125.08, -37.67), 2.5)),
    (12101800, "Gehrman",
     ("m21_00", (13.16, -9.98, -36.54), (20.0, -10.0, -37.0), 1.7)),
    (12101850, "Moon Presence",
     ("m21_00", (13.16, -9.98, -36.54), (20.0, -10.0, -37.0), 1.7)),
    (13401800, "Ludwig",
     ("m34_00", (-407.93, 1503.8, -716.45), (-407.93, 1503.79, -744.64), 2.5)),
    (13401850, "Laurence",
     ("m34_00", (-450.9, 1535.71, -292.69), (-436.53, 1535.71, -266.01), 2.5)),
    (13501850, "Living Failures",
     ("m35_00", (-378.54, 1592.9, -824.55), (-405.5, 1592.8, -824.55), 2.5)),
    (13501800, "Lady Maria",
     ("m35_00", (-452.0, 1595.51, -824.41), (-477.2, 1595.5, -824.41), 2.5)),
    (13601800, "Orphan of Kos",
     ("m36_00", (-700.2, 1580.5, -906.2), (-700.2, 1578.54, -929.2), 2.5)),
]
# Bossowie, którzy istnieją dopiero w danym momencie fabuły: flagi, które trzeba ustawić przed
# wczytaniem Snu (ze skryptów m21_00 gry). 9462 = Sen po Mergo's Wet Nurse; 12411000 usuwa
# Gehrmana, gdy ustawiona; 12101802 / 12101852 = walka już rozpoczęta (wchodzi się przez mgłę).
STORY_FIGHTS = {
    12101800: {9462: True, 12411000: False, 12101800: False, 12101802: True,
               12101850: False, 12101852: False},
    # 9900 (trzy pępowiny) musi być ustawiona: bez niej gra uznaje martwego Gehrmana za
    # koniec („Honoring Wishes”) i od razu puszcza napisy i NG+.
    12101850: {9462: True, 12411000: False, 9900: True, 12101800: True, 12101802: True,
               12101850: False, 12101852: True},
}


def map_id(name):
    """"m24_01" -> spakowany numer mapy gry."""
    return int(name[1:3]) << 24 | int(name[4:6]) << 16


def boss_entry(entry):
    """(mapa, pozycja przed bramą, kąt patrzenia w stronę areny)."""
    name, gate, inside, back = entry
    dx, dz = inside[0] - gate[0], inside[2] - gate[2]
    length = math.hypot(dx, dz)
    dx, dz = dx / length, dz / length
    position = [gate[0] - dx * back, gate[1] + 0.8, gate[2] - dz * back]
    return map_id(name), position, math.atan2(-dx, -dz)  # w grze przód to -(sin, cos)


def settings():
    """(folder gry, kod języka tekstów) z ustawień bbport."""
    game = Path.home() / "bloodborne/CUSA03173"
    for config in LAUNCHER_CONFIG.glob("*.json"):
        try:
            value = json.loads(config.read_text()).get("game_dir")
        except (OSError, ValueError, AttributeError):
            continue
        if value and os.path.isdir(value):
            game = Path(value)
            break
    language = "engus"
    for ini in (BBPORT / "bbport.ini", Path.home() / ".local/share/bbport/bbport.ini"):
        try:
            for line in ini.read_text().splitlines():
                if line.startswith("game_text_language="):
                    language = line.split("=", 1)[1].strip()
        except OSError:
            continue
        break
    if not (game / "dvdroot_ps4/msg" / language).is_dir():
        language = "engus"
    return game, language


def _dcx(path):
    data = Path(path).read_bytes()
    if data[:4] != b"DCX\0":
        return data
    at = data.index(b"DCA\0")
    header = struct.unpack(">I", data[at + 4:at + 8])[0]
    return zlib.decompress(data[at + header:])


def _utf16(data, offset):
    end = offset
    while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
        end += 2
    return data[offset:end].decode("utf-16le", "replace")


def _bnd4(data):
    if data[:4] != b"BND4":
        raise ValueError("to nie BND4")
    count = struct.unpack_from("<i", data, 12)[0]
    header = struct.unpack_from("<q", data, 32)[0]
    files = {}
    for k in range(count):
        at = 64 + k * header
        size = struct.unpack_from("<q", data, at + 8)[0]
        if header == 36:
            start, _, name = struct.unpack_from("<III", data, at + 24)
        else:
            start, _, name = struct.unpack_from("<III", data, at + header - 12)
        files[_utf16(data, name).split("\\")[-1]] = data[start:start + size]
    return files


def _fmg(data):
    groups = struct.unpack_from("<i", data, 12)[0]
    offsets = struct.unpack_from("<q", data, 24)[0]
    texts = {}
    for g in range(groups):
        index, first, last, _ = struct.unpack_from("<4i", data, 40 + g * 16)
        for k, ident in enumerate(range(first, last + 1)):
            at = struct.unpack_from("<q", data, offsets + 8 * (index + k))[0]
            if at:
                texts[ident] = _utf16(data, at)
    return texts


def _texts(game, language, bundle, table):
    files = _bnd4(_dcx(game / f"dvdroot_ps4/msg/{language}/{bundle}.msgbnd.dcx"))
    for name, blob in files.items():
        if name.split(".")[0] == table:
            return _fmg(blob)
    return {}


def lamps():
    """[(punkt, nazwa)] wszystkich lamp, z nazwami w języku gry."""
    game, language = settings()
    names = _texts(game, language, "menu", "イベントテキスト")
    found = {2102961: names.get(70002100, "Hunter's Dream")}
    for path in glob.glob(str(game / "dvdroot_ps4/event/m*.emevd.dcx")):
        data = _dcx(path)
        needle = struct.pack("<i", 7000)  # wspólne zdarzenie 7000 = lampa
        at = data.find(needle)
        while at >= 4:
            if at + 16 <= len(data):
                _, _, flag, entity, _ = struct.unpack_from("<5i", data, at - 4)
                if 2000000 < flag < 4000000 and entity - flag == 1000:
                    ident = 70000000 + entity // 100000 * 100 + entity // 10000 % 10 * 10 + entity % 10
                    found[entity + 1000] = names.get(ident, f"Lampa {entity + 1000}")
            at = data.find(needle, at + 4)
    return sorted(found.items())


def goods():
    """[(id, nazwa)] przedmiotów zwykłych."""
    game, language = settings()
    names = _texts(game, language, "item", "アイテム名")
    return sorted(((i, n.strip()) for i, n in names.items()
                   if n and n.strip() and not n.strip().startswith(("(", "<", "[", "%", "*", "?"))),
                  key=lambda item: item[1].casefold())
