# Handover

Written for whoever picks this up next. `README.md` explains how everything
works and why; this is the shorter version, plus the things that cost real time
to find out and would cost it again.

## Who this is for

The person you are working with is blind and uses NVDA. That shapes the work
more than anything else:

- They cannot check what is on screen for you. When something visual needs
  confirming, ask them to press Alt S, which writes a picture and a text
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
This is now how the mod narrates menus: exact text, and which entry is
selected, read out of Scaleform. See "Reading the interface from memory" below.
The pixel reader is the fallback, used while memory cannot be read or when the
user switches to it with F9. Character select reads from Scaleform too now;
`live.py`, which reads Unreal's objects, is only used by the pixel path and
Alt P.

**Start here if you are new.** Read "Who this is for", "What works", "Where it
stands, and what to do next" and "Working with this person", then the parts of
"Reading the interface from memory" that touch whatever screen you are asked
about. The long middle of this file is findings, each written where it was
learned; search it for a screen's name before investigating that screen.

## What works

From memory, tried in play by the user through the watch mode, which runs the
same narration the mod now does:

- The main menu, its icon row (Options, Gallery, Message Log, Login, Exit),
  and submenus, with setting values.
- Prompts: the Exit prompt, the browser prompt, and Training's return to menu
  prompt, reading the question once and then each answer.
- Grids: Favorite Character (by brightness), Favorite Stage (pictures, by the
  outline on the selected tile), including rows that scroll.
- The menu music list, saying whether each song is ticked, and on its Custom
  tab which songs are unavailable.
- Speed: a move is heard within about a tenth of a second.

In the mod itself, played by the user on 2026-09-13:

- Stage select, moving says the stage name and Alt R adds weather, time and
  temperature, including after backing out of character select, which took
  four rounds to fix (see "Stage select has nothing selected" and what
  follows it).
- Character select's costume panel (Costume, Color, V-Comment) and version
  panel (V-Skill, V-Trigger), which mark the row in gold like any menu, and
  moving through the roster, which says each fighter's name, with two
  players moving at once in Versus and against the CPU, and no cursor tags.
  When both sides' version panels open together, both gold rows are read in
  one sentence ("V-Skill. I - KIKO RENSEI. I - MYO-OKEN"); nobody has
  complained.
- The post-match Results Menu: Play Again, Return to Character/Stage Select,
  Return to Battle Settings and Return to Main Menu as the cursor moves. The
  result above it is summed up once its columns are complete, player one
  first, with wins, win streak and win ratio: "PLAYER 1 loses. Wins 5 to 2.
  Win streak 0 to 1. Win ratio 71.43 to 28.57 percent." Confirmed by the user
  over five matches in a row against the CPU on 2026-09-13, wins and losses,
  each summary new and Alt R repeating the current one. See "The result
  screen".

In the mod itself, played by the user on 2026-09-13 and 2026-09-14 (each has a
section of its own under "Reading the interface from memory"):

- Arcade: path select, each path with battles and best score, Alt R adding
  the path's story; the choice of next opponent after a stage ("CODY. REWARD.
  20320"); the VS screen before every fight, in Versus and Training too
  ("Opponent, CODY, V-Skill 2, V-Trigger 1. Frosty Boulevard."); the ending
  caption without its path code ("Ryu. The young challenger Ryu...").
- Challenges: the Trials notice with its one Close button; trials, the combo
  list read once as a sentence and again on every restart, in both Display
  Move Names and Display Commands, the command pictures put into words in
  the user's notation; Extra Battle's event panel, a short introduction on
  arriving at BEGIN BATTLE and the rest on Alt R.
- The pause menu's Command List, every section including those of two moves
  and of one, each move said as name and command.
- The Battle Lounge, Casual Match and Ranked Match menus read as ordinary
  menus, seen in the spoken log; nothing past their menus has been tried.
- Quitting with F10 now closes the console window.

Written and checked against the game or a recording, but not yet heard in
play: Arcade's final-stage opponent card ("FINAL STAGE. SAGAT. REWARD.
16620"); the Special Artwork credit after an ending; `SUMMARY_SETTLE`, which
stops a summary being said twice when part of it arrives late; the startup
challenge notices, which probably share the Trials notice's template.

From the screen, the older path, now the fallback:

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
- **Zero alpha on a node with empty bounds means nothing.** Arcade's choice
  of next opponent, two cards beside NEXT STAGE on its result screen, sat
  for minutes under a container whose colour multiplier had alpha 0 while
  the cards were plainly on screen, so the reader called them transparent
  and nothing was said. That container's approximate bounds (node data
  `+0x70`, two rectangles) were all zero; every really faded-out node kept
  its bounds. The same rule, checked against the stage grid, music list and
  Arcade recordings, also revealed the main menu's entries at the start of
  one recording and a music list row in another, and every one of those was
  showing in its screenshot. `_node` treats such an alpha as 1. The cards
  themselves are an ordinary gold menu: "CODY. REWARD. 20320".
- **A whole screen can be left behind looking shown.** After each Versus
  match the previous result screen stayed in memory complete, every node
  visible and opaque, and was read in place of the new one. What gives it
  away is the top of its chain: a subtree cut loose from its movie, whose top
  object has no parent and flags of 0 or 1, where a movie's root has 0x1801
  (0x1800 while hidden) and its own function table. In the stage grid and
  music list recordings all 6,105 texts on screen hung from such a root, so
  `TextItem.rooted` requires it (`MOVIE_ROOT_FLAGS`), and the "blind:" log
  groups the rest as "cut loose from its movie".

**Not everything selectable is text.** The main menu's icon row, Options,
Gallery, Message Log, Login and Exit, lights no text when selected, so a
reader that only looks for gold goes silent there; the user caught this on
the first try. What does change is the description line at (110, 992), and
the banner, which switches to the icon's name as it is reached before going
back to rotating adverts. So a move is a change in the gold text or the
description, and a move with no gold is named by whatever short text changed
with it, falling back to the description. The adverts change neither, so
they are never read. `scaleform.selection_key` and `scaleform.landed_on`.

**Do not find the owner by distance.** The first version took the text field
to start 0x2F0 before the DocView's listener, because on the main menu it
does. The Exit prompt, the header and the profile panel allocate the listener
separately, sometimes megabytes away, and every one of them read as a
leftover. The prompt's question and both answers were in memory the whole
time. The listener keeps a pointer to its field 0x98 before itself; follow
that. Comparing a working field's bytes against a failing one side by side is
what showed it: the same back pointers, pointing at different distances.

**A dialog's buttons are not tinted.** The selected one has a gold outline and
a dark fill, and its label stays plain. Recording the Exit prompt while the
user moved between Yes and No, with a screenshot per record to say which was
selected, showed it in the structure instead: the selected button has four
more children (6 against 2), and its label sits one level further down inside
them. `ScaleformText.mark_choices` compares buttons in a row on both counts,
only when nothing on screen is gold, and only for short labels; the rotating
banner's date line has an extra layer too, and without those limits it reads
as a selected button. Display objects keep a child array at `+0xD8`, sixteen
bytes an entry, with the count at `+0xE0`.

