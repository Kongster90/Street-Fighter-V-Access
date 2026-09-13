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
Used where the screen cannot help, which today means character select, and now
able to read the whole interface's text, position and highlight exactly. See
"Reading the interface from memory" below; it is not yet wired into narration.

## What works

- Menu narration, automatic, as the cursor moves. Main menu including its icon
  column, the story, versus, challenges and settings submenus, Battle Settings,
  arcade path select, the Gallery submenus, all three training pause tabs.
- Settings rows report their value. Volume sliders report a level out of ten.
- Checklists say whether the entry is ticked, which is the whole point of the
  menu music screens.
- The voice language grid reads, naming the character and their language.
- Confirmation dialogs read the question and which answer is selected. This
  matters: one of them asks whether to close the game.
- Stage select reports the stage name. Time, temperature and weather come on
  the read key rather than unprompted; they do not affect play.
- Character select reports both fighters, costume and colour, read from memory,
  with all 46 characters named.
- Health, V-Trigger and Critical Art on a hotkey during a match.
- Speech through Prism to NVDA, falling back to Windows voices. Prism puts COM
  into a single-threaded apartment on whichever thread creates it, as Tolk did
  before it, so speech must stay confined to its own thread or screen capture
  breaks.

## What a session in play actually fixed

Worth reading before touching the narration, because every one of these read
correctly in the tests while being useless in the user's ears, and the tests
could not have found any of them.

**Reading a screen and noticing you moved are different jobs.** The loop
watched where the gold sits. Confirmation dialogs have no gold anywhere it
looked, so arrowing between Yes and No was silent: the dialog was read once on
arrival and never again. It now watches a coarse map of the dark areas, since
whatever is selected is dark on every screen in the game. See `change_key`.

**That map was split into rows twice over** and so had no horizontal resolution
at all. Every test pair differed vertically, so all of them passed while it was
broken. Two answers side by side on one row changed not a single cell of it.
The captures that catch this are in the suite now.

**Announcements interrupted each other into nonsense.** Stage select reads
correctly but its detail arrives in pieces across an animating screen: one
stage read "Time 4:30" and corrected itself to "14:30", another gained its
temperature, one produced four readings in a row. Each was announced and each
cut off the last, so what reached the user was a word of each and then nothing.
Announcements are compared on the thing being named, not on everything said
about it.

**A misreading is not a reading.** Sitting on one stage produced twelve
spellings in six seconds. They are refused now unless the name is a stage the
game contains, which the game's own word list settles. 263 of one session's 738
announcements would have been held back by that rule, and every one was
garbage.

**The count you announce has to mean something.** It counted every line of text
recognised anywhere, so idling on the main menu gave "Battle Settings, 10 of
12", then 9 of 11, then 11 of 13, with nothing touched. It counts the entry's
own column now.

**The spoken log is the best diagnostic here by a distance.** Everything
announced goes to `snapshots/spoken-log.txt` with timestamps. Every fault named
quickly this session was named from it; every one guessed at was wrong at least
once first. Ask what they heard and when, then read it.

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
properties at all, being wrappers around Scaleform's native value type. They do
declare functions, though, and those include the getters. See "The Scaleform
text is reachable after all" below before concluding anything from the missing
properties.

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
is by definition a string the game does not contain. It is also the authority
used to refuse a reading outright: a stage name that is not in it is not a
stage name.

**The character names come out of the game's own files.** They used to be
learned by hovering, which was slow and went wrong quietly.
`Content/Chara/DA_VTriggerNameAsset` pairs every character code with the
localisation hashes of its V-Trigger names, and those resolve against the
extracted string table, so `tools/names_from_data.py` recovers all 45 named
characters offline in seconds. Every name it produces appears verbatim in the
game's own strings. It found five codes the hovering had got wrong.

**Three names can never be learned by hovering**, and this is why the rule that
a code should read as the initials of its name must not be trusted alone.
Capcom's internal codes use the Japanese names: `VEG` is M. Bison, `BLR` is
Vega and `BSN` is Balrog. The initials rule rejects all three, so they were
refused forever. `live.SWAPPED_NAMES` records them.

**The highlight colour is RGB 255, 227, 140**, identical on every screen.


