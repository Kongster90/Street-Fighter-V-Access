"""Pull the game's own English UI strings out of its pak files.

The menus are drawn from a localisation table shipped inside the paks, and the
paks are plain Unreal pak version 3 with an unencrypted index. Having that list
lets recognised text be snapped to the string the game actually drew, which
fixes the mistakes OCR makes on stylised menu type, such as reading
"RANKED MATCH" as "RANKED MAT H".

Writes strings.json next to the project.

Usage:
    python tools/extract_strings.py
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAKS = Path(r"G:\Steam\steamapps\common\StreetFighterV\StreetFighterV\Content\Paks")
MAGIC = struct.pack("<I", 0x5A6F12E1)

TARGET = "Content/Localization/Game_Steam/en/Game.locres"


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


def _read_entry(buf: bytes, pos: int) -> tuple[Entry, int]:
    start = pos
    offset, size, uncompressed, method = struct.unpack_from("<qqqi", buf, pos)
    pos += 28 + 20  # fields above, then the hash
    blocks: list[tuple[int, int]] = []
    if method != 0:
        n = struct.unpack_from("<I", buf, pos)[0]
        pos += 4
        for _ in range(n):
            blocks.append(struct.unpack_from("<qq", buf, pos))
            pos += 16
    encrypted = bool(buf[pos])
    pos += 1 + 4  # encrypted flag, compression block size
    return (
        Entry("", offset, size, uncompressed, method, blocks, pos - start, encrypted),
        pos,
    )


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

    out: list[Entry] = []
    for _ in range(count):
        nlen = struct.unpack_from("<i", index, pos)[0]
        pos += 4
        name = index[pos : pos + nlen].split(b"\0")[0].decode("utf-8", "replace")
        pos += nlen
        entry, pos = _read_entry(index, pos)
        entry.name = name
        out.append(entry)
    return mount, out


class Encrypted(Exception):
    """The entry is encrypted and no key is available."""


KEY_FILE = ROOT / "pak_key.txt"


def load_key() -> bytes | None:
    """The pak key, as recovered from the running game by find_pak_key.py."""
    try:
        return bytes.fromhex(KEY_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def align16(n: int) -> int:
    return (n + 15) // 16 * 16


def decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    if len(data) % 16:
        raise ValueError(f"encrypted run is not a whole number of blocks: {len(data)}")
    d = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return d.update(data) + d.finalize()


def read_file(pak: Path, entry: Entry, key: bytes | None = None) -> bytes:
    """The entry's bytes, decrypted and decompressed as needed.

    The engine compresses first and encrypts second, so this undoes them in the
    opposite order. Encrypted data is padded out to a whole number of AES
    blocks, so the decrypted result is trimmed back to the recorded size.
    """
    if entry.encrypted and key is None:
        raise Encrypted(entry.name)

    with pak.open("rb") as fh:
        if entry.method == 0:
            fh.seek(entry.offset + entry.header_size)
            raw = fh.read(align16(entry.size) if entry.encrypted else entry.size)
            if entry.encrypted:
                raw = decrypt(raw, key)
            return raw[: entry.size]

        # Block offsets in pak version 3 are absolute positions in the file, and
        # record the compressed length before encryption padding. So read out to
        # the next block boundary, decrypt, then trim back before decompressing.
        chunks = []
        for start, end in entry.blocks:
            length = end - start
            fh.seek(start)
            raw = fh.read(align16(length) if entry.encrypted else length)
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
        raw = buf[pos : pos - 2 * n]
        pos += -2 * n
        return raw.decode("utf-16-le", "replace").rstrip("\0"), pos
    raw = buf[pos : pos + n]
    pos += n
    return raw.decode("utf-8", "replace").rstrip("\0"), pos


def parse_locres(data: bytes) -> dict[str, str]:
    """Parse a .locres table. Engine 4.7 writes the legacy, unversioned form."""
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


def main() -> None:
    key = load_key()
    print(f"key: {'loaded' if key else 'none, run tools/find_pak_key.py first'}")

    for pak in sorted(PAKS.glob("*.pak")):
        mount, entries = read_index(pak)
        for e in entries:
            if not (mount + e.name).replace("\\", "/").endswith(TARGET):
                continue
            print(f"found in {pak.name}")
            print(f"  {e.size:,} bytes on disk, {e.uncompressed:,} uncompressed")
            print(f"  compression {e.method}, encrypted {e.encrypted}")

            data = read_file(pak, e, key)
            print(f"  recovered {len(data):,} bytes")
            strings = parse_locres(data)
            print(f"  {len(strings):,} localised strings\n")

            out = ROOT / "strings.json"
            out.write_text(
                json.dumps(
                    {"count": len(strings), "strings": strings},
                    indent=1,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            print(f"  wrote {out}")

            values = list(strings.values())
            for probe in ("RANKED", "TRAINING", "ZEKU", "AKUMA", "NASH", "Health Gauge"):
                hits = [v for v in values if probe.lower() in v.lower()][:3]
                print(f"  {probe!r}: {hits}")
            return
    print("Game.locres not found")


if __name__ == "__main__":
    main()
