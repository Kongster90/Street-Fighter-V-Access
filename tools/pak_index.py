"""List the contents of Street Fighter V's pak archives.

The paks are standard Unreal pak version 3 with an unencrypted index, so the
whole file table reads without any key. This matters because the game's own
localisation tables live in here, and those are the exact strings the menus
draw. Matching recognised text against that list is the cheapest way to fix
OCR mistakes such as "RANKED MAT H".

Usage:
    python tools/pak_index.py [substring ...]
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

PAKS = Path(
    r"G:\Steam\steamapps\common\StreetFighterV\StreetFighterV\Content\Paks"
)
MAGIC = struct.pack("<I", 0x5A6F12E1)
FOOTER = 44


def read_index(path: Path) -> tuple[str, list[str]]:
    """Mount point and file names held in one pak."""
    size = path.stat().st_size
    with path.open("rb") as fh:
        fh.seek(max(0, size - 1024))
        tail = fh.read(1024)
        at = tail.rfind(MAGIC)
        if at < 0:
            raise ValueError(f"{path.name}: no pak footer")
        version, index_off, index_size = struct.unpack_from("<IQQ", tail, at + 4)
        if version > 4:
            raise ValueError(f"{path.name}: pak version {version} not handled")
        fh.seek(index_off)
        index = fh.read(index_size)

    pos = 0
    mount_len = struct.unpack_from("<i", index, pos)[0]
    pos += 4
    mount = index[pos : pos + mount_len].split(b"\0")[0].decode("utf-8", "replace")
    pos += mount_len
    count = struct.unpack_from("<I", index, pos)[0]
    pos += 4

    names: list[str] = []
    for _ in range(count):
        nlen = struct.unpack_from("<i", index, pos)[0]
        pos += 4
        if nlen < 0:  # UTF-16 name
            raw = index[pos : pos - 2 * nlen]
            pos += -2 * nlen
            names.append(raw.split(b"\0\0")[0].decode("utf-16-le", "replace"))
        else:
            names.append(index[pos : pos + nlen].split(b"\0")[0].decode("utf-8", "replace"))
            pos += nlen

        # FPakEntry: offset, size, uncompressed size, method, hash,
        # then compression blocks when the entry is compressed.
        method = struct.unpack_from("<i", index, pos + 24)[0]
        pos += 8 + 8 + 8 + 4 + 20
        if method != 0:
            blocks = struct.unpack_from("<I", index, pos)[0]
            pos += 4 + blocks * 16
        pos += 1 + 4  # encrypted flag, compression block size

    return mount, names


def main() -> None:
    wanted = [a.lower() for a in sys.argv[1:]]
    total = 0
    hits: list[str] = []
    for pak in sorted(PAKS.glob("*.pak")):
        try:
            mount, names = read_index(pak)
        except Exception as exc:
            print(f"{pak.name}: {exc}")
            continue
        total += len(names)
        for n in names:
            full = mount + n
            if not wanted or any(w in full.lower() for w in wanted):
                hits.append(full)

    print(f"{total:,} files across the pak set")
    if wanted:
        print(f"{len(hits):,} match {wanted}\n")
        for h in sorted(set(hits))[:120]:
            print("  ", h)


if __name__ == "__main__":
    main()
