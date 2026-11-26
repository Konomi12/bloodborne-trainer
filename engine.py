"""Trainer engine: the game's memory (bbport, Bloodborne 1.09) through /proc/<pid>/mem.

All addresses are offsets into the game image loaded at 0x800000000. Game functions are called
by a short stub in the main loop (stub.s): once per frame it reads a mailbox in game memory,
scales the time step and runs one requested call on the game's own thread.
"""
import ctypes
import math
import os
import signal
import struct
import time

from i18n import tr

BASE = 0x800000000

# Global pointers
WORLD_CHR_MAN = 0x553E878
GAME_DATA_MAN = 0x553B130
GAME_STATE = 0x5556678          # +0x08: loading in progress
EVENT_STATE = 0x553B0D8
EVENT_FLAG_MAN = 0x553B100
EVENT_MAN = 0x553B108
MAP_LIST = 0x553B148

# Game functions
FN_SET_HP = 0x18BCD40           # (chr, hp)
FN_SELECT_SPAWN = 0x1332BC0     # (_, -1): map of the "last lamp" [GameState+0x1528]
FN_RELOAD = 0x13CDE30           # reload into the selected place
FN_SET_FLAG = 0x132E5A0         # (_, flag, value)
FN_GET_FLAG = 0x1399BF0         # (_, flag) -> bool
FN_SAVE_REQUEST = 0x1336DA0     # save the game before leaving
FN_RETURN_TITLE = 0x138BAF0     # OnReturnTitle: back to the main menu
FN_ITEM_FITS = 0x14D9A80        # (inventory, &code, count) -> how many fit
FN_ITEM_ADD = 0x14DA0A0         # (inventory, &key, count) -> slot
FN_GIVE_ANY = 0x14CDA70         # (equipment, _, &holder, count, _, 1, 0) -> slot (<0: refused)
FN_NEW_WEAPON = 0x1A87260       # (&holder, item manager, id): a new weapon instance
FN_NEW_ARMOR = 0x1A87390        # the same for armor
FN_RELEASE_ITEM = 0x1A8BC00     # (&holder): drops our reference
ITEM_MAN = 0x553E990
ITEM_POPUP_MAN = 0x553B1C0
DAMAGE_MAN = 0x553D740          # +0x30: the game draws attack shapes ("デバッグ球表示")
FN_ITEM_POPUP = 0x16D8850       # (queue, &holder, category, id, count, 0): "item acquired" box
CATEGORY_WEAPON, CATEGORY_ARMOR, CATEGORY_GOODS = 0, 1, 4

# The game's debug flags (names from its own debug menu)
FLAGS = {
    "no_dead": 0x553E888,
    "one_hit": 0x553E889,
    "all_no_stamina": 0x553E88A,
    "no_bullets": 0x553E88C,
    "hidden": 0x553E88E,
    "silent": 0x553E88F,
    "all_no_dead": 0x553E890,
    "all_no_damage": 0x553E891,
    "all_no_hit": 0x553E892,
    "all_no_attack": 0x553E893,
    "all_no_move": 0x553E894,
    "all_no_ai": 0x553E895,
}

STATS = {  # offsets in the character data [[GameDataMan]+8]; the names are translated on screen
    "Vitality": 0x40, "Endurance": 0x48, "Strength": 0x58, "Skill": 0x60,
    "Bloodtinge": 0x68, "Arcane": 0x70, "Level": 0x90,
    "Insight": 0x84, "Blood echoes": 0x94,
}
NG_CYCLE = 0x68                 # in GameDataMan

HOOK_SITE = 0x2018E3D
HOOK_ORIGINAL = bytes.fromhex("488d05cc765203")  # lea rax,[rip+0x35276cc]
CAVE = 0x50D9800                # padding after the game's code
MAILBOX = 0x56D3800             # padding after the game's .bss
MAGIC = b"BBTRAIN1"

# Assembled stub.s (the mailbox and return addresses are hard-coded)
STUB = bytes.fromhex(
    "49bb00386d050800000049ff4358c5fa1045c8c4c17a594308c5fa1145c8418b430c413b4310"
    "744e534154415541564189c44d89dd4889e34883e4f04883ec10498b456048890424498b7d20"
    "498b7528498b5530498b4d384d8b45404d8b4d4841ff551849894550458965104889dc415e41"
    "5d415c5b48b8100554050800000049bb448e01020800000041ffe3")