## The Scaleform text is reachable after all

This was recorded here as undone work on the grounds that the objects holding
the on-screen text declare no Unreal properties. That fact is true. The
conclusion drawn from it was wrong, and it cost the project a great deal of
pixel-reading it may not have needed.

Properties are not the only thing a class declares. `ScaleformUtilGFxValue`
declares fifty functions, and they include `GetText`, `GetString`,
`GetTextHTML`, `GetStringMember`, `GetMember`, `GetElement` and `GetArraySize`.
`ScaleformUtilGFxMenuPlayer` declares `OnChangeIndex` and `EI_OnChangeIndex`,
which fire as the selection moves, alongside `OnSelect`, `OnFocusIn` and
`OnPushListItem`. 689 functions across 123 interface classes, enumerated from
outside with `tools/` as it already stood, no injection involved.

So the menu text is behind getters rather than fields, and the event this tool
approximates by polling pixels is one the game already raises.

**Calling them needs code inside the process**, which reading memory from
outside cannot do. Two routes:

1. **UE4SS.** Tried hard, abandoned one symbol short, uninstalled. See below
   before spending any time on it.
2. **Find the text field by watching it change.** Done, and it worked better
   than planned: see the next section.

## Reading the interface from memory

`sfv_access/scaleform.py` reads every Scaleform text field in the game: exact
text, position on the 1920 by 1080 stage, the colour it is tinted, and whether
it is showing. A full read takes about a third of a second and needs neither
the game in front nor any injection. `tools/read_scaleform.py` prints it, and
with `--watch` speaks the highlighted entry as it moves and logs every screen
to `snapshots/scaleform-log.txt`. On the main menu it gave all eleven entries,
the description line, the profile panel and the Fight Money total, spelled
exactly, with the selected entry marked.

How it was found, since none of it came from documentation:

- **Search for the words, not the objects.** The menu words sit in memory only
  a handful of times each. The UTF-16 copies inside Scaleform's heap are
  paragraph buffers: text pointer, length counting the terminator, capacity.
- **Follow pointers up** from a paragraph to its StyledText, and from there to
  its DocView. Both have function tables at fixed places in the executable,
  `+0x34C8530` and `+0x34C8568`, so sweeping the heap for the DocView one finds
  every text field at once. Scaleform's pages are all small read-write regions,
  about 360 MB, and reading all of them takes a tenth of a second. Do the
  pattern matching in numpy; a Python loop over the bytes is what made the
  first full scans take twenty seconds.
- **The highlight was found by recording, not by reasoning.** A recorder read
  the heap each time the description line changed while the user moved through
  the menu, and kept the slots whose value followed the selection. Six floats
  per entry switched to 1.0, 0.89, 0.549 on the selected one. That is the gold
  RGB 255, 227, 140 as a colour multiplier, and 0.27 grey on the rest.
  Walking pointers outward from the text fields then found it: field, `+0x38`
  parent display object, `+0x48` render node, `+0x10` node data, `+0x50` the
  colour transform. The same node data holds the transform at `+0x10`, so the
  position comes free by composing up the parent chain.
- **The gold is stored as 0.89 and 0.549**, not 227/255 and 140/255. Searching
  for the exact fractions finds nothing.
- **Leftovers stay in the heap.** DocViews from closed dialogs keep their text
  until overwritten. They fail the walk to a render node, or come out
  detached, hidden or transparent, and `TextItem.shown` drops them.

**Not everything selectable is text.** The main menu's icon row, Options,
Gallery, Message Log, Login and Exit, lights no text when selected, so a
reader that only looks for gold goes silent there; the user caught this on
the first try. What does change is the description line at (110, 992), and
the banner, which switches to the icon's name as it is reached before going
back to rotating adverts. So a move is a change in the gold text or the
description, and a move with no gold is named by whatever short text changed
with it, falling back to the description. The adverts change neither, so
they are never read. `scaleform.selection_key` and `scaleform.landed_on`.

Known gaps. The clock, the date and a few title-screen fields have DocViews
whose owners do not sit at the usual distance, so they read as leftovers.
Only the main menu has been checked; other screens may highlight differently,
and the dialog and voice grid, which already need their own pixel readers, are
the likeliest to. Pixel-level things such as the health bars are untouched.

