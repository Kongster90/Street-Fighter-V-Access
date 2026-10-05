# Street Fighter V Access

A screen-reader bridge for Street Fighter V on Windows. It reads what the game
shows out of the game's own memory and speaks it through NVDA, with sounds for
what speech is too slow to follow in a fight.

## Why there is nothing on screen to read

Street Fighter V is an Unreal Engine 4 game. Its menus, sliders and health bars
are drawn by Unreal's Slate renderer straight to the GPU. Unlike an ordinary
Windows program, none of it exists as a window, a control, or an accessibility
object, so NVDA sees one blank rectangle with nothing inside it to read.

This is worth being precise about, because it is easy to expect more of the
screen-reader libraries than they can give. Prism, which this uses, is output
only. A program hands it a string and it makes the screen reader say it. It
cannot inspect another application, hook into it, or discover
what it is displaying. They solve the speaking half of the problem, which was
never the hard half. Finding out what the game is showing is entirely up to us,
and there are only a few ways to do it: read the pixels, read the game's
memory, or inject code into the game. This tool reads the game's memory from
outside, with ReadProcessMemory and no injection; see "Reading the running
game" below, and `HANDOFF.md` for each screen.

Findings from this install that shape the approach:

- The game is Unreal Engine 4, and the shipped middleware (PhysX 3.3, APEX 1.3,
  Steamworks SDK 1.30) together with a `4.7.6-0` version string point at
  engine 4.7. That is old enough that the usual off-the-shelf Unreal SDK
  dumpers, which target 4.12 and newer, will not work unmodified.
- The executable carries a `.bind` section, the marker of Steam's DRM wrapper.
  Its code is encrypted on disk and only decrypted once the game is running, so
  analysing the file gets you nothing and everything must happen at runtime.
- There is no client-side anti-cheat in the install directory.

### Why the game files are not a shortcut

The obvious idea is to skip the screen and read the menu text out of the game's
own data. The pak archives are standard Unreal pak version 3 with an
unencrypted index, so `tools/pak_index.py` lists all 103,658 files by name, and
the English string table is right there at
`StreetFighterV/Content/Localization/Game_Steam/en/Game.locres`.

The contents, though, are AES encrypted, all 20,296 entries in the main
archive. Even the plain configuration files read as random bytes, at 7.99 bits
of entropy. The key sits in the executable, which Steam's DRM keeps encrypted
on disk, so the only place it exists in the clear is the memory of the running
game.

**Recovering the key.** `tools/find_pak_key.py` does this without any
disassembly. Take one encrypted block whose plaintext must be ordinary text, a
configuration file, then walk memory offering every plausible 32-byte window as
a key and keep whichever decrypts that block into something readable. A wrong
key produces noise, so the test is decisive. Keys look random, so windows
containing runs of zeros or long repeats are skipped first, which removes the
overwhelming majority before any decryption is attempted.

It found the key in 2.5 seconds, in the executable's read-only data. Two things
about that search are worth recording. The first attempt accepted a wrong key,
because the check allowed a single non-text byte in sixteen; requiring all
thirty-two bytes of two blocks to be text made false positives vanish. And the
key turned out to be a thirty-two character passphrase, entirely printable,
which an early filter had been discarding on the grounds that keys look random.

`tools/extract_strings.py` then decrypts and unpacks the English localisation
table: 50,417 strings, every piece of text the game can display. The engine
compresses before encrypting, so this undoes them in the other order, and each
compression block records its length before encryption padding, so each is read
out to the next block boundary, decrypted, then trimmed.

**What that gives us.** The character names come out of the game's own data
with it (`tools/names_from_data.py`), and memory narration uses the table as
the authority on what the game can say: a stage name that is not in it is not
a stage name, and the Tutorial's instructions are recognised by their opening
words. The mod makes `strings.json` itself the first time it finds the game
running without one (`sfv_access/gametext.py`).

## Requirements

- Windows 10 or 11
- NVDA running, though speech falls back to Windows voices on its own
- Python 3.14, already set up in `.venv`

