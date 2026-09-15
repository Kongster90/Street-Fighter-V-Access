"""The game's own text, recovered from the player's copy of Street Fighter V.

Everything the mod checks readings against, and much of what it says (stage
names, the Tutorial's instructions, artwork credits), comes from the game's
localisation table, `strings.json`. It is Capcom's text, so it is not shipped:
each copy of the mod makes its own from the game it runs beside.

The table sits in the game's pak archives, standard Unreal pak version 3 with
an unencrypted index and AES-256-ECB encrypted contents. The key lives in the
executable, which Steam's DRM keeps encrypted on disk, so it is found in the
running game's memory: take one encrypted block whose plaintext must be
ordinary text (a configuration file) and offer every plausible 32-byte window
of the executable's data as a key. A wrong key gives noise, so the test is
decisive. It is a printable passphrase, which an early filter threw away on
the grounds that keys look random. The engine compresses first and encrypts
second, so undo them the other way round, and each compression block records
its length before encryption padding.

`tools/find_pak_key.py` and `tools/extract_strings.py` do this by hand; the
mod does it by itself the first time it finds the game running without a
`strings.json` (`ensure`), so a new player has nothing to run.
"""

from __future__ import annotations

import json
import struct
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from .memory import ProcessMemory, find_pid, process_path

ROOT = Path(__file__).resolve().parent.parent
STRINGS_FILE = ROOT / "strings.json"
KEY_FILE = ROOT / "pak_key.txt"
EXE = "StreetFighterV.exe"
GAME_PATH_HINT = r"Binaries\Win64"
MAGIC = struct.pack("<I", 0x5A6F12E1)
TARGET = "Content/Localization/Game_Steam/en/Game.locres"
# An uncompressed configuration file: its plaintext is plain ASCII, which makes
# a correct decryption obvious.
WANTED_SUFFIXES = ("BaseGame.ini", "BaseEngine.ini", "BaseInput.ini", ".ini")
# Tab, newline, carriage return and the printable range. A configuration file
# contains nothing else.
TEXT_BYTES = frozenset({9, 10, 13} | set(range(32, 127)))


@dataclass
class Entry:
    name: str
    offset: int
    size: int
    uncompressed: int
    method: int
    blocks: list[tuple[int, int]]
    header_size: int
    encrypted: bool


def paks_for(exe_path: str | Path) -> Path:
    """The pak folder of the game whose executable is at exe_path.

    The game runs from <install>\\StreetFighterV\\Binaries\\Win64 and its paks
    are in <install>\\StreetFighterV\\Content\\Paks, whichever Steam library
    holds it.
    """
    return Path(exe_path).resolve().parents[2] / "Content" / "Paks"


def running_game() -> tuple[int, Path] | None:
    """The running game's process id and pak folder."""
    pid = find_pid(EXE, path_contains=GAME_PATH_HINT, require_path=True)
    if pid is None:
        return None
    path = process_path(pid)
    return (pid, paks_for(path)) if path else None


def _read_entry(buf: bytes, pos: int) -> tuple[Entry, int]:
    start = pos
    offset, size, uncompressed, method = struct.unpack_from("<qqqi", buf, pos)
    pos += 28 + 20  # the fields above, then the hash
    blocks: list[tuple[int, int]] = []
    if method != 0:
        n = struct.unpack_from("<I", buf, pos)[0]
        pos += 4
        for _ in range(n):
            blocks.append(struct.unpack_from("<qq", buf, pos))
            pos += 16
    encrypted = bool(buf[pos])
    pos += 1 + 4  # encrypted flag, compression block size
    return Entry("", offset, size, uncompressed, method, blocks, pos - start, encrypted), pos


