"""Lamp and item lists read from the user's game files (DCX / BND4 / FMG / PARAM / EMEVD)."""
import glob
import math
import re
import struct
import zlib
from pathlib import Path

import bbport
from i18n import tr

# (defeat flag, name, entrance)
# Entrance, from the map files (MSB): (map, fog gate point, point on its inner side, distance).
# The trainer puts the player `distance` metres in front of the gate, facing the arena.
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
# Bosses that only exist at a certain point of the story: the flags to set before loading the
# Dream (from the game's m21_00 scripts). 9462 = the Dream after Mergo's Wet Nurse; 12411000
# removes Gehrman when set; 12101802 / 12101852 = fight already started (entered through fog).
STORY_FIGHTS = {
    12101800: {9462: True, 12411000: False, 12101800: False, 12101802: True,
               12101850: False, 12101852: False},
    # 9900 (three umbilical cords) must be set: without it the game takes a dead Gehrman for
    # an ending ("Honoring Wishes") and rolls the credits and NG+ right away.
    12101850: {9462: True, 12411000: False, 9900: True, 12101800: True, 12101802: True,
               12101850: False, 12101852: True},
}


def map_id(name):
    """"m24_01" -> the game's packed map number."""
    return int(name[1:3]) << 24 | int(name[4:6]) << 16


def boss_entry(entry):
    """(map, position in front of the gate, yaw facing the arena)."""
    name, gate, inside, back = entry
    dx, dz = inside[0] - gate[0], inside[2] - gate[2]
    length = math.hypot(dx, dz)
    dx, dz = dx / length, dz / length
    position = [gate[0] - dx * back, gate[1] + 0.8, gate[2] - dz * back]
    return map_id(name), position, math.atan2(-dx, -dz)  # forward in game is -(sin, cos)


def has_map(game, name):
    """Whether the game files contain a map (The Old Hunters maps need the DLC)."""
    return (game / f"dvdroot_ps4/map/mapstudio/{name}_00_00.msb.dcx").is_file()


def bosses():
    """The bosses whose maps this copy of the game has (all of them if it cannot be told)."""
    try:
        game = settings()[0]
    except FileNotFoundError:
        return BOSSES
    return [boss for boss in BOSSES if has_map(game, boss[2][0])] or BOSSES


def settings():
    """(game folder, text language code) according to the bbport settings."""
    install = bbport.find()
    game = bbport.game_dir(install)
    if not game or not (game / "dvdroot_ps4").is_dir():
        raise FileNotFoundError(tr("Game files not found. Choose the game folder in the bbport "
                                   "launcher, then restart the trainer."))
    messages = game / "dvdroot_ps4/msg"
    wanted = [bbport.ini_value(install, "game_text_language"), "engus", "enggb"]
    wanted += sorted(p.name for p in messages.glob("*"))
    for language in wanted:
        if language and (messages / language / "item.msgbnd.dcx").is_file():
            return game, language
    raise FileNotFoundError(tr("No game texts found in {}").format(messages))


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
        raise ValueError("not a BND4 file")
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
    """[(point, name)] of every lamp, named in the game's language."""
    game, language = settings()
    names = _texts(game, language, "menu", "イベントテキスト")
    found = {2102961: names.get(70002100, "Hunter's Dream")}
    for path in glob.glob(str(game / "dvdroot_ps4/event/m*.emevd.dcx")):
        data = _dcx(path)
        needle = struct.pack("<i", 7000)  # common event 7000 = a lamp
        at = data.find(needle)
        while at >= 4:
            if at + 16 <= len(data):
                _, _, flag, entity, _ = struct.unpack_from("<5i", data, at - 4)
                if 2000000 < flag < 4000000 and entity - flag == 1000:
                    ident = 70000000 + entity // 100000 * 100 + entity // 10000 % 10 * 10 + entity % 10
                    found[entity + 1000] = names.get(ident,
                                                     tr("Lamp {}").format(entity + 1000))
            at = data.find(needle, at + 4)
    return sorted(found.items())


# ---------------------------------------------------------------- game parameters
_SIZES = {"s8": 1, "u8": 1, "dummy8": 1, "s16": 2, "u16": 2, "s32": 4, "u32": 4, "f32": 4,
          "fixstr": 1, "fixstrW": 2}
_FORMATS = {"s8": "b", "u8": "B", "s16": "h", "u16": "H", "s32": "i", "u32": "I", "f32": "f"}


def _layout(paramdef):
    """{field: (offset, type, first bit, bit count)} from a parameter definition."""
    count, size = struct.unpack_from("<HH", paramdef, 8)
    offset = used = unit = 0
    fields = {}
    for i in range(count):
        record = paramdef[0x38 + i * size:0x38 + (i + 1) * size]
        kind = record[64:72].split(b"\0")[0].decode()
        name = record[144:176].split(b"\0")[0].decode().strip()
        width, length, bits = _SIZES[kind], 1, 0
        if "[" in name:
            name, rest = name[:-1].split("[")
            length = int(rest)
        if ":" in name:
            name, rest = name.split(":")
            bits = int(rest)
        if bits:
            if not used or used + bits > unit * 8 or unit != width:
                offset += unit if used else 0
                used, unit = 0, width
            fields[name] = (offset, kind, used, bits)
            used += bits
            if used == unit * 8:
                offset, used = offset + unit, 0
        else:
            if used:
                offset, used = offset + unit, 0
            fields[name] = (offset, kind, 0, 0)
            offset += width * length
    return fields


