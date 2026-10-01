# Street Fighter V Access

A screen-reader bridge for Street Fighter V on Windows. It reads the game's
frames, works out what is on screen, and speaks it through NVDA.

## Why the screen has to be read from pixels

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
and there are only four ways to do it: read the pixels, measure the pixels,
read the game's memory, or inject code into the game. This tool currently does
the first two, and the roadmap below covers the others.

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

**What that gives us.** Every learned character name was checked against this
table and all 26 appear in it verbatim, which is genuine confirmation: the
learner reads the screen and knows nothing about the table, and the table knows
nothing about what was on screen. `tools/check_names.py` does that check.

The names are keyed by opaque hashes rather than by character code, so the
mapping still has to be built by hovering. But the table works as a dictionary,
and `learn_names.py` now refuses any reading that is not a string the game
contains. That instantly rejects ZEW, ROS, PO SO, EN, ILL and CRY, every one of
the misreadings seen in real sessions, while accepting ZEKU, ROSE, POISON,
NASH, NECALLI and the fighter called simply G. Because the check is so much
blunter than the shape rules, a name the game vouches for now needs only two
agreeing reads rather than four.

**Correcting the menus with it.** `sfv_access/strings.py` snaps recognised text
to the nearest string the game can actually display. Every misreading is by
definition a string the game does not contain, and the right answer is
somewhere in the table, so "BAÜLE LOUNGE" becomes "BATTLE LOUNGE", "RANKED MAT
H" becomes "RANKED MATCH" and "HARA ER SELECT" becomes "Character Select". It
also restores words dropped entirely: one settings description was being read
without its leading "Player 1".

Comparing each line against fifty thousand strings one at a time is far too
slow to do while narrating. Each string is indexed by the three-character runs
it contains, so a query is only compared against the few dozen entries sharing
several of its runs. A correction takes about two milliseconds, and an exact
match none at all.

It refuses to guess. Anything under three characters, and anything it cannot
match closely, is left as it was, so player names, league points, dates and
scores pass through untouched. `tools/test_correction.py` checks both halves of
that against misreadings taken from real captures.

## How the two halves work

Menus are text, so they go through the OCR engine built into Windows. The
highlighted entry is then found by colour: every menu in the game marks the
current entry the same way, gold text close to RGB 255, 227, 140 on a near
black bar. That was measured across the main menu, the story, versus,
challenges and settings submenus, and the training pause menu, and it is
identical in all of them.

Finding the gold costs a few milliseconds, so the highlight is tracked several
times a second and only the small strip around it is passed to OCR. That is
what makes live narration affordable while you move through a menu.

The gauges are the opposite case. Health, V-Trigger and the Critical Art gauge
contain no text at all, so OCR can never see them. They are measured straight
from the pixels at known positions instead.

Which of the two applies is decided by looking for real health bars, using
both their colour and whether that colour forms one unbroken run. Character
select artwork also puts warm tones in those rows, and the contiguity test is
what tells a health bar apart from a picture of a fighter.

## Requirements

- Windows 10 or 11 with the English OCR language pack, present by default
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

To check that speech, capture and recognition all work:

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

- Alt R: read what is selected, or the gauges during a match
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
- F9: switch between reading the game's memory and reading the screen
- Alt B: name buttons as Xbox buttons, PlayStation buttons or keyboard keys, remembered between runs
- F5 and Shift F5: health beeps louder or quieter, 5 percent at a time from 40, remembered between runs; 0 is off
- F6 and Shift F6: the counter hit and crossup sounds louder or quieter, the same way
- Alt S: save a snapshot for calibration
- Alt G: status
- Alt X: stop speaking
- Alt K: list these keys
- F10: quit

Menu narration is on at startup. It announces the selected entry whenever it
moves, read from the game's memory: exact text, whether a song is ticked or
unavailable, a prompt's question and answer, and grids of names or pictures.
Everything it reads and says is logged to `snapshots/scaleform-log.txt`.

When memory cannot be read, narration falls back to the screen. That stands
down during a match, where speech cannot keep pace and the gauges are on a
hotkey instead, and whenever the game is not the window in front, since capture
covers the whole screen and would otherwise narrate whatever you had switched
to. F9 chooses between the two by hand, for a screen one of them
reads and the other does not. The read keys use memory when it has a reading,
and the screen otherwise.

## What works

Verified by replaying captured screens through the real announcement code, with
`python tools/replay.py`. The main menu, the story, versus, challenges and
settings submenus, the arcade path select, and all three training pause menu
tabs are read correctly, with the entry name, its position in the list, its
value where it has one, and the game's own description of it. A settings row
reads as, for example, "1P Health Gauge, Auto Recover, 5 of 23, Character
Health Gauge Settings."