def read_index(path: Path) -> tuple[str, list[Entry]]:
    """A pak's mount point and file entries."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(max(0, size - 1024))
        tail = fh.read(1024)
        at = tail.rfind(MAGIC)
        if at < 0:
            return "", []
        _version, index_off, index_size = struct.unpack_from("<IQQ", tail, at + 4)
        fh.seek(index_off)
        index = fh.read(index_size)
    pos = 0
    mount_len = struct.unpack_from("<i", index, pos)[0]
    pos += 4
    mount = index[pos:pos + mount_len].split(b"\0")[0].decode("utf-8", "replace")
    pos += mount_len
    count = struct.unpack_from("<I", index, pos)[0]
    pos += 4
    out: list[Entry] = []
    for _ in range(count):
        nlen = struct.unpack_from("<i", index, pos)[0]
        pos += 4
        name = index[pos:pos + nlen].split(b"\0")[0].decode("utf-8", "replace")
        pos += nlen
        entry, pos = _read_entry(index, pos)
        entry.name = name
        out.append(entry)
    return mount, out


def _align16(n: int) -> int:
    return (n + 15) // 16 * 16


def decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if len(data) % 16:
        raise ValueError(f"encrypted run is not a whole number of blocks: {len(data)}")
    d = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return d.update(data) + d.finalize()


def read_file(pak: Path, entry: Entry, key: bytes | None) -> bytes:
    """An entry's bytes, decrypted and decompressed as needed."""
    if entry.encrypted and key is None:
        raise ValueError(f"{entry.name} is encrypted and there is no key")
    with pak.open("rb") as fh:
        if entry.method == 0:
            fh.seek(entry.offset + entry.header_size)
            raw = fh.read(_align16(entry.size) if entry.encrypted else entry.size)
            if entry.encrypted:
                raw = decrypt(raw, key)
            return raw[:entry.size]
        # Block offsets in pak version 3 are absolute positions in the file and
        # record the compressed length before encryption padding: read to the
        # next block boundary, decrypt, then trim before decompressing.
        chunks = []
        for start, end in entry.blocks:
            length = end - start
            fh.seek(start)
            raw = fh.read(_align16(length) if entry.encrypted else length)
            if entry.encrypted:
                raw = decrypt(raw, key)[:length]
            chunks.append(zlib.decompress(raw))
        return b"".join(chunks)


def _fstring(buf: bytes, pos: int) -> tuple[str, int]:
    n = struct.unpack_from("<i", buf, pos)[0]
    pos += 4
    if n == 0:
        return "", pos
    if n < 0:
        raw = buf[pos:pos - 2 * n]
        return raw.decode("utf-16-le", "replace").rstrip("\0"), pos - 2 * n
    raw = buf[pos:pos + n]
    return raw.decode("utf-8", "replace").rstrip("\0"), pos + n


def parse_locres(data: bytes) -> dict[str, str]:
    """A .locres table. Engine 4.7 writes the legacy, unversioned form."""
    pos = 0
    strings: dict[str, str] = {}
    ns_count = struct.unpack_from("<i", data, pos)[0]
    pos += 4
    if not (0 < ns_count < 100000):
        raise ValueError(f"unexpected namespace count {ns_count}")
    for _ in range(ns_count):
        namespace, pos = _fstring(data, pos)
        key_count = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        for _ in range(key_count):
            key, pos = _fstring(data, pos)
            pos += 4  # source string hash
            value, pos = _fstring(data, pos)
            strings[f"{namespace}/{key}" if namespace else key] = value
    return strings


def sample_block(paks: Path) -> tuple[bytes, str]:
    """One encrypted 32-byte block from an uncompressed text file."""
    for pak in sorted(paks.glob("*.pak")):
        mount, entries = read_index(pak)
        for e in entries:
            if e.method != 0 or not e.encrypted or e.size < 64:
                continue
            if not any(e.name.endswith(s) for s in WANTED_SUFFIXES):
                continue
            with pak.open("rb") as fh:
                fh.seek(e.offset + e.header_size)
                data = fh.read(32)
            if len(data) == 32:
                return data, mount + e.name
    raise LookupError(f"no encrypted text file in the paks at {paks}")


def plausible_key(window: bytes) -> bool:
    """Cheap tests that throw out almost every window. Printable text is kept:
    this game's key is a passphrase."""
    return window.count(0) <= 4 and len(set(window)) >= 12


