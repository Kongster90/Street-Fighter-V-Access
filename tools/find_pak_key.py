"""Recover the pak encryption key from the running game.

Street Fighter V ships its localisation table, and everything else, inside pak
archives whose contents are AES encrypted. The file table is readable but the
data is not, so the character names and every other interface string cannot be
read off disk. The key is held in the executable, which Steam's DRM keeps
encrypted on disk, so the only place it exists in the clear is the memory of
the running game.

The method needs no disassembly. Take one encrypted block whose plaintext is
known to be ordinary text, walk memory offering every plausible 32-byte window
as a key, and keep whichever one decrypts that block into something sensible.
A wrong key produces noise, so the test is decisive.

Most of memory is not key-shaped. Keys look random, so windows containing runs
of zeros, long repeats or mostly printable text are skipped, which removes the
overwhelming majority of candidates before any decryption is attempted.

    python tools/find_pak_key.py
"""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes  # noqa: E402

from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
PAKS = Path(r"G:\Steam\steamapps\common\StreetFighterV\StreetFighterV\Content\Paks")
MAGIC = struct.pack("<I", 0x5A6F12E1)

# An uncompressed configuration file: its plaintext is plain ASCII, which makes
# a correct decryption obvious at a glance.
WANTED_SUFFIXES = ("BaseGame.ini", "BaseEngine.ini", "BaseInput.ini", ".ini")


def read_index(path: Path):
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
    mount = index[pos : pos + mount_len].split(b"\0")[0].decode("utf-8", "replace")
    pos += mount_len
    count = struct.unpack_from("<I", index, pos)[0]
    pos += 4

    entries = []
    for _ in range(count):
        nlen = struct.unpack_from("<i", index, pos)[0]
        pos += 4
        name = index[pos : pos + nlen].split(b"\0")[0].decode("utf-8", "replace")
        pos += nlen
        start = pos
        offset, size_, _usize, method = struct.unpack_from("<qqqi", index, pos)
        pos += 28 + 20
        if method != 0:
            n = struct.unpack_from("<I", index, pos)[0]
            pos += 4 + n * 16
        encrypted = bool(index[pos])
        pos += 1 + 4
        entries.append((name, offset, size_, method, encrypted, pos - start))
    return mount, entries


def sample_block() -> tuple[bytes, str]:
    """One encrypted 32-byte block from an uncompressed text file."""
    for pak in sorted(PAKS.glob("*.pak")):
        mount, entries = read_index(pak)
        for name, offset, size_, method, encrypted, header in entries:
            if method != 0 or not encrypted or size_ < 64:
                continue
            if not any(name.endswith(s) for s in WANTED_SUFFIXES):
                continue
            with pak.open("rb") as fh:
                fh.seek(offset + header)
                data = fh.read(32)
            if len(data) == 32:
                return data, mount + name
    raise SystemExit("no suitable encrypted entry found")


def plausible_key(window: bytes) -> bool:
    """Could this be a key? Cheap tests that throw out almost everything.

    Deliberately does not reject text. Some projects set the pak key as a
    passphrase or a base64 string, so a window of printable characters is a
    perfectly good candidate; an earlier version discarded exactly those.
    """
    if window.count(0) > 4:
        return False
    if len(set(window)) < 12:
        return False
    return True


# Tab, newline, carriage return and the printable range. A configuration file
# contains nothing else.
TEXT_BYTES = frozenset({9, 10, 13} | set(range(32, 127)))


def decrypts_to_text(key: bytes, block: bytes) -> bytes | None:
    """Decrypt and say whether the result is entirely ordinary text.

    Every byte of both blocks has to qualify. Allowing even one exception let
    through a key whose output merely looked textual at a glance; across 32
    bytes a wrong key has almost no chance of passing.
    """
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    out = decryptor.update(block) + decryptor.finalize()
    return out if all(b in TEXT_BYTES for b in out) else None


def main() -> None:
    block, name = sample_block()
    print(f"testing against {name}")
    print(f"ciphertext: {block[:16].hex()}\n")

    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print(f"{EXE} is not running.")
        sys.exit(1)

    with ProcessMemory(pid) as pm:
        mod = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        searched = []
        for section in (".data", ".rdata", "_RDATA"):
            r = pm.section(mod, section)
            if r:
                searched.append((section, r.base, r.size))
        # The executable's own data first, since a key compiled into the game
        # lives there; then everything else, since it may be built at runtime.
        heap = [
            ("heap", r.base, r.size)
            for r in pm.regions()
            if not any(m.base <= r.base < m.end for m in pm.modules())
        ]

        t0 = time.perf_counter()
        tried = 0

        def sweep(label, base, size, key_len, step):
            nonlocal tried
            data = pm.read(base, size)
            if not data:
                return None
            for off in range(0, max(0, len(data) - key_len), step):
                window = data[off : off + key_len]
                if not plausible_key(window):
                    continue
                tried += 1
                out = decrypts_to_text(window, block)
                if out is not None:
                    return base + off, window, out
            return None

        # The executable's own data at every byte offset, since it is small and
        # a key compiled into the game need not be aligned; then the heap, which
        # is far larger, on pointer alignment.
        plans = [(name, b, s, 1) for name, b, s in searched]
        plans += [(name, b, s, 4) for name, b, s in heap]

        for key_len in (32, 16):
            print(f"trying {key_len * 8}-bit keys")
            done = 0
            for label, base, size, step in plans:
                hit = sweep(label, base, size, key_len, step)
                done += 1
                if hit:
                    where, key, out = hit
                    print(f"\nFOUND in {label} at 0x{where:x}")
                    print(f"  key       : {key.hex()}")
                    print(f"  as text   : {key!r}")
                    print(f"  plaintext : {out!r}")
                    print(f"  candidates: {tried:,} in {time.perf_counter() - t0:.1f} s")
                    (ROOT / "pak_key.txt").write_text(key.hex(), encoding="utf-8")
                    print(f"  saved to  : {ROOT / 'pak_key.txt'}")
                    return
                if done % 2000 == 0:
                    print(
                        f"  {done:,}/{len(plans):,} regions, {tried:,} tested, "
                        f"{time.perf_counter() - t0:.0f} s"
                    )
            print(f"  no {key_len * 8}-bit key found, {tried:,} tested")

    print(f"\nnot found. {tried:,} candidates tested in {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
