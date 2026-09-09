"""Dump the whole global name table to names.json.

Worth caching because every later step wants to look names up by text, and
because the list itself says a great deal about how the game is built: the
class names in it are the vocabulary of its interface.
"""

from __future__ import annotations

import json
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import unreal  # noqa: E402
from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
OUT = ROOT / "names.json"


def main() -> None:
    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print(f"{EXE} is not running.")
        sys.exit(1)

    with ProcessMemory(pid) as pm:
        mods = pm.modules()
        main_mod = next(m for m in mods if m.name.lower() == EXE.lower())
        static = [r for r in (pm.section(main_mod, s) for s in (".data", "_RDATA")) if r]

        t0 = time.perf_counter()
        names = unreal.find_name_array(pm, pm.regions(), static_regions=static, verbose=False)
        if names is None:
            print("name table not found")
            sys.exit(2)
        print(f"{names.describe()}  [{time.perf_counter() - t0:.1f} s]")

        layout = names.layout
        table: dict[int, str] = {}
        t1 = time.perf_counter()
        for chunk_index in range(names.num_chunks):
            chunk = pm.ptr(names.address + chunk_index * 8)
            if not chunk:
                continue
            # One read for the whole chunk of pointers beats 16384 small ones.
            raw = pm.read(chunk, layout.elements_per_chunk * 8)
            if not raw:
                continue
            base_index = chunk_index * layout.elements_per_chunk
            for i in range(layout.elements_per_chunk):
                if base_index + i >= names.num_elements:
                    break
                entry = struct.unpack_from("<Q", raw, i * 8)[0]
                if not entry:
                    continue
                text = unreal.entry_text(pm, entry, layout)
                if text is not None:
                    table[base_index + i] = text
        print(f"read {len(table):,} names in {time.perf_counter() - t1:.1f} s")

        OUT.write_text(
            json.dumps(
                {
                    "count": names.num_elements,
                    "resolved": len(table),
                    "names": {str(k): v for k, v in sorted(table.items())},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"wrote {OUT}")

        by_text = {v: k for k, v in table.items()}
        print("\nkey engine names and their indices:")
        for want in ("None", "Class", "Object", "Package", "Function", "Property",
                     "Widget", "UserWidget", "TextBlock", "Slider", "Button",
                     "ProgressBar", "CheckBox", "WidgetTree", "PanelWidget"):
            print(f"  {want:16s} {by_text.get(want, 'not present')}")

        interesting = sorted(
            v for v in table.values()
            if any(k in v for k in ("Widget", "Slider", "TextBlock", "ProgressBar"))
            and "/" not in v and len(v) < 48
        )
        print(f"\n{len(interesting)} interface-related names, first 40:")
        for v in interesting[:40]:
            print(f"  {v}")


if __name__ == "__main__":
    main()
