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

NVDA is what this was built against. Speech backends are tried in order: Tolk,
then the NVDA controller client, then accessible_output2, which pip already
installed and which works on its own. So this step is optional.

For Tolk, take the **x64** build from
[github.com/dkager/tolk](https://github.com/dkager/tolk) and drop `Tolk.dll`
beside `run.py`, along with `nvdaControllerClient64.dll` from NV Access. Both
must be 64-bit to match Python; a 32-bit one is reported by name at startup
rather than failing quietly.

## 3. The game's own text

This is what lets recognised text be corrected against what the game really
says, turning "RANKED MAT H" back into "RANKED MATCH". With the game running:

```bash
.venv\Scripts\python.exe tools\find_pak_key.py
```

```bash
.venv\Scripts\python.exe tools\extract_strings.py
```

The first finds the pak encryption key in the running process, in a couple of
seconds. The second uses it to unpack the English localisation table. Both
write files that stay on your machine.

Without them everything still works; menu text is simply read as recognised,
mistakes and all.

## 4. Character names

Character select reports each fighter's internal code, such as `Z21`. Turning
those into names needs a table, which is built by hovering the roster while the
game tells the tool which code is selected:

```bash
.venv\Scripts\python.exe tools\learn_names.py
```

`character_names.json` in the repository already has a good number of them, so
this only needs running for the ones still missing.

## 5. Run it

```bash
.venv\Scripts\python.exe run.py
```

Or double-click `Start SFV Access.bat`. Control Alt K lists the keys.

## Checking it works

```bash
.venv\Scripts\python.exe selftest.py
```

The other suites under `tools/` need no game running, except
`tools/test_screens.py`, which replays captured screens. Those captures are not
in the repository because they carry the game's artwork and whatever profile
name is on screen, so take your own with Control Alt S and add the expected
readings to that file.

## Building the native part

Only needed for the injected library, which is not finished. It expects
llvm-mingw, extracted into `toolchain/`:

```bash
toolchain\llvm-mingw-20260908-ucrt-x86_64\bin\x86_64-w64-mingw32-clang++.exe -shared -O2 -static -o native\toolchain_check.dll native\toolchain_check.cpp
```