**Say what newly became selected, not everything selected.** The first dialog
reader refused to look for buttons whenever anything was gold, so the prompt
opened from Training's pause menu said nothing: Go to Main Menu stays gold
behind it. It also read the question only if the question was new at the
moment a button took the selection, and the question appears a beat before
the buttons, so the Exit prompt read only "No". A prompt's question is now
read whenever its group of buttons first appears, and a prompt closing says
nothing, where before the button hints coming back were read as a move.

**Almost all of a read is finding the text, not reading it.** A full read took
0.4 seconds: 0.1 listing memory regions and 0.3 sweeping 9,600 pages for
DocViews, against a hundredth for the text and placement of sixty fields.
The first fix swept only the few dozen pages that held text at the last full
sweep, 11 ms, and was wrong for prompts: each newly selected answer is drawn
in a new text field, often in a page that held none, so the answer arrived a
second late and the reader forgot the prompt in the gap and read its question
again. What works is the shape of Scaleform's blocks: whole 64 KB chunks plus
one 4 KB page, 0x11000, 0x21000, 0x31000. Every text field seen lives in one,
there are several hundred, about 70 MB, and `items(quick=True)` sweeps them in
about 40 ms. The address space walk that finds them runs on a background
thread once a second. The watch mode counts a prompt as open while its panel
shows anything, so the gap between answers does not reopen it.

**Grids mark the selection by brightness, not gold.** The Favorite Character
grid dims every name to 0.75 and leaves the selected one at 1.0, as the voice
language grid does, and a large label under the grid repeats the name.
`_mark_by_brightness` takes the one clearly brighter label in a group of three
or more, provided the rest mostly share a tint and its text box is the same
size as theirs. Text boxes record their width and height at DocView `+0x88`;
without that check a heading drawn brighter above dim entries would read as a
selection.

**Pictures are read through the display tree.** The Favorite Stage grid's
tiles hold no text: eighteen tiles of seven parts, the selected one with its
outline switched on and its picture at full brightness, every other picture at
0.4. `tools/record_scaleform.py` now keeps the whole display tree, walked down
through each object's child array (`+0xD8`, sixteen bytes an entry), and that
is what showed it. `find_grids` looks for containers of four or more tiles
with the same number of parts, on the background thread since the walk is too
slow for every read; `selected_tile` picks the one tile drawn differently and
brighter; `name_for_grid` names it by the nearest shown text in the tree, five
levels away for the stage label where the category tab is seven. Each read
checks only the known grids' tiles. Grids whose tiles carry text are left to
the brightness rule. Two locked stages are both named "???", so a selection
is compared by the tile as well as the text. The first recording of this
screen was useless because the recorder never refreshed its block list; see
`keep_pages_current`.

**A tick is a missing part, not a colour.** In the menu music list each row
has a tick box left of the song's name, holding a part with two bare shapes,
the box, and when ticked a third part, the tick. `tick_state` reads that for
the selected entry only, and only when two other rows in the list have a tick
box too. The first version of the rule matched the Sound Settings tabs and
volume rows, which are built the same way one level up; requiring the two bare
shapes inside is what separates them, and a replay of the 151-record recording
then read every song correctly and nothing else. Two recordings were needed:
the first recorder saved only when text changed, and ticking changes no text.
After Deselect All the game leaves the song you are on ticked.

**Unavailable entries are never gold.** The menu music list's Custom tab
shows songs that cannot be chosen in plain 0.6 grey, the same grey as Replay
Saved Status in the Training pause menu, and the cursor on them lights no text.
Each row has the same parts, and the second, the highlight bar, is visible only
on the row the cursor is on; `highlighted_row` compares visibility part by part
(not tint, since grey and ordinary names mix in one list) and is used only for
lists with no gold. Such an entry is said with "Unavailable" and without its
tick. The same session showed the tab name, "BGM LIST", and the popup title,
"Menu BGM List", read out on every scroll: rows empty for a moment while a
list scrolls, and the picture grid rule then took the list for a grid of
pictures and named it after the nearest text. Grids seen holding text are now
never treated as pictures.

**Stage select has nothing selected.** It shows one stage at a time, so memory
narration, which speaks when a selection moves, was silent there while the
pixel reader spoke with a lag. Memory read it perfectly all along: the stage
name, drawn twice, and conditions as label and value in one text, "Weather |
Clear", "Time | 10:30", "Temperature | 77°F" (a real degree sign; a console
shows it as a replacement character). `stage_on_offer` recognises the screen by
two or more of those conditions and takes the stage as the text nearest them in
the display tree, which leaves out the heading drawn above. Moving says the
name only; the read key adds the conditions, as the pixel path did.

**The background thread must never stall.** The same thread refreshes the
block list and walks the display tree for picture grids. Back on stage select
after character select, memory went silent for the rest of the session: its
text was in new blocks at higher addresses that the list never learned about,
while a fresh reader found it at once. The likely cause, not reproduced, is
the grid walk following a torn-down screen's pointers into garbage claiming
thousands of children. Three defences: `children` keeps only objects whose
parent pointer names the object asking, the walk stops after a quarter of a
second, and `Session.read` refreshes the block list itself if the background
one is more than four seconds old.

**It recurred with those defences in place**, so the cause above is not
proven, and a fresh reader started afterwards on the same screen still read it
perfectly. Two diagnostics are in now. If quick reads find nothing for two
seconds, `Session._check_empty` runs a full search; if that finds text, the
mod speaks from full searches until quick reads recover, and
`scaleform-log.txt` gets a line starting "quick read found nothing" saying how
old the block list was and which block sizes held the missed text. And if a
pass of the mod's narration loop takes over five seconds, `faulthandler`
writes every thread's stack to `snapshots/hang-log.txt`. After the user next
goes stage select, character select, back to stage select, read both. A
"quick read found nothing" line means the block list is at fault; a stack
dump means something hangs; neither, with silence, means the reading is fine
and the narrator is not speaking it.

**The next run ruled out both.** Back on stage select, quick and full reads
alike found nothing showing for 46 seconds, no hang was logged, and then the
text reappeared after the user moved between stages and narration carried on.
So for that time the text was either somewhere the reader does not look, or
found and judged not showing. `Session._start_wide_sweep` now tells which:
once per minute while blind it logs "blind: text found but not counted as
showing" with each text grouped by reason (not attached, parent hidden,
transparent, off the stage, placeholder), then sweeps every readable region
of any size or protection, about 20 seconds in the background, and logs any
DocViews showing text there, adding those regions to what is read. If stage
select's names turn up under "parent hidden" or "transparent", the visibility
rules are wrong for that screen; if under a wide sweep region, Scaleform had
put them outside its usual small pages.

**It was the visibility rule.** The next run logged "STAGE SELECT" under
"parent hidden" while blind, and the wide sweep found nothing elsewhere. Stage
select and character select are panels of one movie; each panel's container
has the visible bit, and on returning from character select stage select's
container kept its bit clear, sometimes for a minute, until the stage was
changed a few times. `_show_hidden_stage_select` counts text under the hidden
containers above stage select's conditions as showing, but only when nothing
at all is showing, which is never true while character select really is on
screen, and only for text hidden by those containers and nothing else, so
character select's leftovers under their own container stay hidden. It will
also read the chosen stage during the loading screen after character select,
which seemed harmless. The general lesson: the render node's visible bit can
lag behind the screen, so other screens may go blind the same way, and the
"blind:" log lines will say so.