class TrainerError(Exception):
    pass


def become_subreaper():
    """Processes orphaned by the launcher stay ours (Yama lets us read our descendants)."""
    ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)


def ptrace_scope():
    """The Yama ptrace policy: 0 or 1 work with the trainer, 2 and 3 block it."""
    try:
        with open("/proc/sys/kernel/yama/ptrace_scope") as f:
            return int(f.read())
    except (OSError, ValueError):
        return 0


def elf_symbol(path, name):
    """Address of an exported symbol inside a 64-bit ELF shared library, or 0."""
    with open(path, "rb") as f:
        header = f.read(64)
        if header[:6] != b"\x7fELF\x02\x01":
            return 0
        offset = struct.unpack_from("<Q", header, 0x28)[0]
        size, count = struct.unpack_from("<HH", header, 0x3A)
        f.seek(offset)
        table = f.read(size * count)
        sections = [struct.unpack_from("<IIQQQQIIQQ", table, i * size) for i in range(count)]
        for section in sections:
            if section[1] != 11:    # SHT_DYNSYM
                continue
            strings = sections[section[6]]
            f.seek(strings[4])
            names = f.read(strings[5])
            f.seek(section[4])
            symbols = f.read(section[5])
            wanted = name.encode() + b"\0"
            for start, _, _, defined, value, _ in struct.iter_unpack("<IBBHQQ", symbols):
                if defined and names[start:start + len(wanted)] == wanted:
                    return value
    return 0


def find_game_pids():
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/comm") as f:
                if f.read().strip() != "bb-probe":
                    continue
            with open(f"/proc/{entry}/stat") as f:
                if f.read().rsplit(")", 1)[1].split()[0] == "Z":
                    continue
        except OSError:
            continue
        found.append(int(entry))
    return found