The in-match gauges read correctly for health, V-Trigger and Critical Art.

### Reading the settings screens

These screens broke several assumptions at once, and `tools/test_screens.py`
now checks every captured screen against the entry that is really highlighted,
so a change that fixes one and breaks two is obvious instead of invisible.

The settings screens keep a list of pages on the left and the open page on the
right, and highlight one entry in each. Treating a run of rows as a single band
merged the two into one spanning the whole screen, whose recognised text was
both entries run together. Bands are now split on horizontal gaps, and where
several survive, the one on the widest dark bar wins, since the panel's bar
spans most of the screen while a list item's is a few hundred pixels. Within
one bar the leftmost entry wins, which is the label rather than its value; bar
widths are bucketed for that comparison because a label and its value measure a
pixel or two apart, and an exact comparison picked the value and announced
"Auto Recover" instead of the setting it belonged to.

Gold frames run along the edges of these screens and carry more gold than any
lettering, so bands near the edge are discarded and the rest are read, with only
those yielding actual text considered.

Comparing bar widths turned out not to measure what it claimed. On the volume
rows it made the page list win over the setting being changed, so moving
between volume sliders announced "Sound Settings" every time. The bands are now
grouped by how close together they sit vertically, which separates two quite
different situations that want opposite answers. A settings screen highlights
the page in its list and the row in its panel, far apart, and the panel is the
live one, so the rightmost group wins. A single entry can also span several
lines, as an arcade path shows its title, battle count and best score all in
gold, and there the topmost line is the label. Within a group the topmost and
leftmost band is the label and anything to its right is its value.

Separating bands horizontally also fixed Battle Settings, which had been a known
gap for days. Its measurement had been diluted by a band stretching across the
whole width; once the measurement was local to the entry, the threshold could
come down to reach it without letting artwork through elsewhere.

The screen settings page had been announcing itself as a match in progress. It
draws a sample HUD so its position can be adjusted, and that sample is pixel for
pixel a real one, so no measurement of the bars can tell it apart. A highlighted
menu entry now settles it first, since during an actual round there is not one.

### Reading a slider

Volume rows carry a drawn bar of ten cells and a printed number. On every row
but the highlighted one the number reads fine; on the highlighted one it is
small, gold on black, and falls inside the same band as the bar, and no amount
of re-reading that band recovered it reliably.

So the bar is counted instead, which is exact. Which way round the cells are
depends on the row: on an ordinary row the panel is pale and a filled cell is
dark, while on the highlighted row the bar is black and a filled cell is
bright. Measuring each cell's distance from the background of its own row
covers both without needing to know which applies, and the separation is not
close, with filled cells scoring above 115 and empty ones below 30.

A level fills from the left, so the filled cells must form a run starting at
the first one. Anything else is not a bar, which is what stops a word sitting
in a pill across the middle of a row from being reported as a level.

It is announced as "level 8 of 10" rather than "8 of 10", because the position
in the list follows immediately and two bare counts in a row cannot be followed
by ear.

### Reading stage select

Stage select has no highlighted entry to find. It shows one stage at a time
filling the screen, with the name across the middle and the conditions beneath
it, so `sfv_access/screens.py` reads it by position instead.

The screen is recognised by its conditions rather than its heading. The heading
is stylised and comes back as anything from "STAGESELECT" to "ST -", while
Time, Temperature and Weather are plain text and always present.

The names are drawn in the same stylised type and arrive badly damaged, and
this is where the localisation table pays for itself: "Ringof PoWer" becomes
"Ring of Power", "Metro City,Bay AiZa=" becomes "Metro City Bay Area", and
"Hollif ollyBeatdown" becomes "Holly Jolly Beatdown". Stages that have two
variants keep them apart, so The Grid and The Grid Alternative read distinctly.

Two smaller things. The degree sign comes back as a zero, so eighty degrees
reads as "800 F"; stage temperatures are two digits, which makes the trailing
zero unambiguous, and it is spoken as "80 degrees Fahrenheit". And the screen
carries a highlighted control of its own for the stage setting, which was being
announced instead of the stage; the stage leads now and the control follows.

Correcting a whole announcement at once finds nothing, because no single line
of the game's text is a stage name and its conditions together. It is corrected
a clause at a time instead, since each part is its own string in the table.

That work exposed a real fault in correction. "Temperature 800 F" matched the
bare word "Temperature" closely enough to win, and the reading was silently
thrown away. A correction must now carry the same whole numbers as the text it
replaces. The first version of that rule compared every digit and blocked a
good correction, because recognition drops digits into the middle of words and
had turned "Area" into "A7ea"; only numbers standing on their own count.