**Reads slow as a session goes on.** Scaleform's blocks grew from 72 MB to
119 MB over an evening of screens, and a quick read from about 40 ms to about
110 ms, most of it the sweep and placing leftover text from closed screens.
Worth speeding up, for instance by remembering DocViews that failed to place.

**Templates hold placeholder text.** Every prompt carries a run of lower-case
w, and Training's loading screen runs of capital W. They are never drawn, but
their render state looks exactly like the question's, so they are recognised
by content: `is_placeholder`.

**The render node's visible bit only counts on parents.** It is clear on the
Exit prompt's question while the question is on screen, and dropping the
check entirely brought back a date line that never shows on the main menu,
which its container hides. Ignore the field's own bit; honour its parents'.

**Get ground truth into the recording.** Three recorders for the prompt caught
nothing useful, because each one decided in advance what to keep. The one that
worked kept every field whatever the reader thought of it, saved a frame with
each record, and stopped on a hotkey rather than guessing when the user was
done. Also: a file being written reports its old size in a directory listing
on Windows, so open it before concluding a recorder wrote nothing.

**How the mod uses it.** `sfv_access/memory_narration.py` holds what the watch
mode used to: `Narrator` decides read by read whether the screen moved and what
to say (with the clock passed in, so `test_scaleform.py` replays sequences
through it), and `Session` stays attached across the game closing and
reopening and writes `snapshots/scaleform-log.txt`, rotated past 5 MB. The
mod's `_watch_loop` asks the session each tick; if it returns a reading the
narrator speaks and the pixel tick is skipped, otherwise the pixel tick runs.
`Session.read` returns None until it has seen text at least once, so a game
update that moves the offsets falls back to the screen rather than going
silent. The read keys (R, D, A) and the snapshot key use the memory reading
when there is one; a snapshot saves it beside the frame as
`sfv-<stamp>-memory.txt`. Character select's `live.py` readout ("Player 1,
KEN, costume 0, colour 0") used to run on a thread of its own whenever nothing
in the memory reading was selected. It was removed on 2026-09-13: memory now
names the fighters, the costume panel names costume and colour, and the user
said player numbers on every move are more speech than needed. It still speaks
from the pixel path and on Alt P.

**Character select's roster marks nothing.** It is pictures, and memory shows
no sign of the cursor on it, but the fighter's name in the side panel follows
the cursor: the log went CODY, ZEKU, KOLIN, URIEN, BLANKA, LUCIA while nothing
was selected. `mark_fighters` recognises the screen by its "CHARACTER SELECT"
heading and takes every shown text that is a fighter's name, from
`character_names.json`, as selected. Arriving says both fighters, moving says
the one moved to, for either side; the user tried two players at once in
Versus and found it good.

**The cursor tags look like a prompt.** "1P", "2P" and "CPU" sit in a holder
beside the heading's, deeper and with more children. While exactly one tag
shows, the heading and the tag have the shape of a prompt's two buttons, and
`_mark_by_layers` chose the tag: "CPU. Unavailable" whenever player one's
blinking tag was off, "KOLIN. 1P" and bare "2P" in a two player match, and
"CAMMY. CPU" while picking the CPU's fighter. With two tags showing the holder
has two labels and the rule stays off, which is why it came and went with the
blinking. The first fix blamed the picture grid rule, which was a guess, and
skipped every rule but that one; play caught it within minutes. So
`mark_fighters` now clears every mark in the heading's movie that is not a
fighter's name, whichever rule made it, and leaves gold and other movies
alone. The replay of the session that caught it said only names.

**The result screen.** After a Versus match the big "AKIRA / WINS" banner
shows with the winner's quote, then over about ten seconds the result
columns, then the Results Menu, the first thing on the screen that is really
selected. Each side has a column: player ("PLAYER 1", "CPU"), "WIN" or "LOSE"
in three layers, and "Wins" and "Win Streak" each in a holder with its
number. "Win Ratio" and two percentages sit below both columns, and their
positions do not follow the columns: after player one won 1 to 0, "0.00%"
was drawn at x 632 and "100.00%" at 772. `result_summary` finds each side's
player and numbers by tree distance to that side's outcome, gives each
percentage to the side whose wins it agrees with (two decimals), leaves the
ratio out if neither way agrees, and says "PLAYER 1 loses. Wins 2 to 1. Win
streak 0 to 1. Win ratio 66.67 to 33.33 percent." once the columns are
complete. Player one comes first whoever won and wherever it stands: the
user did not like hearing "CPU wins" first. The user asked for win ratio and
streak there. While the screen arrives, one fading layer of "LOSE" beside
"CPU" had the shape of a prompt's chosen button, and was read out as the
result; `mark_results` clears non-gold marks in that movie, and the narrator
says nothing on that screen but the summary until the menu is selected.
Alt R repeats it. Four matches against the CPU, two won and one lost after
the first, gave ratios that agreed with the wins every time, player one's
percentage always drawn at x 772. Each match left the previous result screen
behind looking shown (see "A whole screen can be left behind"), which made
one summary stale and the next silent until `TextItem.rooted`. Draws, two
players and other modes are unseen.

**The VS screen.** Before each fight (Arcade, Versus and Training alike) one
panel shows both fighters' names, each side's V-Skill and V-TRIGGER as label
and value, the stage's name, and player one's level, LP, rank and title,
with nothing selected. `versus_summary` recognises it by V-Skill and
V-TRIGGER twice each, no gold and no CHARACTER SELECT or VERSION SELECT
heading (a scan of every logged screen found only VS screens that way), and
says, once, "Opponent, ABIGAIL, V-Skill 1, V-Trigger 1. Metro City Bay
Area." That wording is the user's: the opponent and version numbers, not
version names, and the stage. The opponent is the right-hand side, where
player one's opponent stood in Arcade, Versus and Training (only Arcade
shows a level on just one side, player one's, if that is ever needed to
tell). A version's number is the numeral before " - " in its value, which
shares a holder with its label. The stage is the one text sitting directly
in the panel, and must be a string in `strings.json`; at (644, 979) in all
three modes. Replaying the Arcade recording gave exactly that sentence. The
result screen and this share `screen_summary`, which the narrator and Alt R
use.

**Notices with one button.** Opening Trials in Challenges shows a notice,
"Some combos or move properties in Trials and Demonstrations may be
different from the current patched version of the game.", with one button,
Close. It is the Exit prompt's template: the message at 0.62 grey and half
alpha in a panel, a "wwww" placeholder, and a row holding one button of six
children with its label inside a layer (at alpha 0.15). `_mark_by_layers`
compares buttons, so with one it never looked and the notice was silent.
`_mark_lone_button` takes a label two levels under a six-child button, alone
in its row, with other text in the row's panel, as a chosen button; the
narrator then reads the panel first, as for any prompt opening. No shown
text in the three recordings has that shape. Read live: the message, then
"Close". Confirmed in play by the user on 2026-09-13. The startup challenge
notices ("Perform a combo 10 time(s)!" with a Close button) are probably the
same template and may read now too; unchecked.