class Game:
    def __init__(self):
        self.pid = None
        self.fd = None
        self.hooked = False
        self.keyboard_ptr = 0
        self.keyboard_missing = False
        self.forced = set()     # flags the trainer turned on (it only turns these off again)
        self.hitboxes = False   # whether the trainer turned hitbox drawing on

    # ---------------------------------------------------------------- connection
    @property
    def attached(self):
        return self.fd is not None

    def attach(self):
        """Connects to the running game. Returns a status line for the user."""
        if self.attached:
            if self.pid in find_game_pids():
                return self._ensure_hook()
            self.detach(restore=False)
        pids = find_game_pids()
        if not pids:
            return tr("The game is not running.")
        for pid in pids:
            try:
                fd = os.open(f"/proc/{pid}/mem", os.O_RDWR)
                if len(os.pread(fd, 7, BASE + HOOK_SITE)) != 7:
                    os.close(fd)
                    continue
            except PermissionError:
                if ptrace_scope() >= 2:
                    return tr("Your system blocks access to game memory (ptrace_scope). "
                              "See the README.")
                return tr("No access to the game. Close it and start it from the trainer.")
            except OSError:
                continue
            self.pid, self.fd = pid, fd
            return self._ensure_hook()
        return tr("The game is starting…")

    def detach(self, restore=True):
        if self.fd is not None:
            if restore:
                try:
                    self.restore()
                except (OSError, TrainerError):
                    pass
            try:
                os.close(self.fd)
            except OSError:
                pass
        self.fd = self.pid = None
        self.hooked = False
        self.keyboard_ptr = 0
        self.keyboard_missing = False
        self.forced.clear()
        self.hitboxes = False

    def _ensure_hook(self):
        if self.hooked:
            return tr("Connected.")
        if not self.ptr(BASE + GAME_DATA_MAN):
            return tr("Waiting for the game to start…")
        site = self.read(BASE + HOOK_SITE, 7)
        if site != HOOK_ORIGINAL:
            return tr("Unexpected game version (1.09 is required): leaving it alone.")
        cave = self.read(BASE + CAVE, len(STUB))
        box = self.read(BASE + MAILBOX, 0x100)
        if cave is None or box is None or cave.strip(b"\0") not in (b"", STUB.strip(b"\0")) \
                or (box.strip(b"\0") and not box.startswith(MAGIC)):
            return tr("The space for the trainer's stub is taken: leaving the game alone.")
        fresh = bytearray(0x100)
        fresh[0:8] = MAGIC
        struct.pack_into("<f", fresh, 8, 1.0)
        self.write(BASE + MAILBOX, bytes(fresh))
        self.write(BASE + CAVE, STUB)
        rel = (BASE + CAVE) - (BASE + HOOK_SITE + 5)
        self._patch_stopped(BASE + HOOK_SITE, b"\xe9" + struct.pack("<i", rel) + b"\x90\x90")
        self.hooked = True
        return tr("Connected.")

    def _patch_stopped(self, address, data):
        os.kill(self.pid, signal.SIGSTOP)
        try:
            deadline = time.monotonic() + 1
            while time.monotonic() < deadline:
                states = []
                for task in os.listdir(f"/proc/{self.pid}/task"):
                    try:
                        with open(f"/proc/{self.pid}/task/{task}/stat") as f:
                            states.append(f.read().rsplit(")", 1)[1].split()[0])
                    except OSError:
                        pass
                if all(s in "TtZX" for s in states):
                    break
                time.sleep(0.002)
            self.write(address, data)
        finally:
            os.kill(self.pid, signal.SIGCONT)

    def restore(self):
        """Turns off everything the trainer turned on and gives the game its own code back."""
        for name in list(self.forced):
            self.set_flag(name, False)
        if self.hitboxes:
            self.set_hitboxes(False)
        if self.hooked:
            self._patch_stopped(BASE + HOOK_SITE, HOOK_ORIGINAL)
            self.hooked = False

    # ---------------------------------------------------------------- memory
    def read(self, address, size):
        if self.fd is None or not 0x10000 <= address < 0x7FFFFFFFFFFF:
            return None
        try:
            data = os.pread(self.fd, size, address)
        except OSError:
            return None
        return data if len(data) == size else None

    def write(self, address, data):
        if self.fd is None or not 0x10000 <= address < 0x7FFFFFFFFFFF:
            raise TrainerError(tr("bad address"))
        if os.pwrite(self.fd, data, address) != len(data):
            raise TrainerError(tr("writing to the game failed"))

    def unpack(self, address, fmt):
        data = self.read(address, struct.calcsize(fmt))
        return None if data is None else struct.unpack(fmt, data)[0]

    def ptr(self, address):
        value = self.unpack(address, "<Q")
        return value if value and 0x10000 <= value < 0x7FFFFFFFFFFF else 0

    def chain(self, address, *offsets):
        """ptr(...ptr(ptr(address) + o0) + o1 ...)"""
        value = self.ptr(address)
        for offset in offsets:
            if not value:
                return 0
            value = self.ptr(value + offset)
        return value

    def i32(self, address):
        return self.unpack(address, "<i")

    def set_i32(self, address, value):
        self.write(address, struct.pack("<i", int(value)))

    # ---------------------------------------------------------------- game state
    def player(self):
        return self.chain(BASE + WORLD_CHR_MAN, 0x60)

    def loading(self):
        state = self.ptr(BASE + GAME_STATE)
        return not state or self.read(state + 8, 1) != b"\0"

    def in_world(self):
        return bool(self.player()) and not self.loading() and self.chr_data(self.player()) != 0

    def need_world(self):
        if not self.attached or not self.hooked:
            raise TrainerError(tr("the trainer is not connected to the game"))
        if not self.in_world():
            raise TrainerError(tr("load a character first"))
        return self.player()

    def chr_data(self, chr_):
        return self.chain(chr_ + 0x3B0, 0x20) if chr_ else 0

    def vitals(self, chr_):
        """(hp, max_hp, stamina, max_stamina) or None."""
        data = self.chr_data(chr_)
        if not data:
            return None
        values = (self.i32(data + 0xF8), self.i32(data + 0xFC),
                  self.i32(data + 0x134), self.i32(data + 0x138))
        return None if None in values else values

    def transform(self, chr_):
        """The position block: rotation at +0x1D0, position at +0x1E0."""
        return self.chain(chr_ + 0x58, 0x08, 0x3B0, 0x68) if chr_ else 0

    def position(self, chr_):
        block = self.transform(chr_)
        data = self.read(block + 0x1D0, 32) if block else None
        if data is None:
            return None
        values = struct.unpack("<8f", data)
        if not all(math.isfinite(v) for v in values[4:7]):
            return None
        return list(values[4:7]), list(values[0:4])

    def map_id(self):
        maps = self.ptr(BASE + MAP_LIST)
        if not maps:
            return 0
        index = self.i32(maps + 0x20)
        array = self.ptr(maps + 0x10)
        if index is None or not array:
            return 0
        count = self.i32(array + 0x18)
        entries = self.ptr(array + 0x20)
        if count is None or not entries or not 0 <= index < count:
            return 0
        return self.unpack(entries + index * 0xA0 + 8, "<I") or 0

    def game_data(self):
        return self.chain(BASE + GAME_DATA_MAN, 0x08)

    # ---------------------------------------------------------------- calls
    def heartbeat(self):
        return self.unpack(BASE + MAILBOX + 0x58, "<Q")

    def call(self, function, *args, timeout=2.0):
        """Calls a game function on the game's main thread and returns rax."""
        if not self.hooked:
            raise TrainerError(tr("the trainer is not connected to the game"))
        box = BASE + MAILBOX
        seq, ack = struct.unpack("<II", self.read(box + 0x0C, 8))
        if seq != ack:
            raise TrainerError(tr("the game is still running the previous command"))
        padded = [a & (2**64 - 1) for a in args] + [0] * (7 - len(args))
        self.write(box + 0x18, struct.pack("<7Q", function, *padded[:6]))
        self.write(box + 0x60, struct.pack("<Q", padded[6]))  # the stack argument
        new = (seq + 1) & 0xFFFFFFFF
        self.write(box + 0x0C, struct.pack("<I", new))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.unpack(box + 0x10, "<I") == new:
                return self.unpack(box + 0x50, "<Q")
            time.sleep(0.003)
        # Withdraw a command that did not run, so it cannot fire later by surprise.
        self.write(box + 0x0C, struct.pack("<I", ack))
        raise TrainerError(tr("the game is not responding (loading or paused?)"))

    def game_call(self, offset, *args):
        if self.read(BASE + offset, 4) != b"\x55\x48\x89\xe5":
            raise TrainerError(tr("game function {} does not look like 1.09").format(hex(offset)))
        return self.call(BASE + offset, *args)

    # ---------------------------------------------------------------- features
    def set_flag(self, name, on):
        self.write(BASE + FLAGS[name], b"\x01" if on else b"\0")
        self.forced.add(name) if on else self.forced.discard(name)

    def set_hitboxes(self, on):
        """Drawing of attack shapes. The damage manager only exists in game, so this is called
        repeatedly; it does nothing when the state already matches."""
        manager = self.ptr(BASE + DAMAGE_MAN)
        if not manager:
            return
        wanted = b"\x01" if on else b"\0"
        if self.read(manager + 0x30, 1) not in (wanted, None):
            self.write(manager + 0x30, wanted)
        self.hitboxes = on

    def set_speed(self, speed):
        if self.hooked:
            self.write(BASE + MAILBOX + 8, struct.pack("<f", min(max(speed, 0.05), 4.0)))

    def set_hp(self, chr_, hp):
        self.need_world()
        self.game_call(FN_SET_HP, chr_, max(0, int(hp)))

    def full_heal(self):
        player = self.need_world()
        hp, max_hp, _, max_stamina = self.vitals(player)
        self.game_call(FN_SET_HP, player, max_hp)
        self.set_i32(self.chr_data(player) + 0x134, max_stamina)

    def kill_player(self):
        player = self.need_world()
        self.set_flag("no_dead", False)
        self.game_call(FN_SET_HP, player, 0)

    def teleport(self, position, rotation=None):
        player = self.need_world()
        warp = self.ptr(self.ptr(player) + 0x5F8)
        if not BASE < warp < BASE + 0x50DA000:
            raise TrainerError(tr("unexpected teleport function"))
        if rotation is None:
            rotation = self.position(player)[1]
        scratch = BASE + MAILBOX + 0x80
        self.write(scratch, struct.pack("<8f", *position[:3], 1.0,
                                        rotation[0], rotation[1], rotation[2], 0.0))
        self.call(warp, player, scratch, scratch + 0x10, 1)
        flags = self.read(player + 0x1E4, 1)
        if flags:
            self.write(player + 0x1E4, bytes([flags[0] | 2]))

    def warp_lamp(self, point):
        """Like lamp travel in game: sets the last lamp and reloads the world there."""
        self.need_world()
        state = self.ptr(BASE + GAME_STATE)
        previous = self.read(state + 0x1528, 4)
        self.write(state + 0x1520, b"\0")
        self.set_i32(state + 0x1528, point)
        if not self.game_call(FN_SELECT_SPAWN, 0, 0xFFFFFFFF) & 0xFF:
            self.write(state + 0x1528, previous)
            raise TrainerError(tr("the game refused this warp"))
        self.game_call(FN_RELOAD)

    def warp_position(self, map_id, position, yaw):
        """Reloads the world straight at a given spot (the game's forced spawn point).
        The last lamp stays. Call clear_forced_spawn() once loading is done."""
        self.need_world()
        state = self.ptr(BASE + GAME_STATE)
        spot = struct.pack("<4f", *position[:3], 1.0)
        facing = struct.pack("<4f", 0.0, yaw, 0.0, 0.0)
        for at, data in ((0x14C4, struct.pack("<I", map_id)), (0x14D0, spot), (0x14E0, facing),
                         (0x14F0, struct.pack("<I", map_id)), (0x1500, spot), (0x1510, facing),
                         (0x1520, b"\x01")):
            self.write(state + at, data)
        if not self.game_call(FN_SELECT_SPAWN, 0, 0xFFFFFFFF) & 0xFF \
                or self.unpack(state + 0x0C, "<I") != map_id:
            self.clear_forced_spawn()
            raise TrainerError(tr("the game refused this warp"))
        self.game_call(FN_RELOAD)

    def clear_forced_spawn(self):
        """A marker left behind would send the player here after a death too."""
        state = self.ptr(BASE + GAME_STATE)
        if state:
            self.write(state + 0x1520, b"\0")

    def return_to_title(self):
        self.need_world()
        if not self.ptr(BASE + EVENT_MAN):
            raise TrainerError(tr("the game's event manager is missing"))
        self.game_call(FN_SAVE_REQUEST)
        time.sleep(0.7)
        self.game_call(FN_RETURN_TITLE)

    def _need_flags(self):
        self.need_world()
        if not self.ptr(BASE + EVENT_FLAG_MAN) or not self.ptr(BASE + EVENT_STATE):
            raise TrainerError(tr("event flags are not ready yet"))

    def get_event_flag(self, flag):
        self._need_flags()
        return bool(self.game_call(FN_GET_FLAG, 0, flag) & 0xFF)

    def set_event_flag(self, flag, value):
        self._need_flags()
        self.game_call(FN_SET_FLAG, 0, flag, 1 if value else 0)

    def _show_item(self, holder, category, item_id, count):
        """Queues the item for the "acquired" box, the way the game does on pickup."""
        queue = self.ptr(BASE + ITEM_POPUP_MAN)
        # with neither a free nor a used node the game function would write to address zero
        if queue and (self.ptr(queue + 0x10) or self.ptr(queue + 0x08)):
            self.game_call(FN_ITEM_POPUP, queue, holder, category << 28, item_id, count, 0)

    def give_goods(self, goods_id, count, popup=True):
        """Adds an item (the "goods" category) to the inventory. Returns how many were added."""
        self.need_world()
        data = self.game_data()
        if not data:
            raise TrainerError(tr("character data is missing"))
        inventory = data + 0x328
        code = BASE + MAILBOX + 0xB0
        key = BASE + MAILBOX + 0xB4
        self.write(code, struct.pack("<II", 0x40000000 | goods_id,
                                     0x80000000 | (3 << 28) | goods_id))
        fits = ctypes.c_int32(self.game_call(FN_ITEM_FITS, inventory, code, count) & 0xFFFFFFFF).value
        if fits <= 0:
            raise TrainerError(tr("no room for more (inventory limit)"))
        count = min(count, fits)
        slot = ctypes.c_int32(self.game_call(FN_ITEM_ADD, inventory, key, count) & 0xFFFFFFFF).value
        if slot < 0:
            raise TrainerError(tr("the game refused the item"))
        if popup:
            self._show_item(key, CATEGORY_GOODS, goods_id, count)
        return count

    def give_equipment(self, category, item_id, popup=True):
        """Adds one weapon or armor piece the way the game does: first creates the instance
        (a holder), then puts it into the inventory."""
        self.need_world()
        data = self.game_data()
        manager = self.ptr(BASE + ITEM_MAN)
        if not data or not manager:
            raise TrainerError(tr("character data is missing"))
        create = {CATEGORY_WEAPON: FN_NEW_WEAPON, CATEGORY_ARMOR: FN_NEW_ARMOR}[category]
        holder = BASE + MAILBOX + 0xB0
        self.write(holder, bytes(0x20))
        self.game_call(create, holder, manager, item_id)
        if not self.unpack(holder, "<I"):
            raise TrainerError(tr("the game did not create the item"))
        try:
            result = self.game_call(FN_GIVE_ANY, data + 0x1D0, 0, holder, 1, 0, 1, 0)
            if ctypes.c_int32(result & 0xFFFFFFFF).value < 0:
                raise TrainerError(tr("the game did not accept the item (inventory full?)"))
            if popup:
                self._show_item(holder, category, item_id, 1)
        finally:
            self.game_call(FN_RELEASE_ITEM, holder)

    def keep_items(self, saved):
        """Keeps carried item counts from going down. `saved`: a dict kept between calls."""
        data = self.game_data()
        if not data:
            return
        inventory = data + 0x328
        # the first [+0x24] slots hold key items (left alone), the ordinary ones follow
        total = self.unpack(inventory + 0x10, "<I")
        split = self.unpack(inventory + 0x24, "<I")
        base = self.ptr(inventory + 0x48)
        if not base or total is None or split is None or not 0 < total - split <= 4096:
            return
        table = self.read(base, (total - split) * 16)
        if table is None:
            return
        for slot, (key, _, count, _) in enumerate(struct.iter_unpack("<IIiI", table)):
            if (key >> 28) & 7 != 3 or key == 0xFFFFFFFF:
                saved.pop(slot, None)
                continue
            old = saved.get(slot)
            if old and old[0] == key and 0 < count < old[1]:
                self.set_i32(base + slot * 16 + 8, old[1])
            else:
                saved[slot] = (key, count)

    def characters(self):
        """Every character in the world except the player: a list of addresses."""
        world = self.ptr(BASE + WORLD_CHR_MAN)
        if not world:
            return []
        player = self.ptr(world + 0x60)
        blocks = self.ptr(world + 0x08)
        count = self.i32(blocks + 0x18) if blocks else None
        if count is None:
            return []
        found = []
        for b in range(min(max(count + 2, 0), 64)):
            block = self.ptr(world + 0x850 + b * 8)
            if not block:
                continue
            n = self.i32(block)
            entries = self.ptr(block + 8)
            if n is None or not 0 < n <= 0x3FFF or not entries:
                continue
            table = self.read(entries, n * 0x38)
            if table is None:
                continue
            for i in range(n):
                chr_ = struct.unpack_from("<Q", table, i * 0x38)[0]
                if chr_ >= 0x10000 and chr_ != player:
                    found.append(chr_)
        return found

    def nearby(self, limit=12, radius=60.0):
        """[(distance, chr, hp, max_hp, position)] of living characters around the player."""
        me = self.position(self.player())
        if me is None:
            return []
        result = []
        for chr_ in self.characters():
            vitals = self.vitals(chr_)
            if not vitals or not 0 < vitals[0] <= 10_000_000 or vitals[1] <= 0:
                continue
            where = self.position(chr_)
            if where is None:
                continue
            distance = math.dist(me[0], where[0])
            if distance <= radius:
                result.append((distance, chr_, vitals[0], vitals[1], where[0]))
        result.sort()
        return result[:limit]

    # ---------------------------------------------------------------- keyboard
    def keyboard_state(self):
        """The game's SDL key table (index = scancode) or None."""
        if not self.hooked or self.keyboard_missing:
            return None
        if not self.keyboard_ptr:
            function = self._host_symbol("libSDL3.so", "SDL_GetKeyboardState")
            if not function:
                self.keyboard_missing = True
                return None
            self.keyboard_ptr = self.call(function, 0, timeout=0.5)
        return self.read(self.keyboard_ptr, 100) if self.keyboard_ptr else None

    def _host_symbol(self, library, symbol):
        base = path = None
        with open(f"/proc/{self.pid}/maps") as f:
            for line in f:
                parts = line.rstrip("\n").split(None, 5)
                if len(parts) > 5 and library in parts[5] and int(parts[2], 16) == 0:
                    base, path = int(parts[0].split("-")[0], 16), parts[5]
                    break
        if not path:
            return 0
        try:
            # through the game's root: an AppImage's files need not be visible at the same path
            value = elf_symbol(f"/proc/{self.pid}/root{path}", symbol)
        except (OSError, struct.error, IndexError):
            return 0
        return base + value if value else 0