### One path, not two

Everything above described how a screen is read. For a long time none of it
reached the narration you actually hear.

There were two paths. Pressing the read key called `announce`, which is where
every improvement went: picking the right entry among several highlights,
reading a slider by counting its cells, correcting text against the game's own
words, handling stage select. Moving through a menu went somewhere else
entirely, through a rule that simply picks whichever patch of gold is largest,
which is the behaviour all of that work replaced.

So the tests passed and the mod still read the wrong thing, because the tests
exercised the path nobody was listening to. The scan now only detects that the
highlight moved; deciding what to say is left to `announce` in both cases. An
announcement costs about a hundred milliseconds, which is comfortably inside
the time it takes to move from one entry to the next.

Moving through a menu leaves the description out, since hearing a whole
sentence on every press is exhausting. Asking for a reading includes it, and
Alt D says it alone.

Everything announced is written to `snapshots/spoken-log.txt`, so a reading
that comes out wrong in play can be looked at afterwards rather than recalled.

### Known gaps

- Stage select is read off the screen rather than out of memory. That works and
  the names come out right, but it only does so while the game is the window in
  front, unlike character select.
- Stage select is read off the screen rather than out of memory. That works and
  the names come out right, but it only does so while the game is the window in
  front, unlike character select.
- The stun gauge is not read. It was empty in every capture so far, so there is
  nothing yet to calibrate against.
- The V-Trigger stock count reports how many are charged, not how many the
  character has in total. Telling an empty stock apart from an absent one needs
  a capture with a partly filled gauge.

## Calibration

`Alt S` writes a PNG and a matching text file into `snapshots/`. The
text file lists every recognised line with its position. `tools/replay.py`
then replays any snapshot through the live announcement code, which is how
this was built and how a regression gets caught.

For the character table: `learn_names.py` builds it, `show_names.py` reports it
and says which entries check themselves, and `test_learning.py` replays the
failures above against the learner without needing the game. That test writes
to a scratch file under `snapshots/`, because an earlier version of it wrote to
and then deleted the real table.

Other tools in `tools/`: `crop.py` cuts a region out for close inspection,
`analyze_selection.py` measures how the highlighted entry differs from the
rest, `analyze_hud.py` locates the gauges, and `test_highlight.py` checks
highlight detection and times it.

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
`MainMenuHeaderGFxPlayer` and `MainMenuFooterGFxPlayer` for the chrome that the
pixel reader has to filter out.

This redirects the plan. There is no UMG widget tree to walk. What there is
instead are the `GFxPlayer` and `GFxDataProvider` objects, which are ordinary
Unreal objects holding the data the game pushes into Flash, and which therefore
have readable properties. `CharaSelectGFxDataProvider` should hold the
character list, and that is one of the screens the pixel reader cannot handle.

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
The selected menu entry is tinted with the same gold the pixel reader looks
for, stored as the multiplier 1.0, 0.89, 0.549. `sfv_access/scaleform.py`
does this in about a third of a second, and `tools/read_scaleform.py` prints
or speaks it. It is now what narration uses, through
`sfv_access/memory_narration.py`, with the pixel reader as the fallback.

**Character select, working from memory.** Taking the second route for one
screen first, because it is the screen the pixel reader fails at completely.
The roster is artwork with no text, so recognition can only ever see the two
large names. The game, meanwhile, keeps a preview model on stage for each side,
and that model knows exactly what it is:

- `CharaCode`, the internal character code
- `CostumeId` and `ColorId`, which the pixel reader cannot read at all

`sfv_access/live.py` serves this. Alt P speaks it on demand, and menu
narration falls back to it automatically whenever no highlighted text can be
found, which is exactly the character select case. Memory narration does not
use it: the fighters' names are read from Scaleform and are the only
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

What is missing is the mapping from code to the name a person would recognise.
Those names come from the encrypted localisation table, so `tools/learn_names.py`
builds the table the other way round: it reads the code from memory and the
displayed name off the screen. Scroll the roster with the game in front and it
fills itself in, saving to `character_names.json`. Until a code is known it is
spoken as-is.

Getting that pairing right took three attempts, and the failures are the
instructive part, because every one of them was silent.

The preview models carry no player number, and nothing about the order they
appear in the object list corresponds to which side they stand on, so the first
version matched every code against the other fighter's name. Ordering by world
position fixed the stability, since the two stand at roughly Y minus 570 and
plus 530, but not the question of which end is player one, which cannot be read
from the objects at all. Guessing that from the roster's initials was still
wrong often enough to produce a table where six different codes had all been
learned as KEN.