**Trials.** A trial lists its combo's steps down the left (x 134, from y 340,
about 48 apart), each step drawn three times at one place: a top layer,
white while to do and (1, 0.8, 0, alpha 0.5) once landed, over two red
layers (1, 0.4, 0.3, alpha 0.5) that become (1, 0.6, 0.3) as a trial
completes. That red tint appeared nowhere else in either log. Nothing is
selected, but the layers rule marked some layers, and as steps lit and reset
the marks moved, so attempts read broken parts of the list; `_unique` also
dropped a repeated move ("SHUKUMYO" twice in one combo). `trial_summary`
says the list once, steps joined by commas without numbers ("Standing Hard
Punch (COUNTER), SHUKUMYO, ..."), through `screen_summary`, and `mark_trial` clears the
marks. At the user's request it is said again on a restart
(`trial_restarted`): "Restart Battle" appears at (95, 900) each time the
user restarts, the steps reset to white with it, and Try Again leaving the
pause menu shows no notice, so a highlighted Try Again vanishing counts too
(closing the pause menu with Try Again highlighted will also reread). A
replay of the 23:15 to 23:21 session gave one reread per notice. Display
Commands draws most inputs as button pictures with no text: "(STANDING) M
H" and steps made only of pictures are absent; that is now solved, see the
next section. Confirmed in play on 2026-09-14 in both displays.

**Pictures inside text are named.** The command display's pictures are
inline images in the text field, each in place of a space character, not
separate display objects. A paragraph (the pointer in StyledText's array)
holds its chars at +0x00, length at +0x08, and format runs at +0x20 with
their count at +0x28: start, length and TextFormat pointer, 0x18 bytes each.
A run's TextFormat has an image description at +0x30 (null for plain text);
the description's URL is a GFx String at +0x50, a pointer tagged in its low
two bits to data holding the length (top bit a flag) at +0x00 and ASCII
chars from +0x0C: "img:///Game/CommonAsset/TaggedImages/punch_h.punch_h".
Matched against a full-resolution screenshot of Zeku's first trial on
2026-09-13: cmd_2 down arrow, cmd_236 quarter circle forward, cmd_214
quarter circle back (numpad notation, facing right), punch and kick the
white icons (any strength; two in a row is two buttons), punch_m and
punch_h the yellow and red strength icons, plus the plus sign, next the
arrow meaning then. `field_text` puts known ones into words through
`input_words` and `describe_inputs`, so every reader sees "down, down plus
punch punch" and "medium punch, heavy punch"; the strength letter printed
before a coloured button is dropped. The notation is the user's own
example, given on 2026-09-14: "heavy punch, quarter circle forward plus
kick kick, down, down plus heavy punch". No comma before plus, a plain
button pressed twice is said twice, a trial's steps are joined by commas
without numbers, the arrow meaning then is only a comma, and "(STANDING)"
is dropped (a button with no direction before it is standing already, the
user's reasoning). "(CROUCH)" is said "down plus" and "(JUMP)" "jump", also
the user's choice (`STANCE_WORDS`); the Zeku trial logged as "(JUMP) H",
"(CROUCH) H", " M", " H" reads "jump heavy punch, down plus heavy punch,
medium punch, heavy punch". Other cmd_ digits are
spelled as directions and 41236/63214 named; kick_m and kick_h, guessed by
pattern, read correctly in play; punch_l and kick_l are still unseen. The
user confirmed the whole trial reading in play on 2026-09-14, rereads on
restart included: "jump heavy kick, down plus heavy punch, quarter circle
back plus medium kick, ...". punch_l then read correctly in the Command List
("light punch, medium punch"); kick_l is the only button still unseen.
Unknown picture names stay spaces and are logged once each as "pictures in
text with no words: [...]", which is the list to extend; so far only
button_x, button_a and button_y, controller prompts beside "Fighter Profile"
and the Command List's own key hints, all rightly silent. Costs about 4 ms
on a 135 ms read. The Command List uses the same pictures and reads with
them, confirmed in play on 2026-09-14.

**The Command List's short sections.** The pause menu's Command List reads
each move as its name and command from the pictures ("BUSHIN GRAM - BAN.
forward, down, down forward plus kick"), the row marked by `highlighted_row`:
each move's row has sixteen parts and the third is shown only on the cursor's
row. That rule wanted four rows, so a section of two, such as Normal Throw
(TSURIGANE OTOSHI, MIKOSHI), was silent. Lists of two or three rows are now
read too, but only when exactly one part differs in visibility across the
rows and it is shown on exactly one; the three recordings give no marks
under that rule. Checked live on Normal Throw that MIKOSHI's row is the one
marked; a screenshot to confirm the cursor was on it could not be taken, the
game being behind. A section of one move (Unique Attacks: NOUTEN WARI) has
nothing to compare, so `_mark_single_move` takes it: only while the note "All
commands assume the character is facing right." shows and nothing in that
movie is chosen, a list whose text all sits in one row of eight parts or
more, each part a background and a holder, with no other such row beside
it. Read live: "NOUTEN WARI. forward plus heavy punch". A trial's step
layers behind the pause menu are still marked at that point in the pass,
hence the check within the note's movie only. Every section, short or
single, was confirmed in play on 2026-09-14. Also buttons drawn side by side
are pressed together: the same button is said twice ("punch punch") and
different ones get plus between them ("heavy punch plus heavy kick", the
throw "light punch plus light kick"), from the user's example "KAGEROU.
heavy punch, heavy punch, medium punch plus medium kick"; commas stay
between directions and at the arrow meaning then. The Icon Info page is a
legend of icons that are not text pictures, so only its descriptions show
("Hold the down button", "Hold the left button", "Without directional
button", "A move corresponding to each V-Skill.") and one is taken for a
selection; not handled, and the user has not asked.

Charge inputs are `cmd_4c` and `cmd_2c` (a direction's digits then "c"):
Guile's Sonic Boom `<cmd_4c><cmd_6><plus><punch>` read "forward plus punch"
and Somersault Kick "up plus kick" until `input_words` said them as "hold
back" and "hold down", the Icon Info page's own word, giving "hold back,
forward plus punch". The user reported it on 2026-09-14 and is happy with
"hold". The same day Zangief's Screw Pile Driver and Borscht Dynamite read
without their `cmd_0`, the circling arrow, now "full circle": "(NEAR
OPPONENT) full circle plus punch". The pak index lists every tagged image
(97); the command pictures are cmd_0, 1, 12369, 1c, 2, 214, 236, 2c, 3, 319,
4, 41236, 421, 46, 4c, 5, 6, 623, 63214, 7, 8, 9, and all have words now
(the longer ones as directions in order). Other tagged images that could
turn up in commands and have no words yet: hold, p_hold, k_hold, release,
p_release, k_release, ex, ex2, ex3, v, v2, v3, v_trigger, next_ar, middot.
`rapid` was seen in E. Honda's Hundred Hand Slap, `<punch><rapid>`, which read
"punch"; it is now in `MANNER_WORDS`, joined to the button by a space: "punch
rapidly". Their joining in `describe_inputs` would need thought (a hold then a
release of one button is not "plus"), so they wait until seen.

**Extra Battle's event panel.** Entering Extra Battle in Challenges puts the
cursor on BEGIN BATTLE beside one event's panel, and only BEGIN BATTLE was
said. The panel (recognised by "PARTICIPATION FEE (FM)" and "NO. OF
REMAINING PLAYS", their common ancestor being the panel) holds the title at
the top, label and value rows on one line each (START, DEADLINE with "(19:55
remaining)", REWARD whose reward is a picture, the fee, remaining plays), a
description whose paragraphs start with a heading line ("Difficulty" /
"Easy", "Clear Reward" / "\"Forest\" Gem, 100 EXP"), and "Clear Conditions:
Win the battle!". `extra_battle_details` turns it into sentences; the
narrator says the brief form (title, deadline, fee, difficulty, clear
conditions, the deadline and fee added at the user's request) once before
BEGIN BATTLE on arriving, and Alt R says all of it. Confirmed in play by
the user on 2026-09-14.

**Starting the game.** Recorded on 2026-09-14 with a quiet recorder beside
the mod (`snapshots/scaleform-startup`, from the Capcom title onward): black,
the title with "Applying Title Update Ver.07.011..." and then "Connecting to
server..." at (960, 886), each for under a second, the title again, "Logging
into the server..." for about eight seconds, a loading screen, then the main
menu under the Current Missions notice. The title's "Press any button" was
never a text field in memory (the only other text was the copyright line,
judged hidden while drawn), so it cannot be read the usual way. It does not
matter: the user says the title carries on to the main menu by itself, with
nothing to press until the missions notice. The first read of a new game said
" Sub Menu", a button hint shown alone on a black frame. Status lines went
unsaid because nothing was selected and they are not the description line,
so the selection key never changed; `status_line` makes a screen whose one
text ends "..." (at most 60 characters) a summary through `screen_summary`,
said once it holds for `SUMMARY_SETTLE`, so only the login line is heard. No
other logged screen had one text ending that way.

**Notices after logging in.** Two follow each other over the main menu,
the same template: a title, one scrolling text of entries separated by
blank lines, and one Close. Current Missions entries are a line of what to
do ("Perform a cross-up 10 time(s)!") and "DEADLINE:Sep 15, 2026, 9:00:00
PM (Days left: 1) Reward: 50" with an `icon_FM` picture before the amount.
Currently Available Extra Battle (not completed) entries are a title, a
detail line ("Costume: RASHID : Airman", after an entitlement picture),
"DEADLINE:Sep 14, 2026, 9:00:00 PM ( 4:50 remaining)" and "Reward: "Forest"
Gem, 100 EXP", each reward after a picture of itself; the time remaining is
hours and minutes as the notice was built at startup. Close is plain white
with no chosen-button layers, and the title field is at zero alpha (its own
node only, with bounds) while drawn; `_show_notice_title` counts it as
showing while a notice list shows. The main menu's cursor starts on the
advert banner behind, which `_mark_highlighted_rows` marks, so the first
notice said "UPGRADE KIT AVAILABLE NOW" and the second the same. `mark_notice`
finds a text with `NOTICE_DEADLINE` lines and a Close sharing a panel within
four levels, marks Close, and clears non-gold marks in other movies.
`notice_details` gives the title and each entry's name and detail lines,
counts made plain ("10 times", "1 match"), and for Alt R the time left in
words, the deadline with the month in full and no seconds, and the reward.
The narrator's introduction before a button, Extra Battle's until now,
takes it too, and because the second notice's Close is where the first's
was, a new list with Close still selected is introduced without a move
(notices only: Extra Battle's brief carries a live time remaining).
`ICON_WORDS` says the Fight Money picture after its amount everywhere
("Reward: 50 Fight Money"); `SILENT_PICTURES` stops pictures that sit beside
their own words, and the controller hints, being logged as wanting words.
The missions notice was heard correctly on 2026-09-14. The Extra Battle one
listed "[Quick & Immovable] Get the Crossover Costume! [2]" once per
costume, and at the user's request the brief now names each entry once with
whose costumes it offers (`NOTICE_COSTUME`), and every notice's brief ends
"Press Alt R for more information." before Close: "Currently Available
Extra Battle (not completed). [Quick & Immovable] Get the Crossover
Costume! [2]. For RASHID, BALROG, SAGAT and MENAT. Get Your Hands on Fortune
Tickets! Press Alt R for more information. Close". Checked live, not yet
heard. On the main menu the
banner advert was said every fifteen seconds while idle on it in an earlier
session ("Aug 31, 2026 - Sep 30, 2026. UPGRADE KIT AVAILABLE NOW", 13:45:31
to 13:46:36 on 2026-09-14); not yet looked into.

**Reattaching after the game restarts picked the launcher.** On 2026-09-14
the user quit the game with the mod running and launched it again; memory
narration logged nothing more and the pixel reader spoke the change ticket
prompt ("... used in the Yes is selected."). `find_pid` took a name match when
nothing matched `Binaries\Win64`, and the launcher in the install root starts
a moment before the game and stays running, so the session's retry attached
to it and read nothing while `_still_there` kept passing. `scaleform.attach`
and `live` now pass `require_path=True`; `game.is_running` keeps the fallback,
since the launcher running does mean the game is starting.

**The Fighter ID and Home change.** Bought as a ticket in the shop's Other
Services, it starts at the next login: after "Logging into the server..." a
prompt (message and Yes/No, the Exit prompt's template) read correctly once
the reattach fix was in. Yes led to "Please select your Home." with a Next
button, then the Home screen: an "All" tab with LB and RB beside it, and a
grid of flags with no text, forty tiles of three parts in view, in ISO 3166
three letter order with the game's logo (OTH) first. The picture grid rule
found the grid and named it after the nearest text, so moving said "All"
once and nothing more. `tile_country` reads a tile's code through its script
object (tile +0x150, then +0xE0 to a string node whose first word points at
the characters); all forty matched the screenshot. The flag loaders also
point at "img:///Game/CommonAsset/CountryFlags/AFG.AFG" and the like, but one
tile ahead and with gaps, which a watcher comparing screenshots with codes
showed. The game has no country names in its text, so `country_names` asks
Windows (`EnumSystemGeoID`, `GetGeoInfoW` for GEO_ISO3 and GEO_FRIENDLYNAME),
"Bahamas, The" becomes "The Bahamas" and OTH "Other". `_mark_picture_grids`
adds a selected text for the tile, named by country, when it and two other
tiles resolve to codes. At the user's request the tab (the grid's nearest
text, which the picture rule used to take) is marked selected too, so
switching with LB or RB says it before the country, "Asia. Afghanistan", and
the country's `slot` is tied to the tab as well as the tile so the flag
landed on is named even when it is the same one. The user heard the tabs
All, Asia, Africa, South America and Oceania with their countries. North
America was silent: its grid holds Canada and the United States (three parts
each) and six empty places of one part, too few alike for `grid_tiles`. While
the description line is `HOME_PROMPT` (`on_home_screen`), `_tiles_of` lets a
container count as a grid by its flag tiles alone, and `_flag_under_cursor`
takes the one flag with every part shown (the outline among them) when
`selected_tile` cannot decide. Heard in play on 2026-09-14 ("North America.
Canada", "United States"), and the user chose their Home with it. Next came
"Please choose a Fighter ID." with its notes and Next, read as a prompt.
There the user pointed out, not for the first time, that Alt R said only
"Next": `prompt_message` gives a prompt's panel texts besides its buttons,
as the opening does, and Alt R now says them before the answer.

Next is the Fighter ID entry, and typing was silent. "Please enter your
Fighter ID." in white at (598, 409); under it at (598, 482) a 0.27 grey field
holding what is typed (the user typed "Kon" and it was there), both three
levels under one panel; the description line "Please enter text using the
keyboard. <button_back>/ESCAPE Key: Cancel entry and close window". The
field is empty, so not shown, until something is typed. `text_entry` finds
the prompt (starting "Please enter" or "Please input") and the text below it
in the same panel while that description shows; the narrator says the
prompt and the instructions on arriving, then `typed_words` for each change
("capital K", "o", "o deleted"), clearing its repeat guard so a letter typed
twice is said twice; Alt R says the prompt and `entry_value_words`, "Kon, 3
characters: capital K, o, n". Capitals are said, since a name heard as a word
does not say how it is written. The Battle Lounge password uses the same
description line over the lounge settings; its field is not known and
`text_entry` does not match it. Heard in play on 2026-09-14: the user typed
their new ID letter by letter with it. The confirmation after it, a prompt
with Yes, No and Do not change, read as any prompt; its message begins with
the chosen Home's flag as a picture named by its code ("USA") before the ID,
which `_with_pictures` now says as the country: "United States, Kongster. Are
you sure you want to proceed using this information? ...". The game checks
the ID after Yes. A four letter ID gave the "Please choose a Fighter ID."
prompt again with '"Kong" doesn't meet the minimum character requirement...'
and Next; it was said in full, then three seconds in Next flickered between
its chosen drawing (layer at 1161, 671) and a plain one (960, 690), and
"Next" cut the message off. `landed_on` no longer names a chosen button that
is alone in a group the narrator already knows is open. The user then
registered a six letter ID through the whole flow by ear, ending on
"United States, Konggster. Registration complete. Welcome to the world of
STREET FIGHTER V! Next" (2026-09-14). Still to come in that flow: the Fighter ID entry
and the confirmation.

**Training's attack data.** Asked for on 2026-09-14: combo damage, count and
frame advantage. With Attack Data on, player 1's labels "DAMAGE\nSTUN\nCOMBO\n
DAMAGE SCALING\nATTACK LEVEL" sit at (98, 195), their values in one text at
(338, 195), "57(+27)\n133(+63)\n2\n90%\nHIGH", then "Frame" (497) and "7 (-4)"
(621); the other side's at 1152, 1457 and 1696. A watcher logging every
change at thirty reads a second during the user's play showed the values
change the moment a hit or block lands (a block gives combo 0, chip damage
included), the frame number counts down at sixty a second through each
side's action, the bracket is the frame advantage mirrored between sides,
and the other side's frame text goes away when nothing runs. `attack_data`
parses player 1's; the narrator arms when the values change, or when the
other side's counter starts while player 1's runs (the same attack twice
leaves the values alone), and says `attack_summary` once both counters have
stood at 0 for `ATTACK_SETTLE` (0.25 s): "2 hits, 57 damage, plus 9",
"Blocked, minus 2". A combo of 0 with damage and plus 52 turned up once (a
throw or knockdown), so "Blocked" needs the advantage within 15. Alt R with
nothing selected gives `attack_details`. Replaying the logged session gave
one sentence per attack, 76 in all.

In play the user heard long combos said too soon: "3 hits", "5 hits", "6
hits", "7 hits", "8 hits" through one. Through special moves and long
combos both frame texts go away entirely, and a missing counter had been
taken for one at rest. Now only player 1's counter showing 0 (with the other
side's at 0 or gone) counts, the values must also have held still
`ATTACK_SETTLE`, and when player 1's frame text stays away the values holding
still `ATTACK_SETTLE_UNCOUNTED` (2 s) will do. In the log the frame text came
back about a second after a long combo's last hit, so that combo is now "8
hits, 275 damage, minus 10" once; a replay of the whole session from the
screen log gave one sentence per attack and none mid-combo.

The user then said the frame advantage was read wrong, and it was: every
sign reversed. Player 1's attack values are the left panel's, but player 1's
frame readout is the right one (x 1696): in the first log only the right
counter ran while player 1 moved before any hit, and a light attack's hit
(30 damage) left "(-4)" on the left and "(+4)" on the right. `attack_data`
now takes `counter` and `advantage` from the right readout. The replay then
gives light hits plus 4, blocked lights plus 2 or 3, knockdown enders plus
22 and plus 27. Whether the readouts swap when player 1 is on the right side
(Side Setting) is unknown. The user confirmed the signs in play.

Attacks that miss: the attack values do not change and the bracket keeps the
last advantage; only player 1's counter runs, from the action's total frames
down to 0 ("13 (+3)", "7", "1" in the first log). There is no startup,
active or recovery split and no advantage to give. A quick read every 30 to
100 ms sees the first value two to six frames late, so a total said from it
would be short by that much; not built, the user asked whether it exists.

**The game's short messages.** Pressing X on Special in the shop seemed to do
nothing but make a sound: the game showed "Your selection is\ncurrently
unavailable." at (95, 900) for a few seconds, selecting nothing, so nothing
was said. Every text ever logged at exactly that place is such a message
("[SFI Ryu] has been added to the Gallery.", "ZEKU: \nReceived 5000 EXP.",
"Perform a cross-up 10 time(s)! has begun! \nCheck it out from "Challenge"
>> "Missions."", a locked story setting's "currently unavailable") or a
trial's "Restart Battle", which the trial rule answers by rereading the
combo and `TOAST_UNSAID` leaves out. `scaleform.toast` finds one; the
narrator adds it after whatever else is said, once while it shows, and
again if the same one returns after a second's absence (`GROUP_MEMORY`),
clearing its repeat guard so pressing X on Special twice says it twice.
None of the four recordings has one. Confirmed in play by the user on
2026-09-14 on the shop's Special. The Extra Battle notice's shorter brief was
heard and approved the same day.

**The shop's item lists.** A bought item's row is its name at x 491 and
"Purchased" at x 1144, both in the 0.6 grey, both marked by the highlight
bar rule, so it read "Stage: Ring of Pride. Unavailable. Purchased.
Unavailable", or without "Purchased" when scrolling brought another bought
row's label to the same place (a move says only what is newly selected, by
position and text). An unbought row is its name in the usual 0.27 grey
alone; choosing one opens a gold "Buy on Steam". At the user's request
`mark_purchased` unmarks the label and gives the name the `note` "Already
purchased", which `landed_on` and `selection_phrase` say in place of
Unavailable: "Stage: Ring of Pride. Already purchased". Confirmed in play by
the user on 2026-09-14 in Stages and the other categories.

**Arcade path select.** The paths (STREET FIGHTER I to V, each row with
NO. OF BATTLES and BEST SCORE, the one you are on gold, a description to the
right) read from the screen before memory took over, and never from memory:
the user noticed on 2026-09-13. The top node of their whole movie (the
object under the root, flags 0x1801) holds alpha zero with bounds while it is
on screen. Nothing in its node data told it from other movies' tops, and a
menu left loaded behind another screen might be hidden the same way (a
78-text movie showed nothing behind the Versus results for reasons not
recorded), so `_show_path_select` ignores that alpha only while the
description line "Please select a path..." shows. Read live: "STREET FIGHTER
I. NO. OF BATTLES: 4. BEST SCORE 123220". Confirmed in play by the user on
2026-09-13, all six paths, stories included. Alt R there adds
the path's story, its lines said as sentences (`path_story`: "Launched in
August 1987, ... Story Chronological Order: 1. A young Ryu and Ken..."), in
place of the description line, at the user's request. If another screen
turns out silent with "transparent" texts and a zero-alpha movie top, this
is the pattern; the evidence for a general rule would be a screenshot of a
movie hidden that way that is really off screen, or none after several.

**Arcade endings.** A run ends on artwork with a caption: a title naming the
path and fighter ("SFI Ryu" at (160, 780)) and a paragraph of story at
(220, 868), in one panel, and nothing else shown, which the user clicks
through. Read live on 2026-09-13, `ending_summary` says "Ryu. The young
challenger Ryu stands before..." once, through `screen_summary`. The title's
path game (SFI, SFII, SFIII, SFIV, SFV) is dropped at the user's request
(`ENDING_PATH`). It needs
exactly two shown texts, the shorter (40 characters at most) above the
longer (60 at least), within four steps in the tree, and the longer not the
menu's description line; a scan of every logged screen found only endings
and one main menu moment ("Top User" and the description) of that size.
Both endings logged so far had one caption page, then path select. The
ending itself was heard in play. After it came a page crediting an unlocked
picture, "Special Artwork: BENGUS" alone at (160, 911); the game has 57
strings of that kind ("Special Artwork: <artist>", "SF Legacy: ...
Artwork"), so a single shown text containing "Artwork" that is one of the
game's strings is read too. Checked live, not yet heard.

Known gaps. The clock sits one object further down and is not resolved.
Screens other than Versus and Training may head their character select
differently, and a prompt drawn inside character select's own movie, if there
is one, would lose its choice to `mark_fighters`. Not yet heard from memory in
play: the voice language grid (the brightness rule may cover it; its EN and
JA badges are pictures and are not read), and anything in a match.
Pixel-level things such as the health bars are untouched.

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
reintroduce a second one. The same goes for memory narration: `Narrator` in
`memory_narration.py` is the only place it is decided, and both the mod and
`tools/read_scaleform.py --watch` call it. A fix tried in the watch mode is a
fix in the mod.

**The selection rules run in an order, and later ones undo earlier ones.**
`ScaleformText.mark_choices` runs the generic rules first (prompt buttons by
layers, brightness, highlight bars, picture grids, the lone button, the
single Command List move) and then the screen rules that clear false marks
(`mark_fighters`, `mark_results`, `mark_versus`, `mark_trial`). A rule that
asks "is anything else selected?" in between sees marks that are about to be
cleared: the single-move rule was refused on its first try by a trial's step
layers still marked behind the pause menu. Ask within the screen's own movie
(`chain[-1]`), and put new rules where their questions get true answers.

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

The pixel-read menus were judged "for the most part, maybe 95 per cent of the
time" by the user. The memory reader then took over narration, and every screen
the user tried with it in the watch mode ended with "it works as it should".
The user finds memory reading better and wants it everywhere; the pixel reader
is kept as the fallback and for the gauges.
What follows is roughly in order of value.

0. **Keep going screen by screen, as the user finds them.** The user's
   stated goal is memory reading everywhere. The way the 2026-09-13/14
   session went, and the way to continue: the user plays, finds a screen that
   is silent or reads wrongly, and says so while still on it. Read the live
   screen from memory at once (the snippets under "How this session found
   things" below), and the tail of `snapshots/spoken-log.txt` and
   `scaleform-log.txt`. Nearly every silent screen was one of four things:
   nothing on it selected (give it a summary through `screen_summary`, or an
   introduction as Extra Battle has); a rule mistaking layers or tags for a
   selection (clear marks in that screen's movie, as `mark_fighters`,
   `mark_results`, `mark_trial` do); text judged hidden that is on screen (a
   zero alpha, a movie top, a cut-loose copy: see those sections); or the
   selection marked by a shape no rule knew (a lone button, a short list, a
   single row). Scope any new rule to its screen by a text only that screen
   shows, check it against the three recordings for false marks, add a test
   built from what memory showed, and say the result in the user's words.

   Heard and confirmed this session: see "What works". Waiting to be heard:
   Arcade's final-stage opponent card, the Special Artwork credit,
   `SUMMARY_SETTLE`, and the startup challenge notices. Not yet tried at all:
   character select in Training and Arcade (if one does not read, look for
   its heading in the log; `CHARACTER_SELECT_HEADING` is the only thing
   recognising the screen), the result screen with two players, a draw, or
   Survival, the voice language grid, and anything online past its menus.
   Still worth asking the user: whether character select's costume and
   version panels should say whose they are, since both sides' read the
   same; whether Icon Info in the Command List should be read.

   The VS sentence was once said twice, without and then with the stage,
   which arrived a read late; `SUMMARY_SETTLE` now waits for a summary to
   hold still for 0.4 s.

   Before the final stage Arcade's result screen shows FINAL STAGE where
   NEXT STAGE was, with one opponent and no choice, and nothing was said
   about him. `Session._note_arcade_offer` (still in: "arcade offer (...)"
   in `scaleform-log.txt`, twice per result screen with either marker, each
   hidden fighter's name with its reason and the flag word / raw alpha of
   every object above it, "e" for empty bounds) caught it on the next run:
   SAGAT, REWARD, 16620 in gold in the second card's slot, under the usual
   zero-alpha empty-bounds container and also a card object at alpha zero
   with bounds, for the half minute the screen stayed. Whether a sighted
   player sees that card is unknown; no screenshot exists. The name is the
   game's own final opponent, so `_show_final_opponent` counts gold fighter
   cards hidden only by alpha, beside a shown FINAL STAGE, as showing, and
   the narrator holds selections made while a summary settles and says them
   after it: "FINAL STAGE. SAGAT. REWARD. 16620". Not yet heard. The fight's
   own bar also says FINAL STAGE, hence the result-screen checks. The mod stopped by
   itself that evening at 20:33 on Arcade's result screen with nothing in
   either log; if it happens again, ask whether they closed it, and look for
   a console window's last lines. `scaleform-arcade-choice` is a 541-record
   recording of that screen, the stage card, the VS screen and a fight.

   The result screen summary works against the CPU. Unheard: two players,
   a draw, and other modes' result screens (Arcade, Survival). If the ratio
   is missing from what is said while two percentages show in the log, they
   did not agree with the wins, and the log's numbers will say what they
   mean instead. The "blind:" log lines also list "YOU WIN", "YOU LOSE",
   "GAME OVER" and "DRAW GAME" under hidden panels, which look like other
   modes' result banners.

   Starting the mod with the game, asked for on 2026-09-14, is written: see
   "Starting with the game" under "Running things". The user then put it on
   hold, along with sharing the mod with friends, until every screen in the
   game speaks properly; do not raise either until then. The launch options
   are not set in Steam, so the mod is started by hand.

1. **Screens nobody has tried.** Not yet seen from memory: online matches
   past their menus (Ranked, Casual, Battle Lounge rooms); story mode and its
   chapter select; Survival; the Demonstrations and tutorial lists beyond
   their menus; the controller and button config page; the shop; the player
   profile; the Gallery's contents. Each screen this session took minutes to
   an hour once the user was on it. `tools/record_scaleform.py <name>` is the
   tool when a selection's marking is unknown and the user needs to move
   through it; plain live reads were enough for everything else this session.

   `tools/grab_screens.py` saves a frame each time the selection moves, so the
   user plays normally and you read what comes out. Ask them what they heard as
   well as reading the frames: every real bug this session lived in the gap
   between those two.

2. **Character select's third fighter.** It says "Other, KEN" alongside Player
   1 and Player 2. The game keeps a third preview model and the reader does not
   know what to call it. Small, and it needs no game in front since it reads
   from memory.

3. **A replay suite for memory readings.** `test_screens.py` replays pixels;
   memory narration is tested only against hand-built fakes of memory. The
   recordings in `snapshots/scaleform-*/records.jsonl` hold every text field
   and the display tree, and replaying them through `ScaleformText`'s rules and
   `Narrator` would catch a change that breaks one screen while fixing
   another, as `test_screens.py` does for pixels. The analysis in this session
   already replayed several of them by hand.

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

For memory narration the loop was: they play with narration on and say what
sounded wrong, you read `snapshots/scaleform-log.txt`, which has every screen
and everything said. When a screen marks its selection in a way nobody knows
yet, `tools/record_scaleform.py <name>` keeps everything plus a screenshot per
record until F10; ask them to hold each state for a few seconds and
to do the thing in question (tick, untick, move a row) more than once. Only
one of the watch mode, the recorder and the mod can hold the keys at a time.

Shortcuts are plain Alt plus a key, at their request: fewer keys to press, and
Windows claims some Control Alt combinations. They chose F10 for quit (and for
stopping the watch mode and recorder) and F9 for switching between memory and
the screen, and are happy with F keys generally.
Before adding a key, check it registers (every current one was free), and
remember a global hotkey is taken from every program while the mod runs.

Two things they have asked for that are easy to forget. Do not make them
navigate by screen position: they cannot know what is on the left or the right
until the mod tells them, and asking is the wrong way round. And do not read
out what does not affect play; the stage conditions were cut for exactly that
reason.

Push every change to `origin`, which is
github.com/Kongster90/Street-Fighter-V-Access. They asked for that as a
standing instruction rather than something to be asked about each time.

**How they want things said**, each their own choice, all in place:

- Moves say the name alone; detail goes on Alt R. Exceptions they asked for
  are the one-time summaries: the result screen, the VS screen, a trial's
  combo list, Extra Battle's introduction.
- No player numbers on each move at character select.
- The result screen puts player one first, whoever won, and gives wins, win
  streak and win ratio.
- The VS screen: "Opponent, <name>, V-Skill <n>, V-Trigger <n>. <stage>."
- Arcade endings leave out the path code (SFI, SFII and so on).
- Combos, in their own examples: "heavy punch, quarter circle forward plus
  kick kick, down, down plus heavy punch" and "KAGEROU. heavy punch, heavy
  punch, medium punch plus medium kick". Directions are words with commas
  between them; no comma before plus; the same button pressed twice is said
  twice; different buttons pressed together get plus between them; the
  game's "then" arrow is only a comma; "(STANDING)" is left out; "(CROUCH)"
  becomes "down plus"; "(JUMP)" stays "jump"; a trial's steps are joined by
  commas without numbers. They do not know move names, so Display Commands
  with these words is what they use.
- A trial's list is read again on every restart.
- A bought item in the shop says "Already purchased" after its name.
- Alt R on a prompt says its message again, then the selected answer.
- Notices after logging in say each entry once, a costume battle with whose
  costumes it offers rather than one entry per costume, and end with "Press
  Alt R for more information."

**How this session found things.** Almost everything came from reading the
game's memory while the user held the screen, with small scripts run from the
repository root, for example:

```bash
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, '.'); from sfv_access import scaleform as sf, memory_narration as mn; r = sf.attach(); every = r.items(everything=True); [print(mn.describe(it)) for it in every if it.shown]; print(mn._reasons([it for it in every if not it.shown and it.text.strip()]))"
```

That lists what is shown with selection marks and groups the rest by why it
is hidden. From there: `reader.children(obj)` and `reader._node(obj)` walk the
display tree around a text's `chain`; `reader.chain_states(chain)` gives each
object's flag word, raw alpha and empty bounds; `scaleform.screen_summary`,
`trial_summary`, `extra_battle_details` and a `memory_narration.Narrator` fed
two readings show what would be said. When a picture matters, a
full-resolution screenshot through `sfv_access.capture.Capture().frame()`
works only while the game is in front (`game.find_window().is_foreground`);
read the PNG yourself. To test a new rule against the past, the recordings in
`snapshots/scaleform-stages`, `scaleform-bgm` and `scaleform-arcade-choice`
hold every text with its chain and the display tree with flags, alpha and
children, and replaying them is how each loosened rule was shown not to mark
anything else. The logs replay too: `scaleform-log.txt` records every screen
as it changed with its marks, which is enough to rerun `Narrator` over a
session.

## Running things

Setup from a clean clone is in `SETUP.md`. Day to day:

```bash
.venv\Scripts\python.exe run.py
```

```bash
.venv\Scripts\python.exe tools\test_screens.py
```

The other suites are `selftest.py`, and `test_correction.py`, `test_learning.py`,
`test_memory.py`, `test_scaleform.py` and `test_launch.py` under `tools/`. All
seven should pass before anything is committed. `tools/show_bands.py <snapshot>` explains why a screen was read the
way it was, and is the first thing to reach for when one reads wrongly.

Memory reading does not need the game in front, and does not care if it is
minimised. Reading the screen does. So the mod narrates from memory whether or
not the game has focus, while the pixel fallback stays quiet unless it does.

```bash
.venv\Scripts\python.exe tools\read_scaleform.py --watch
```

The watch mode: memory narration alone, for trying changes without the rest
of the mod. Close the mod first.

The user starts the mod with `Start SFV Access.bat`. It used to end with
`pause`, so quitting with F10 left the console open at "Press any key"; it
now pauses only when Python exits with an error, and `app.main` ends with
`os._exit(0)` after flushing, so native calls on the speech, capture and
hotkey threads cannot hold the process open after a clean quit. The user
confirmed the window now closes on F10 (2026-09-14). The
virtual environment's python.exe is a launcher that starts the real
interpreter as a child, so one running mod shows two `python.exe run.py`
processes.

**Starting with the game.** Steam launch options, as the user already has
for Stardew Valley with SMAPI, rather than something running from Windows
startup. `tools/steam_launch_options.py --apply` sets Street Fighter V's
(app 310950) in `userdata\<id>\config\localconfig.vdf` to
`"<repo>\.venv\Scripts\pythonw.exe" "<repo>\start_with_game.pyw" %command%`,
refusing while steam.exe runs (Steam writes that file back on exit), keeping
`localconfig.vdf.before-sfv-access`, and leaving alone launch options it did
not write; `--remove` undoes it. The launcher starts `run.py --with-game`
under pythonw, output to `snapshots/console-log.txt`, unless the mutex in
`sfv_access/instance.py` says a copy runs, then runs the game command and
waits for it. No console at all, because a console coming up over the game
is one more window, and Windows 11's default terminal may not honour opening
minimised. `--with-game` leaves the game's state out of the banner (it
always said "game not running") and `GameWatch` closes the mod
`GAME_GONE_SECONDS` (3) after both game processes are gone, or after
`GAME_WAIT_SECONDS` (180) if the game never appears, so the Alt keys are not
kept from other programs. Checked on 2026-09-14 by running the launcher
with a stand-in game command, then a copy of ping.exe renamed
StreetFighterV.exe: no window, banner in the log, closed four seconds after
the stand-in ended, mutex released. Not yet done at the time of writing:
setting the launch options in Steam, which needed the user's go-ahead and
Steam closed, and a real launch from Steam.