def _params(game, name):
    """{id: {field: value}} of a parameter table, e.g. "EquipParamGoods"."""
    folder = game / "dvdroot_ps4"
    table = _bnd4(_dcx(folder / "param/gameparam/gameparam.parambnd.dcx"))[f"{name}.param"]
    layout = _layout(_bnd4(_dcx(folder / "paramdef/paramdef.paramdefbnd.dcx"))[f"{name}.paramdef"])

    def row(start):
        values = {}
        for field, (offset, kind, bit, bits) in layout.items():
            if kind not in _FORMATS:
                continue
            value = struct.unpack_from("<" + _FORMATS[kind], table, start + offset)[0]
            values[field] = value >> bit & (1 << bits) - 1 if bits else value
        return values

    result = {}
    for i in range(struct.unpack_from("<H", table, 0x0A)[0]):
        ident, _, start, _ = struct.unpack_from("<IIqq", table, 0x40 + i * 24)
        result[ident] = row(start)
    return result


# ---------------------------------------------------------------- items
def _item_names(game, language, table):
    names = _texts(game, language, "item", table)
    return {i: n.strip() for i, n in names.items()
            if n and n.strip() and not n.strip().startswith(("(", "<", "[", "%", "*", "?"))
            and n.strip() != "NOT NEEDED" and not re.fullmatch(r"[a-z]{2}\d+", n.strip())}


# Variant and group names are translated on screen.
WEAPON_VARIANTS = (("Normal", 0), ("Uncanny", 10000), ("Lost", 20000))
WEAPON_GROUPS = ("Weapons (right hand)", "Firearms, shields and torches (left hand)")
ARMOR_GROUPS = (("headEquip", "Attire: head"), ("bodyEquip", "Attire: chest"),
                ("armEquip", "Attire: arms"), ("legEquip", "Attire: legs"))
GOODS_GROUPS = ("Healing and bullets", "Throwables and buffs", "Hunter tools",
                "Upgrade and ritual materials", "Echoes and insight", "Chalices",
                "Keys and story items (careful)", "Bells and miscellaneous", "Gestures",
                "Other (may not work)")


def _goods_group(row):
    kind, order = row["goodsType"], row["sortId"]
    if kind == 1:
        return GOODS_GROUPS[6]
    if kind == 2:
        return GOODS_GROUPS[3]
    if kind == 6:
        return GOODS_GROUPS[5]
    # the game orders the rest by sortId: consecutive ranges are consecutive kinds
    if order >= 500000:
        return GOODS_GROUPS[8]
    if order >= 240000:
        return GOODS_GROUPS[7]
    if order >= 220000 or 90000 <= order < 100000:
        return GOODS_GROUPS[2]
    if order >= 120000:
        return GOODS_GROUPS[9]
    if order >= 100000:
        return GOODS_GROUPS[4]
    if order >= 30000:
        return GOODS_GROUPS[1]
    return GOODS_GROUPS[0]


def catalog():
    """[(group name, [item])] in the order the game lists them.

    An item: {"kind": "weapon" | "armor" | "goods", "id", "name"}; weapons also have "levels":
    {variant offset: {upgrade level: id}}.
    """
    game, language = settings()
    groups = {}

    def put(group, order, item):
        groups.setdefault(group, []).append((order, item["name"], item))

    names = _item_names(game, language, "武器名")
    rows = _params(game, "EquipParamWeapon")
    for ident, name in names.items():
        if ident % 100000 or ident not in rows or ident == 1000000:  # 1000000: bare fists
            continue
        levels = {}
        for _, offset in WEAPON_VARIANTS:
            found = {level: ident + offset + level * 100 for level in range(11)
                     if ident + offset + level * 100 in rows
                     and ident + offset + level * 100 in names}
            if found:
                levels[offset] = found
        group = WEAPON_GROUPS[0 if rows[ident]["rightHandEquipable"] else 1]
        put(group, rows[ident]["sortId"],
            {"kind": "weapon", "id": ident, "name": name, "levels": levels})

    names = _item_names(game, language, "防具名")
    rows = _params(game, "EquipParamProtector")
    for ident, name in names.items():
        if ident not in rows:
            continue
        for field, group in ARMOR_GROUPS:
            if rows[ident][field]:
                put(group, rows[ident]["sortId"], {"kind": "armor", "id": ident, "name": name})
                break

    names = _item_names(game, language, "アイテム名")
    rows = _params(game, "EquipParamGoods")
    for ident, name in names.items():
        if ident in rows:
            put(_goods_group(rows[ident]), rows[ident]["sortId"],
                {"kind": "goods", "id": ident, "name": name})

    order = (*WEAPON_GROUPS, *(group for _, group in ARMOR_GROUPS), *GOODS_GROUPS)
    return [(group, [item for _, _, item in sorted(groups[group], key=lambda e: e[:2])])
            for group in order if group in groups]