So the current version assumes nothing about sides. It watches for change
instead: move the cursor and exactly one code changes in memory while exactly
one name changes on screen, and those two must belong together. That fixes the
link with no geometry involved, and the link drives everything after. The first
observation is deliberately not treated as a change, because registering both
sides at once leaves nothing to disambiguate.

Two rules then catch what would otherwise pass unnoticed. A display name
belongs to exactly one character, so a name already spoken for is refused
rather than reassigned; that rule alone would have caught the entire first bad
table. And where a code is alphabetic it should read as initials of the name,
so KEN, CMY and RSD line up with KEN, CAMMY and RASHID, and one that does not
line up is refused. Rejections are written to `snapshots/learn-log.txt` rather
than spoken, so a stream of failures does not talk over you.

Reads can also land while the game is rewriting a string, which yielded codes
like `äµ°ÞªÆ` that were then learned as characters. Codes are now required to be
short and alphanumeric.

Until the sides are settled the reader names both fighters without claiming a
player number, so it is obvious whether the table is calibrated.

A later session exposed a subtler fault that only showed up by comparing two
tables built on different days. Four codes had quietly changed meaning between
them and four names had disappeared entirely, with nothing said either time.
The pairing was right; the timing was not. The displayed name and the preview
model update at different moments as the cursor moves, and during that gap a
wrong pairing sits perfectly still. Two agreeing reads was only six tenths of a
second of stability, which the gap could outlast. It now takes four, and a
recorded entry is never quietly replaced: a disagreement is reported and the
existing value kept.

The same comparison caught two entries that were not names at all but partly
recognised ones, `ROS` where ROSE was on screen and `PO SO` for POISON. A
candidate that is the beginning of a name already recorded is now refused, as
is a short two-word name with no full stop, since the real two-word names all
carry one.

A third session showed the protections working and moved the problem somewhere
else. Eleven disagreements were reported and refused, and in every case the
recorded name was right and the new reading was a damaged one: KEN read as EN,
GILL as ILL, AKUMA as KUMA, RYU as CRY, CHUN-LI as CHU NZLI. Without the rule
against quiet replacement that pass would have destroyed ten correct entries.
Nine other characters produced no readable name at all.

So the bottleneck is no longer the pairing but the recognition itself. The
names are outlined type over a full-bleed picture of the fighter, which the
engine reads badly. `ocr.boost` discards everything below the top of the
brightness range and inverts what is left, turning pale lettering over artwork
into dark text on a light ground. On the captures to hand that takes ZRKUJ to
ZEKU and unreadable to readable. Each name is now read both ways, and when the
two agree the reading counts double towards confirmation, so a clean name is
learned in half the time while a doubtful one still has to prove itself.

All of these, including the exact failure that produced the table of nothing
but KEN, are replayed against the learner by `tools/test_learning.py`, which
writes to scratch files so it cannot touch the real table or the real log.

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

## Roadmap

**Next.** Close the gaps above. Character select and the Battle Settings page
both need a capture pass of their own.

**After that.** Speech is too slow to follow a live round, so the gauges want
continuous audio cues rather than words: a tone whose pitch tracks health, a
stereo position that tracks the distance between fighters, and spoken output
kept for hotkey queries and round transitions.

**Reading the running process.** Reading values out of memory from outside,
with ReadProcessMemory and no injection at all, would give exact health, meter,
timer and round numbers instead of measured pixels. It is the cheaper half of
the memory work and a stepping stone to the next item, since both need the same
address hunting.

**Hooking the game properly.** Injecting a library and walking Unreal's global
object array would expose the widget tree itself: real labels, real slider
values, real focus, and no OCR anywhere. This is the version worth aiming at.
What makes it a project rather than an afternoon, on this game specifically:

- Engine 4.7 dates from early 2015, so the UObject, FName and UProperty layouts
  have to be written by hand. The usual dumpers start at 4.12.
- The Steam DRM wrapper rules out static analysis, so the byte patterns that
  locate the global object array have to be found at runtime.
- Capcom customised the engine, so a correct object dump still has to be mapped
  onto their own interface classes.
- The debugging loop is the real cost. Neither of us can see the screen, and a
  wrong pointer crashes the game instead of printing a message.

## A caution about online play

Reading another process's memory, and injecting code into it, is what cheat
software does. Nothing here touches the game process; it only looks at the
screen. Once the memory work above arrives, keep it to offline modes such as
training, arcade and versus rather than ranked or casual matches.
