"""Build the zip that players install from.

    .venv\\Scripts\\python.exe tools\\build_package.py

Writes dist\\SFV-Access-<date>-<commit>.zip holding one folder, SFV Access:
the mod's code as committed, a copy of the Python this runs on with the
virtual environment's packages, and the files in package\\ (the installer, the
uninstaller and Read me first.txt). Nothing taken from the game goes in:
strings.json and pak_key.txt are made on each player's machine the first time
the mod sees the game (`sfv_access/gametext.py`), and settings and logs stay
with whoever made them.

The copied Python is checked before zipping by importing everything the mod
needs with it, isolated from this machine's own Python.

Afterwards it tidies up: the staging folder goes, being a full unzipped copy
worth 129 MB that is rebuilt from scratch every time, and so do older zips,
the user wanting only the newest kept. Both are named as they are removed.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
NAME = "SFV Access"

# From the committed files, only what a player's copy runs.
CODE_FILES = ("run.py", "start_with_game.pyw", "character_names.json", "roster.json", "Start SFV Access.bat")
CODE_DIRS = ("sfv_access",)
TOOLS = ("install.py", "uninstall.py", "steam_launch_options.py", "find_pak_key.py", "extract_strings.py")
# Parts of Python the mod never uses.
PYTHON_SKIP_DIRS = {"Doc", "include", "libs", "Scripts", "tcl", "share", "Tools"}
PYTHON_SKIP_LIB = {"test", "idlelib", "tkinter", "turtledemo", "ensurepip", "site-packages", "__pycache__",
                   "lib2to3", "pydoc_data"}
PYTHON_SKIP_DLLS = ("_tkinter", "tcl", "tk")
# Packages in the virtual environment used only by development tools.
PACKAGES_SKIP = ("pip", "capstone")
IMPORT_CHECK = ("import sfv_access.app, sfv_access.gametext, numpy, PIL, prism, win32api, win32com.client, "
                "bettercam, cryptography, winrt.windows.media.ocr; print('imports ok')")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def copy_python(target: Path) -> None:
    base = Path(sys.base_prefix)
    for item in base.iterdir():
        if item.name in PYTHON_SKIP_DIRS:
            continue
        if item.is_file():
            shutil.copy2(item, target / item.name)
        elif item.name == "Lib":
            shutil.copytree(item, target / "Lib", ignore=lambda d, names: [
                n for n in names if n == "__pycache__" or (Path(d) == item and n in PYTHON_SKIP_LIB)])
        elif item.name == "DLLs":
            shutil.copytree(item, target / "DLLs", ignore=lambda d, names: [
                n for n in names if n.lower().startswith(PYTHON_SKIP_DLLS)])
        else:
            shutil.copytree(item, target / item.name, ignore=shutil.ignore_patterns("__pycache__"))
    packages = Path(sys.prefix) / "Lib" / "site-packages"
    shutil.copytree(packages, target / "Lib" / "site-packages", ignore=lambda d, names: [
        n for n in names if n == "__pycache__"
        or (Path(d) == packages and n.lower().startswith(PACKAGES_SKIP))])


def tidy(keep: Path) -> None:
    """Remove the staging folder and every zip but the one just built."""
    stage = DIST / "stage"
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
        print(f"removed {stage}")
    for old in sorted(DIST.glob(f"{NAME.replace(' ', '-')}-*.zip")):
        if old.resolve() != keep.resolve():
            old.unlink()
            print(f"removed {old}")


def main() -> int:
    if sys.prefix == sys.base_prefix:
        print("Run this with the virtual environment's Python, whose packages go into the package.")
        return 1
    if git("status", "--porcelain", "--", "sfv_access", "tools", "package", *CODE_FILES):
        print("There are uncommitted changes to the mod. Commit them first, so the package matches a commit.")
        return 1
    commit = git("rev-parse", "--short", "HEAD")
    stamp = f"{dt.date.today():%Y-%m-%d}-{commit}"
    stage = DIST / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    folder = stage / NAME
    folder.mkdir(parents=True)

    for name in CODE_FILES:
        shutil.copy2(ROOT / name, folder / name)
    for name in CODE_DIRS:
        shutil.copytree(ROOT / name, folder / name, ignore=shutil.ignore_patterns("__pycache__"))
    (folder / "tools").mkdir()
    for name in TOOLS:
        shutil.copy2(ROOT / "tools" / name, folder / "tools" / name)
    for item in (ROOT / "package").iterdir():
        shutil.copy2(item, folder / item.name)
    (folder / "VERSION.txt").write_text(f"Street Fighter V Access test version {stamp}\n", encoding="utf-8")
    # The command prompt can misread batch files with bare line feeds, and
    # Notepad is happier with Windows line endings too.
    for path in folder.iterdir():
        if path.suffix.lower() in (".bat", ".txt"):
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            path.write_text(text, encoding="utf-8", newline="\r\n")
    print("copying Python")
    (folder / "python").mkdir()
    copy_python(folder / "python")

    check = subprocess.run([str(folder / "python" / "python.exe"), "-I", "-c",
                            f"import sys; sys.path.insert(0, r'{folder}'); {IMPORT_CHECK}"],
                           cwd=folder, capture_output=True, text=True)
    print(check.stdout.strip() or check.stderr.strip())
    if check.returncode != 0:
        print("The copied Python cannot import what the mod needs; not zipping.")
        return 1

    zip_path = DIST / f"SFV-Access-{stamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, path.relative_to(stage))
    size = zip_path.stat().st_size / 1024 / 1024
    print(f"wrote {zip_path} ({size:.0f} MB)")
    tidy(zip_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