def decrypts_to_text(key: bytes, block: bytes) -> bytes | None:
    """The block decrypted, if every byte of it is ordinary text."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    d = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    out = d.update(block) + d.finalize()
    return out if all(b in TEXT_BYTES for b in out) else None


def find_key(pm: ProcessMemory, block: bytes, heap: bool = False, progress=None):
    """Search the game for the pak key: (address, key, plaintext), or None.

    The executable's own data at every byte offset first, since a key compiled
    into the game need not be aligned; then, with `heap`, everything else on
    pointer alignment, which is far larger and slow.
    """
    mod = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
    plans = []
    for section in (".data", ".rdata", "_RDATA"):
        r = pm.section(mod, section)
        if r:
            plans.append((section, r.base, r.size, 1))
    if heap:
        plans += [("heap", r.base, r.size, 4) for r in pm.regions()
                  if not any(m.base <= r.base < m.end for m in pm.modules())]
    for key_len in (32, 16):
        for done, (label, base, size, step) in enumerate(plans, 1):
            data = pm.read(base, size)
            if data:
                for off in range(0, max(0, len(data) - key_len), step):
                    window = data[off:off + key_len]
                    if plausible_key(window):
                        out = decrypts_to_text(window, block)
                        if out is not None:
                            return base + off, window, out
            if progress:
                progress(key_len, label, done, len(plans))
    return None


def extract_strings(paks: Path, key: bytes | None) -> dict[str, str]:
    """The English localisation table from the game's paks."""
    for pak in sorted(paks.glob("*.pak")):
        mount, entries = read_index(pak)
        for e in entries:
            if (mount + e.name).replace("\\", "/").endswith(TARGET):
                return parse_locres(read_file(pak, e, key))
    raise LookupError(f"Game.locres not found in {paks}")


def write_strings(strings: dict[str, str], path: Path = STRINGS_FILE) -> None:
    temp = path.with_name(path.name + ".writing")
    temp.write_text(json.dumps({"count": len(strings), "strings": strings}, indent=1, ensure_ascii=False),
                    encoding="utf-8")
    temp.replace(path)


def recover(note=print) -> bool:
    """Find the key in the running game and write strings.json. True if it worked."""
    game = running_game()
    if game is None:
        note("game text: the game is not running")
        return False
    pid, paks = game
    started = time.monotonic()
    block, name = sample_block(paks)
    with ProcessMemory(pid) as pm:
        hit = find_key(pm, block)
    if hit is None:
        note(f"game text: no key found in the executable's data, tested against {name}")
        return False
    _where, key, _plain = hit
    strings = extract_strings(paks, key)
    KEY_FILE.write_text(key.hex(), encoding="utf-8")
    write_strings(strings)
    note(f"game text: {len(strings):,} strings written in {time.monotonic() - started:.1f} s")
    return True


_started = False


def ensure(say, note) -> None:
    """Make strings.json once, in the background, if it is missing and the game runs.

    `say` speaks to the player; `note` writes to the log. Called on every
    reading; does nothing after the first call in a session.
    """
    global _started
    if _started:
        return
    _started = True
    if STRINGS_FILE.exists():
        return

    def work() -> None:
        say("Setting up the game's text for the first time. This takes a moment.")
        try:
            done = recover(note)
        except Exception as exc:  # the rest of the mod carries on without it
            note(f"game text: failed: {exc!r}")
            done = False
        if done:
            _forget_loaded_text()
            say("The game's text is ready.")
        else:
            say("Could not set up the game's text. Menus will still read, but some screens may not. "
                "Start the game again to try again.")

    threading.Thread(target=work, daemon=True).start()


def _forget_loaded_text() -> None:
    """Make every reader of strings.json load it again, now that it exists."""
    from . import scaleform, strings

    scaleform._game_strings = None
    scaleform._tutorial_openings = None
    strings._shared, strings._loaded = None, False