Speech goes through [Prism](https://github.com/ethindp/prism), installed by pip
as `prismatoid`. It picks the best output available: a running screen reader
first, NVDA among them, then Windows OneCore voices, then SAPI 5. It talks to
NVDA directly, so no DLLs are needed beside `run.py`. If the screen reader it
chose exits while the tool is running, the next announcement picks again.

## Running it

Double-click `Start SFV Access.bat`, or from a terminal in this folder:

```bash
.venv\Scripts\python.exe run.py
```

To check that speech, capture and reading the game's memory all work:

```bash
.venv\Scripts\python.exe selftest.py
```

Only one copy can run at a time, because hotkeys are exclusive. A second copy
says so at startup instead of leaving its keys quietly dead.

### Starting with the game

Steam can start the mod each time Street Fighter V starts, through the game's
launch options. With Steam closed:

```bash
.venv\Scripts\python.exe tools\steam_launch_options.py --apply
```

That sets the launch options to run `start_with_game.pyw` before the game, the
same way SMAPI is started for Stardew Valley. It changes nothing else in
Steam's settings, keeps a copy of the file it edits, and `--remove` takes it
back out. Run it with neither to see what is set.

Started this way the mod opens no window, writes what it would have printed to
`snapshots/console-log.txt`, and closes a few seconds after the game does. If
a copy is already running, for instance one started by hand, it leaves that
one alone. F10 still closes it early, and `Start SFV Access.bat` still starts
it by hand.

## Keys

These work while the game has focus, including in fullscreen.

- Alt R: read what is selected, with its detail
- Alt H: read health and meters
- Alt P: read the game's own state, currently character select
- Alt D: describe the selected entry
- Alt Down: next line
- Alt Up: previous line
- Alt Home: first line
- Alt End: last line
- Alt Period: repeat the current line
- Alt A: read the whole screen
- Alt M: turn menu narration on or off
- Alt B: name buttons as Xbox buttons, PlayStation buttons or keyboard keys, remembered between runs
- Alt T: turn story subtitles on or off, remembered between runs
- F5 and Shift F5: health beeps louder or quieter, 5 percent at a time from 40, remembered between runs; 0 is off
- F6 and Shift F6: the counter hit sound louder or quieter, the same way
- F7 and Shift F7: the crossup sound louder or quieter, the same way
- Alt S: save a picture of the game and what memory reads, for checking one against the other
- Alt G: status
- Alt X: stop speaking
- Alt K: list these keys
- F10: quit

Menu narration is on at startup. It announces the selected entry whenever it
moves, read from the game's memory: exact text, whether a song is ticked or
unavailable, a prompt's question and answer, and grids of names or pictures.
Everything it reads and says is logged to `snapshots/scaleform-log.txt`, and
everything said to `snapshots/spoken-log.txt`. Until the game has drawn text it
can read, nothing is said and the read keys say they cannot read the game yet.
Memory is read whether or not the game is the window in front.

## Reading the running game

Work in progress, and already past the point where the game's internals are
readable. Everything below is done from outside the process with
ReadProcessMemory, so a wrong pointer fails a read instead of crashing the
game. Tools live in `tools/`; the game must be running.

**The name table.** `find_names.py` locates Unreal's global name table by
following references from a string that has to be in it, then proves the
candidate by resolving names back out. No byte signatures are involved, which
matters because engine 4.7 predates the published ones and the DRM wrapper
rules out searching the file. It resolves to roughly 65,000 names, index zero
being "None". `dump_names.py` writes them all to `names.json`.

**The object list.** `find_objects.py` finds the global object list by locating
the one object that is its own class, the UClass named "Class". That
self-reference is a signature nothing else shares, and matching it pins down
the name and class field offsets at the same time. This build keeps its objects
in a flat array rather than the chunked one later versions use, which is why
sweeping for a chunk table found nothing. About 145,000 live objects, each with
a resolvable name, class and full path.

Confirmed for this build, as module offsets from `StreetFighterV.exe`:

- name table pointer at `+0x3A75490`
- object list at `+0x3978730`, a flat array head of data pointer, count, capacity
- UObject fields: internal index `+0x0C`, class `+0x10`, name `+0x18`, outer `+0x20`

Both are checked before use, so a game update that moves them costs a fallback
to the full search rather than a wrong answer.

**What the object graph revealed.** The interface is not built with Unreal's
own widgets. It is Scaleform GFx, Adobe's Flash-based middleware, with 349 live
GFx objects across 274 classes against 7 for UMG. `dump_objects.py` reports
this, and the class names line up exactly with the screens: `PortalMenuGFxPlayer`,
`MainTitleMenuGFxPlayer`, `OptionMenuGFxPlayer`, `CharaSelectGFxPlayer`,
`CommandListGFxPlayer`, `GameUIGFxPlayer` for the match HUD, and
`MainMenuHeaderGFxPlayer` and `MainMenuFooterGFxPlayer` for the chrome around
every menu.

This redirects the plan. There is no UMG widget tree to walk. What there is
instead are the `GFxPlayer` and `GFxDataProvider` objects, which are ordinary
Unreal objects holding the data the game pushes into Flash, and which therefore
have readable properties. `CharaSelectGFxDataProvider` should hold the
character list.

**Class layout and properties.** `find_properties.py` works out where a class
keeps its field list and where a property records its offset, by trying
candidates and keeping whichever one makes every field resolve to something the
engine recognises. All 560 sampled fields resolve, so the answer is not in
doubt. Confirmed: next field `+0x28`, parent class `+0x30`, child list `+0x38`,
property offset `+0x4C`.

With that, live objects read properly. Text, object references, numbers and
flags all come out, and inherited engine plumbing can be told apart from what
the game declares itself. Reading the live character select screen gives, among
others:

- `SwfMovieAssetPath` = `SwfMovie'/Game/MenuAsset/CharaSelectGFx/CharacterSelectGFx...'`
- `MenuRootValue`, `CharaNameValues`, `TimeCounterValue` pointing at GFx values
- `pManager` pointing at the live `BP_CharaSelectManager_C_0`

**Where this stops, for now.** The `ScaleformUtilGFxValue` objects that hold the
actual on-screen content declare no properties at all. They are thin wrappers
around Scaleform's own native value type, so the text lives in native fields
behind the object header rather than anywhere Unreal describes. Their shape is
consistent across instances, four pointers followed by inline data, and one
sample already reads as UTF-16 text, so it is tractable. It is simply a second
reverse engineering pass into Scaleform rather than Unreal.

Two routes from here. Decoding that value type generalises to every screen at
once, which makes it the one worth having. Reading each screen's own state is
quicker per screen but has to be redone for each one.

**Scaleform's own text, working from memory.** The general route turned out not
to need the value type at all. Scaleform's text fields can be found directly:
each owns a DocView whose function table sits at a fixed place in the
executable, so one sweep of Scaleform's heap pages finds them all, and each
leads to its paragraphs of UTF-16 text. From the field, the parent chain and
the render nodes give its position on the stage and the colour it is tinted.
The selected menu entry is tinted gold, RGB 255, 227, 140 on screen,
stored as the multiplier 1.0, 0.89, 0.549. `sfv_access/scaleform.py`
does this, and `tools/read_scaleform.py` prints or speaks it. It is what
narration uses, through `sfv_access/memory_narration.py`. Each part of a screen
also carries the instance name its author gave it ("moneyLabelElement",
"reward", "cursorElement"), which says what a text means where its position
cannot; see `HANDOFF.md`.

**Character select, from the game's objects.** The roster is artwork with no
text. The game keeps a preview model on stage for each side, and that model
knows exactly what it is:

- `CharaCode`, the internal character code
- `CostumeId` and `ColorId`

`sfv_access/live.py` serves this, and Alt P speaks it on demand. Narration
does not need it: the fighters' names are read from Scaleform and are the only
selection on that screen (`scaleform.mark_fighters`), so moving through the
roster says each name, and the costume and version panels after a pick read
as gold menus.

Making that fast enough to poll took three fixes. Objects are not allocated in
screen order, so there is no shortcut of looking only at recently created ones;
the whole pointer array is read in one go and each entry checked by comparing
pointers rather than resolving names. Re-deriving the process id means walking
every process on the machine, so instead a value at a known address is read to
confirm the existing handle still works. And moving the cursor destroys the
preview models and builds new ones, so caching them by address is useless;
the scene actor that owns them survives the whole screen and holds them in an
array, which turns each later read into two pointer lookups.

Two mistakes along the way are worth recording. Looking up a class by name only
accepted `Class`, but a class defined as a Blueprint is a
`BlueprintGeneratedClass`, so every Blueprint lookup silently failed and fell
back to a full scan on every single call. And resolving each object's name to
compare it meant several reads per object across 151,000 of them, when the name
being searched for has exactly one index that can be found once and compared as
a single integer.

Together those take the first read on arriving at the screen from six seconds
to two, and every read after it to about thirty milliseconds.

The codes are mapped to names from the game's own data by
`tools/names_from_data.py`, into `character_names.json`. They were once learned
by hovering, pairing the code in memory with the name read off the screen,
which was slow and went wrong quietly; three codes use the Japanese names
(`VEG` is M. Bison, `BLR` Vega, `BSN` Balrog) and could never have been learned
that way.

### Native toolchain

`toolchain/` holds llvm-mingw, extracted from the project's own release zip. It
is portable, so nothing was installed and deleting the folder removes it
entirely. Build the check with:

```bash
toolchain\llvm-mingw-20260908-ucrt-x86_64\bin\x86_64-w64-mingw32-clang++.exe -shared -O2 -static -o native\toolchain_check.dll native\toolchain_check.cpp
```

`native/toolchain_check.cpp` exists to prove the chain works: it builds to a
64-bit DLL that loads and returns the expected value when called. That is all
it is for, and it is where the injected library will start.

## The screen reader that came first

Until 2026-10-04 the mod could also read the screen: Windows' text
recognition over captured frames, the selected entry found by its gold, the
gauges measured off the picture, and the text corrected against the game's
localisation table. Memory reading replaced it screen by screen, and once
every screen read from memory the user asked for it to go. Its code, and the
tools and tests built around it (`tools/replay.py`, `tools/test_screens.py`,
`tools/show_bands.py`, `tools/learn_names.py` and others), are in the history
up to commit d2f50c4. Screen capture remains, for Alt S's pictures.

## A caution about online play

Reading another process's memory, and injecting code into it, is what cheat
software does. This mod only reads memory from outside; it never writes to the
game or injects anything. Whether to use it online is each player's choice.
