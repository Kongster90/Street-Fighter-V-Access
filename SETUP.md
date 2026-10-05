# Setting up from a fresh clone

The repository holds the code. It deliberately does not hold anything taken out
of Street Fighter V itself, so a few things have to be fetched or regenerated
on the machine that will run it. All of it is quick.

## 1. Python

Python 3.14 on Windows. From the project folder:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. A screen reader to speak through

NVDA is what this was built against. There is nothing to fetch: speech goes
through [Prism](https://github.com/ethindp/prism), which pip installed as
`prismatoid`. It finds NVDA or another running screen reader by itself and
falls back to the Windows voices when there is none.

## 3. The game's own text

Stage names, the Tutorial's instructions and the check that a text is one the
game can say all come from the game's localisation table. The mod makes `strings.json` by itself the first time it finds the game
running without one, saying so as it starts and when it is ready, in about
three seconds (`sfv_access/gametext.py`). To do it by hand instead, with the
game running:

```bash
.venv\Scripts\python.exe tools\find_pak_key.py
```

```bash
.venv\Scripts\python.exe tools\extract_strings.py
```

Both write files that stay on your machine.

## 4. Character names

These come from the game's own files and are already in the repository, in
`roster.json` and `character_names.json`; `tools/names_from_data.py` rebuilds
them, with the game running.

## 5. Run it

```bash
.venv\Scripts\python.exe run.py
```

Or double-click `Start SFV Access.bat`. Alt K lists the keys.

To have Steam start it with the game instead, close Steam and run:

```bash
.venv\Scripts\python.exe tools\steam_launch_options.py --apply
```

The launch options it writes name this folder, so run it again if the folder
moves. See "Starting with the game" in `README.md`.

## Building a package for players

```bash
.venv\Scripts\python.exe tools\build_package.py
```

This writes `dist\SFV-Access-<date>-<commit>.zip`, which carries its own
Python, so a player needs nothing installed. They extract it and run
`Install SFV Access.bat`, which copies it to
`%LOCALAPPDATA%\Programs\SFV Access` and sets the Steam launch options,
closing and reopening Steam for them. `package\Read me first.txt` is their
guide. Commit first: the build refuses uncommitted changes to the mod, so a
package always matches a commit.

## Checking it works

```bash
.venv\Scripts\python.exe selftest.py
```

The suites under `tools/`, every `tools/test_*.py`, need no game running.

## Building the native part

Only needed for the injected library, which is not finished. It expects
llvm-mingw, extracted into `toolchain/`:

```bash
toolchain\llvm-mingw-20260908-ucrt-x86_64\bin\x86_64-w64-mingw32-clang++.exe -shared -O2 -static -o native\toolchain_check.dll native\toolchain_check.cpp
```