### Where UE4SS got to, and why it is not installed

Tried thoroughly and abandoned one symbol short. Nothing of it is installed;
the game folder holds only the executable. `tools/ue4ss_setup.py --remove`
puts it back to that state if it is ever reinstalled.

The experimental build gets remarkably far on a game five engine versions below
anything it targets. It loads, works out that this is 4.7 by itself, and finds
GMalloc, `FName::ToString`, `FName::FName`, `FUObjectHashTables::Get`,
`GNatives` and `GameEngineTick` unaided on a DRM-wrapped executable. Two things
it cannot find. `GUObjectArray` this project already knows, at module
`+0x3978720`, being the array head at `+0x3978730` less the 0x10 UE4SS's own
example subtracts, and supplying it works. The other is object construction.

**Object construction is the whole blocker.** UE4SS looks for
`StaticConstructObject_Internal`, a name 4.7 predates, via a call inside a class
this engine version does not have. Pointing it at inert padding crashes the
game with the fault address equal to the padding, which proves UE4SS calls the
function rather than merely hooking it.

Seven approaches failed to identify the real one, and they are recorded in the
commits so nobody repeats them: ranking functions that touch the object array
by callers finds small accessors; ranking by size finds vtable-reached
functions; Unreal's per-file log category names are not in this binary; call
sites filling four stack slots narrows 46 MB to two dozen but the two at the
right distance from the hash tables both crashed; a six-argument function with
allocation's exact shape has no eight-argument callers; and measuring arity by
disassembly founders on the same rock as the rest.

That rock is worth naming, because it defeated every attempt: **there is no
reliable way here to say where a function begins.** This binary does not pad
consistently between functions. Deriving starts from call targets is better and
is what `tools/walk_callers.py` does, but it still admits jump targets and
thunks, and frame sizes come out wrong often enough that arity counts cannot be
trusted. Getting further needs proper control flow recovery, not instruction
counting.

**One fact worth having before resuming:** UE4SS's hook ignores that function's
arguments entirely and only dereferences its return value as an object. So a
correct address really would work, and every crash meant wrong function rather
than a broken approach.

The tools are kept: `ue4ss_setup.py` installs and removes the configuration,
`ue4ss_signatures.py` writes the signature files, `ue4ss_log.py` reads the log,
and `walk_callers.py` and `find_construct_arity.py` are the two least bad
searches. `find_construct.py` is the first and worst of them.


## Traps

**There is one regression suite and it matters.** `tools/test_screens.py`
replays every captured screen through the real announcement code and checks the
entry that is actually highlighted. It is at 87 checks, and it now covers more
than which entry is named: what position it claims, whether it reports a value
or a level it should not, which description it picks, whether moving is
noticed, whether idling repeats itself, and the screens that must never be read
as dialogs. Several times a change
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

**The gold pulses, and a dim frame is not a mid-transition capture.** One
snapshot was recorded here for a long time as a menu still fading in, with no
gold anywhere and nothing to fix. Look at it: the screen is fully drawn and
General Story is plainly highlighted. The Gallery submenu settled it, giving
1367 gold pixels in one frame and 27 two seconds later without anything being
touched, while its dark bar held at 0.68 against 0.00 for every other row in
both. The lettering brightens and dims, and the dim phase falls outside the
colour match, so a tight gold test goes quiet at random on any screen. The dark
bar behind the entry does not move, and `selected_by_dark_bar` uses it once the
gold has failed. Be suspicious of any conclusion that a frame simply has no
highlight in it.

**Do not guess geometry.** Every layout question here was settled by capturing a
frame and measuring it. Guessing produced three wrong answers about which side
of the stage each fighter stands on before measuring produced the right one,
and the voice grid went the same way: its rows are 52 pixels apart, not the 45
first assumed, so every crop landed just above the names and recognition
returned nothing at all. Find the separator lines and measure them.

**Not every screen marks its choice the same way.** The gold on a dark bar is
the rule, not a law. The main menu's icon column marks its choice with a solid
gold tile and carries no text at all. A confirmation dialog uses a thin gold
outline round a dark fill, whose edges are too narrow to survive the band
builder. The voice language grid inverts it completely: the tile you are on is
the bright one and every other is dimmed. Each needed its own reader, and each
read as silence until it got one.

