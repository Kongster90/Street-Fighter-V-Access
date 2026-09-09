# Handover

Written for whoever picks this up next. `README.md` explains how everything
works and why; this is the shorter version, plus the things that cost real time
to find out and would cost it again.

## Who this is for

The person you are working with is blind and uses NVDA. That shapes the work
more than anything else:

- They cannot check what is on screen for you. When something visual needs
  confirming, ask them to press Control Alt S, which writes a picture and a text
  dump into `snapshots/`, then read the picture yourself.
- Format replies linearly. No ASCII diagrams, no wide tables, no long runs of
  punctuation.
- Anything that speaks needs to be usable without sight. The learning tool had
  to be given speech and a stop hotkey before it was usable at all, because it
  runs with the game in front and the console behind it.

## What the project is

Street Fighter V draws its interface with Unreal's Slate renderer straight to
the GPU. Nothing on screen exists as a window, a control, or an accessibility
object, so NVDA sees one blank rectangle. There is nothing to expose. The
meaning has to be reconstructed, and this does it two ways.

**From the pixels.** Capture the frame, recognise the text, find the highlighted
entry by the gold the game marks it with, then correct the recognised text
against the game's own words.

**From the running game.** Read its memory from outside with ReadProcessMemory.
Used where the screen cannot help, which today means character select.

## What works

- Menu narration, automatic, as the cursor moves. Main menu, the story, versus,
  challenges and settings submenus, Battle Settings, arcade path select, all
  three training pause tabs.
- Settings rows report their value. Volume sliders report a level out of ten.
- Stage select reports the stage, time, temperature and weather.
- Character select reports both fighters, costume and colour, read from memory.
- Health, V-Trigger and Critical Art on a hotkey during a match.
- Speech through Tolk to NVDA, with fallbacks.

## Facts worth not rediscovering

**The game.** Unreal Engine 4.7, roughly. The executable has a `.bind` section,
which is Steam's DRM wrapper, so its code is encrypted on disk and only exists
in the clear while running. Static analysis of the file gets you nothing. There
are two processes called `StreetFighterV.exe`; the real one is the one under
`Binaries\Win64`, and matching on name alone picks the small launcher.

**Engine internals, all confirmed against this build and re-validated at
runtime before use:**

- name table pointer at `StreetFighterV.exe+0x3A75490`
- object list at `+0x3978730`, a flat `TArray` head of data pointer, count,
  capacity. Not the chunked array later engine versions use, which is why
  sweeping for a chunk table finds only noise.
- UObject fields: internal index `+0x0C`, class `+0x10`, name `+0x18`, outer
  `+0x20`
- class layout: next field `+0x28`, parent `+0x30`, child list `+0x38`,
  property offset `+0x4C`

Both tables were found by following references from something guaranteed to be
present, not by byte signatures, because this build predates the published ones.
The object list was found via the one object that is its own class, the UClass
named `Class`; that self-reference is a signature nothing else shares.

**A class defined as a Blueprint is a `BlueprintGeneratedClass`, not a `Class`.**
Accepting only the latter made every Blueprint lookup fail silently and fall
back to a full scan of 151,000 objects on every call.

**The interface is Scaleform GFx, not UMG.** 349 live GFx objects across 274
classes, against 7 for UMG. There is no widget tree to walk. The class names map
onto the screens: `WSMainMenuGFxPlayer`, `OptionMenuGFxPlayer`,
`CharaSelectGFxPlayer`, `GameUIGFxPlayer` for the match HUD. The
`ScaleformUtilGFxValue` objects that hold the on-screen content declare no
properties at all, being wrappers around Scaleform's native value type. Decoding
that is undone work.

**The pak files.** Standard Unreal pak version 3, unencrypted index, so the file
table reads without a key. The contents are AES-256-ECB encrypted. The key lives
in the executable and `tools/find_pak_key.py` recovers it from the running
process in about two seconds, by offering every plausible 32-byte window as a
key against a block whose plaintext must be ordinary text. It is a printable
passphrase, which an early filter discarded on the grounds that keys look
random. The engine compresses first and encrypts second, so undo them the other
way round, and each compression block records its length before encryption
padding, so read to the next block boundary, decrypt, then trim.

**The localisation table has 50,417 strings**, and this is the single most
useful thing in the project. It corrects every misreading, because a misreading
is by definition a string the game does not contain. Character names in it are
keyed by opaque hashes rather than by character code, which is why the code to
name mapping still has to be learned by hovering.

**The highlight colour is RGB 255, 227, 140**, identical on every screen.

## Traps

**There is one regression suite and it matters.** `tools/test_screens.py`
replays every captured screen through the real announcement code and checks the
entry that is actually highlighted. It is at 36 checks. Several times a change
fixed one screen and quietly broke two others, and this is the only thing that
caught it. Run it after every change to reading behaviour.

**Beware of two code paths.** The worst bug in the project was that everything
improved lived in `announce`, which only ran when a key was pressed, while the
narration the user actually hears went through a cruder rule. All the tests
passed and the mod still read the wrong thing. They share a path now. Do not
reintroduce a second one.

**Never let a test write to real data.** One version of `test_learning.py` wrote
to and then deleted `character_names.json`, destroying a table that had taken a
session in the game to build. Tests now point at scratch files and assert that
they are doing so.

**A capture taken mid-transition is not a bug.** One snapshot has the menu
still fading in, every pixel pure grey, no gold anywhere. No colour-based
detector can find a highlight in it. Check for that before chasing a phantom.

**Do not guess geometry.** Every layout question here was settled by capturing a
frame and measuring it. Guessing produced three wrong answers about which side
of the stage each fighter stands on before measuring produced the right one.

## Where it stands, and what to do next

In rough order of value:

1. **Sit with the user while they use it.** It has just had its narration path
   corrected and has not been tested in play since. Everything announced is
   logged to `snapshots/spoken-log.txt` with timestamps, so a bad reading can be
   looked at rather than recalled.

2. **Finish the character names.** About 20 of 56 codes are still unnamed, so
   they read as `Z34` rather than a name. `tools/learn_names.py` does it; the
   game's word list makes it reliable now. `tools/show_names.py` reports the
   state. The season codes cannot be self-checked, so if one reads wrongly in
   play, correct it by hand.

3. **Combat.** Deliberately deferred and completely unstarted. Speech cannot
   follow a round, so this wants continuous audio cues rather than words: pitch
   for health, stereo position for the distance between fighters, and speech
   kept for round transitions and a hotkey query. This is where the mod stops
   being a menu reader and becomes something to fight with. The HUD reader in
   `sfv_access/hud.py` already gives health and both meters.

4. **Move stage select to memory.** It works, but off the screen, so unlike
   character select it needs the game in front. There is almost certainly a
   stage code in memory to match, as with characters.

5. **The injected library.** `native/toolchain_check.cpp` builds and loads, so
   the toolchain is proven, but nothing else is written. Only worth doing for
   things reading cannot achieve, such as being notified when a menu changes
   instead of polling for it. Decoding Scaleform's value type would be the
   bigger prize, since it would generalise to every screen at once.

## Running things

Setup from a clean clone is in `SETUP.md`. Day to day:

```bash
.venv\Scripts\python.exe run.py
```

```bash
.venv\Scripts\python.exe tools\test_screens.py
```

The other suites are `selftest.py`, and `test_correction.py`, `test_learning.py`
and `test_memory.py` under `tools/`. All five should pass before anything is
committed. `tools/show_bands.py <snapshot>` explains why a screen was read the
way it was, and is the first thing to reach for when one reads wrongly.

Memory reading does not need the game in front, and does not care if it is
minimised. Reading the screen does.