**Small text over artwork needs enlarging before it will read.** The names on
the voice grid tiles are about twelve pixels tall and return nothing at their
own size. Enlarged four times they read every time. `screens._read_bigger`.

**Match against the smallest vocabulary that can hold the answer.** Those tile
names, matched against the game's whole 21,922 string word list, came back as
"c BJ-LI" and "Q ALSInn". Matched against the 46 known characters they come
back as Chun-Li and Dhalsim, and genuine noise is refused. The right list beats
a better algorithm.

## Where it stands, and what to do next

The menus are in good shape and were tested in play. The user's own words after
the last pass were that it works "for the most part, maybe 95 per cent of the
time". What follows is roughly in order of value.

1. **Screens nobody has ever captured.** This is the highest value work and it
   is cheap. Everything verified so far came from a capture pass, and each new
   screen has taken minutes rather than hours. Not yet seen: the online modes,
   so Ranked, Casual, Battle Lounge and Extra Battle; story mode and its
   chapter select; survival difficulty; the trials and tutorial lists; the
   controller and button config page; the command list; the shop; the player
   profile; the post-match results screen.

   `tools/grab_screens.py` saves a frame each time the selection moves, so the
   user plays normally and you read what comes out. Ask them what they heard as
   well as reading the frames: every real bug this session lived in the gap
   between those two.

2. **Character select's third fighter.** It says "Other, KEN" alongside Player
   1 and Player 2. The game keeps a third preview model and the reader does not
   know what to call it. Small, and it needs no game in front since it reads
   from memory.

3. **Put the memory reader behind narration.** The reader works; nothing uses
   it yet. First run `tools/read_scaleform.py --watch` across the screens the
   user cares about and read `snapshots/scaleform-log.txt`, to learn which
   screens highlight with the gold tint and which do not. Then feed the same
   announcement code the pixel path uses, keeping to one code path as the
   trap below insists. The test suite replays pixels, so save the memory
   reading beside each capture and replay that too. Stage names, which the
   pixel reader gets wrong, should come out exact.

4. **Combat.** Deliberately deferred and completely unstarted. Speech cannot
   follow a round, so this wants continuous audio cues rather than words: pitch
   for health, stereo position for the distance between fighters, and speech
   kept for round transitions and a hotkey query. This is where the mod stops
   being a menu reader and becomes something to fight with. The HUD reader in
   `sfv_access/hud.py` already gives health and both meters.

5. **Move stage select to memory.** It works off the screen, so unlike
   character select it needs the game in front. There is almost certainly a
   stage code in memory to match, as with characters.

Deliberately not on this list: UE4SS, and finishing the character names. The
names are done, from the game's own files. UE4SS is written up above and is one
function short after seven approaches; do not restart it without reading that
section first.

## Working with this person

They are blind, they cannot see the screen for you, and the loop that works is
this. They play, the capture tool writes frames, you read the frames, you
change the code, they play again. Ask for what you need in one message rather
than several, since every round trip costs them a pass through the game.

Two things they have asked for that are easy to forget. Do not make them
navigate by screen position: they cannot know what is on the left or the right
until the mod tells them, and asking is the wrong way round. And do not read
out what does not affect play; the stage conditions were cut for exactly that
reason.

Push every change to `origin`, which is
github.com/Kongster90/Street-Fighter-V-Access. They asked for that as a
standing instruction rather than something to be asked about each time.

## Running things

Setup from a clean clone is in `SETUP.md`. Day to day:

```bash
.venv\Scripts\python.exe run.py
```

```bash
.venv\Scripts\python.exe tools\test_screens.py
```

The other suites are `selftest.py`, and `test_correction.py`, `test_learning.py`,
`test_memory.py` and `test_scaleform.py` under `tools/`. All six should pass
before anything is committed. `tools/show_bands.py <snapshot>` explains why a screen was read the
way it was, and is the first thing to reach for when one reads wrongly.

Memory reading does not need the game in front, and does not care if it is
minimised. Reading the screen does.
