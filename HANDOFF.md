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
user switches to it with F9. Character select reads from Scaleform too now.
`live.py`, which reads Unreal's objects, serves the pixel path and Alt P, and
since 2026-09-15 finds the objects that hold the button layouts
(`memory_narration.KeyConfig` and `SavedLayout`). Two things come from
Windows rather than the game: the keyboard bindings the game saves in
Input2.ini, and on Button Preview the buttons being pressed (`pads.py`).

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

Also in the mod, played by the user on 2026-09-14 (sections under "Reading
the interface from memory" and "Where it stands"):

- Starting the game: the notices after logging in, Current Missions and
  Currently Available Extra Battle, each entry once, costume battles with
  whose costumes, then "Press Alt R for more information." and Close, Alt R
  giving deadlines and rewards.
- The game's short messages at the foot of the screen, such as "Your
  selection is currently unavailable." on the shop's Special.
- The shop's item lists, a bought item saying "Already purchased".
- The Fighter ID and Home change, start to finish: the change ticket prompt,
  the Home screen's flags said as countries with their region tabs, the
  Fighter ID typed with each character echoed and Alt R spelling it, the
  confirmation with the flag said as the country, the too-short and taken
  errors, and "Registration complete".
- Alt R on any prompt says its message again before the selected answer.
- Command pictures for charge ("hold back"), the full circle and rapid
  presses; Guile, Zangief, E. Honda and Blanka checked.
- Training's attack data: one sentence when an attack or combo is over, "2
  hits, 57 damage, plus 9", and all of it on Alt R.

Played by the user on 2026-09-15:

- Controller Settings (Training and Versus): each action's button, following
  edits, "left bumper, moved from Button Combo 3"; Alt B naming buttons as
  Xbox, PlayStation or keyboard keys, with a hint on opening; Button Preview
  saying what each pressed button does.
- Starting with the game from Steam, closing with it.
- Keyboard Settings (Options, Other Settings): a hint to press Alt R, which
  lists each key with what it does ("B, light kick"); Redo keyboard mapping,
  every step said with the key just assigned. The user's words: "everything
  worked as it should".
- Challenges' Demonstrations: each page, title and explanation or caption
  with its commands in words, said once when it waits on Start Demonstration
  or Proceed ("Moving. By pressing the left or right directional buttons...
  Start Demonstration"), Alt R repeating it.
- Story's Tutorial: each instruction once as it comes, buttons said as their
  actions ("pressing either light punch, or light kick"), and the TIP boxes
  between steps. The scene subtitles are left unsaid, the user's story voices
  being English; Alt T turns them on.
- The lone "Sub Menu" hint at launch is no longer said (written the same
  day, not yet heard from a launch).

Written and checked against the game or a recording, but not yet heard in
play: Controller Settings with both players' screens open in Versus. Heard in
the user's Arcade run of 2026-09-16, and so ticked off: an ending ("G. The
so-called "President of the World"..."), the Special Artwork credit after it
and the Gallery messages, Arcade's final-stage opponent card ("FINAL STAGE.
RYU. REWARD. 35570"), the bonus stage and its result, the score summaries,
and summaries said once each (`SUMMARY_SETTLE`); "Logging into the server..."
at startup has been heard at every login since.

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
tick. A grey only counts in `landed_on` if the same text was grey a read ago:
the main menu's banner at (799, 452) brightens from the 0.27 its entries are
drawn in to white as it takes the name of the mode, and passing through 0.6
while structurally chosen it said "TRAINING. Unavailable" on returning from
Training (and the same for Arcade and Versus; the user reported it on
2026-09-15, and `scaleform-log.txt` at 14:01:53 holds the frame, white a read
later). The rows of a list are grey before the cursor reaches them, so real
ones survive the test; arriving on a grey row with nothing grey behind it now
says the name without "Unavailable", which the read key still gives. The same session showed the tab name, "BGM LIST", and the popup title,
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

On 2026-09-30, measured beside the mod with a profiler in its own process: a
quick read of the main menu was 36 ms and about 3,000 ReadProcessMemory
calls, two thirds of the time the sweep (616 blocks, 55 MB) and most of the
rest placing each field. A list keeps every row it builds as it scrolls
(Survival's fighter list went from 47 fields to 260, eight per row), and
each text read every parent above it again, so the list took 75 ms. A pass
of `items` now keeps each object's render node and parent for the pass
(`_pass`, per thread, since the wide sweep reads on its own thread), reads
a DocView's text, listener and box in one read, a StyledText's head and its
paragraph array in one each, and an object's parent and render node entry
in one: on Survival's screen, 7,311 reads to 4,441 and 65 ms to 52, results
identical. What is left is the sweep (24 ms) and `_mark_highlighted_rows`
(18 ms, only while a long list shows with no gold in it). Narrowing the
sweep to blocks that held text is what made new text a second late before,
and a scrolled-in row is new text, so it was left alone.

**Fighter lists went quiet in the middle.** The user reported lag scrolling
Survival's and Trials' fighter lists (two columns, five rows in view). It
was silence, not lag: RYU to KARIN were said, then nothing all the way down
however long they waited, and going up and back down said the fighter. The
profiler showed reads fast enough; a recorder that logged every fighter's
name read but not counted as showing found the cursor's cell there all
along, gold and in place, at (646, 772), under a node at alpha zero with
real bounds (third object up from the field). Pressing down from the bottom
row scrolls a new row in; its other cell came up to full alpha within half
a second, the cursor's stayed at zero until it was selected again without a
scroll. Whether it is drawn is not known. `_show_list_cursor` counts it as
showing, the final opponent's way: only while `FIGHTER_LIST_MIN` fighters'
names show in one movie, only under the first zero-alpha object above a
gold fighter's name, and only text hidden by nothing else. The user found
it "mostly working" the same day, with a few stutters that caught up after
a moment.

The stutters were blocks. A recorder logging the gold cell whenever it was
incomplete, with a full search beside each quick read, found the row the
list had just built complete and gold in the full search only, in blocks
the quick read's list did not have yet, while the old cell's gold drained
part by part; and earlier "GUILE" was said, then "SCORE 195400. TIME..."
alone a second later, the name in a walked block and the rest not. Whatever
the cursor lands on waited for the next walk, anything up to a second. Now
a quick read whose selection differs from the last one brings the walk
forward (`refresh_soon`, at most every `PAGE_REFRESH_SOON` after the last,
blocks only; the grid walk keeps its pace), and `landed_on` says a
fighter's name again when new text joins it in its cell (the first two
objects above, holding no other fighter's name: character select's two
sides share one holder, and the first try said "KOLIN. KEN" as player 1
moved). On a still screen that is still about one walk a second.

The user found that "about mostly the same", so the delay was measured: a
recorder polling every controller and the keyboard (the game's bindings,
the arrows, and the user's own Space for up and S for down) every 5 ms,
reading as the mod does, timed each press to the first read with the new
fighter gold. Median 209 ms, one in ten over 418, the worst about 530. Most
moves were the game taking a few hundredths to light the cell plus one or
two read cycles (a read of 50 to 110 ms, then `POLL`); the slow ones were
blocks, the walk brought forward taking 210 ms while scrolling, against 76
idle, and slowing the reads it ran beside. A walk over only Scaleform's
stretch of addresses still meets about 8,000 regions (41 ms), so that was
no help. What did help: each block is an allocation of its own, 0x11000 at
the start of a 128 KB slot (the 0xF000 after it free but unusable), so a
new one can only be in space the last walk found free, and there are about
700 such stretches. `refresh_pages` notes them from the same walk
(`ProcessMemory.regions_and_gaps`) and every quick read goes through them
(`_probe_gaps`, one `query` per region, about 3 ms). A checker in its own
process, probing every 0.1 s against a full walk every second, found the
first version caught 7 new blocks of 187 (it stopped at the unusable
tail), the second 386 of 418 (it stopped at free space Windows left between
new blocks), and the third goes through each stretch to its end; the rest
were blocks grown inside an existing allocation, left to the walks. With
the first version (and the walk brought forward, which stays) the recorder
measured median 194 ms, one in ten over 294, the worst 563, and the user
called it "working pretty well"; with the second, "working nicely"
(2026-09-30). The third was not tried in play; it only finds more.

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
the user on 2026-09-14. On 2026-09-15 the user found that the bumpers, which
move between the events on offer, said nothing: they swap the panel's contents
and leave BEGIN BATTLE gold, so nothing is newly selected and `landed_on`
returns nothing (`scaleform-log.txt` from 17:58:23 holds four such reads).
`Narrator.step` now names a new event where it stands, by its title alone,
the user having asked long ago that a move say the name and leave detail to
Alt R. What marks it as another event is the whole panel without its DEADLINE
line, since the deadline counts down while the same event shows. The brief
alone was not enough: the user then heard silences of ten seconds and more
moving through the six events on offer on 2026-09-15 ("it hangs and comes
back", spoken-log.txt from 18:06:15), the crossover costume ones sharing a
title, fee, difficulty and conditions and differing in their rewards further
down the panel.

**Survival's Battle Supplement screen.** Read live from the user's run on
2026-09-15 (stage 1 of Easy, `tools/read_scaleform.py`). Down the middle a
list of supplements with their costs, which read as a menu already ("Health
Recovery: Medium. -9000"); on the left a spending panel (Selected Supplement,
SCORE and its number, the supplement with its cost, what that leaves, Selected
Battle Items, Parameter Increase with its percentage a row below); on the
right the fight just won (TIME "0:00'31''616", "+ 13900", SCORE); and at the
foot "Next Stage 2", which alternates with "CPU Level 2" in the same place.
The fight's own HUD is still on the screen behind it ('9999999', '9:59:59.99',
'STAGE ', 'PLAYER 1'), so anchors are the "BATTLE SUPPLEMENT" heading, the
time's shape, "+ " and a number, and the "Next Stage" and "CPU Level" labels.
Two scores sit on that screen and the user asked which was which: the "+ N"
beside the fight's time is what the stage earned, the panel's SCORE is the
running total and what there is to spend (stages 1 to 3 earned 13900, 12790
and 11704 against a total of 38394). They are said as "Score for the stage"
and "Total score ..., to spend".

`survival_summary` says "Stage 1 cleared. Time 31.616 seconds. Score 13900.
Next stage 2. CPU level 2" through `screen_summary`, waiting until every part
is there so it is said once and whole; `survival_details` gives the left panel
on Alt R. The left panel stops at `FOOTER_TOP`, the description line having
been read as the parameter increase while its percentage was not drawn, and
the increase must look like a number. Not yet tried: later stages, a lost
run, the save menu, and whatever Survival's end shows.

**Survival's Battle Items screen** follows the supplement one, heading
"Battle Items", and lists what the player holds with how many ("Grapes. x2",
"Kanzuki-ryu Scroll. x1", "Masters Guide. x4"), the selected one gold at
(803, 260) as the supplement list does, over the same left panel. It read
already, but the names say nothing about what the things do, and that is in
the description line. At the user's request the line now follows the name by
itself after `DESCRIBE_AFTER` (0.5 s) on that screen alone, and moving on
before it is due drops it, so running through the list stays quick. This is
the one place that breaks the rule of naming on a move and leaving detail to
Alt R. At the user's request
the sentence carries the health they are taking into the next stage, since
Survival does not refill it: `Narrator` asks its `health` callback for a
reading, but only on that screen, and `app._health_reading` measures player
one's bar with `hud.health_fraction` off a frame up to half a second old. The
bars are the fight's own, still drawn behind the screen; if they cannot be
read the sentence is what it was. The first try read one frame per pass and
said the sentence over and over, the same bar reading 94, 100, 0, 95, 96, 97
as the screen flashed (spoken-log.txt 19:41:56 onwards on 2026-09-15). Now
`app._health_reading` takes `HEALTH_FRAMES` frames `HEALTH_FRAME_GAP` apart,
uses the middle reading and only if `HEALTH_AGREE` of them sit within
`HEALTH_TOLERANCE` of it, and the narrator asks once per visit and keeps the
answer (`health_reading`, `health_asked`), so a wobble can no longer make a
new sentence. Reading the middle of them was wrong: the user's fight
ended in a perfect KO, which leaves full health, and the readings were 94 to
97 with the odd 100. A watcher of its own (a second process, so its capture
does not disturb the mod's) saved three frames of the screen and the picture
settled it: player one's bar is drawn there, in the fight's own place, and it
was full, 732 of 735 columns lit in the best frame, while another read 95. A
shine sweeps along the bar and hides a stretch of it, and a shine can only
take lit columns away, so the fullest of `HEALTH_FRAMES` frames is the true
reading (`app._health_reading`), and the narrator asks once per visit. The
same probe run while the user had tabbed away read 0 percent five times over,
having captured the Claude window, so the reading is taken only while the
game is in front. Opponent's bar: not drawn on that screen, only player
one's.

Taking five frames in a row as the screen opened then said 33 percent to a
user who had lost almost nothing: the bar arrives filling up from empty. So
`app._health_share` returns one frame's reading, cheap enough to ask for every
pass, and `Narrator` watches it: the fullest of the last `HEALTH_WINDOW`
samples (which ignores the shine), believed once it has held within
`HEALTH_TOLERANCE` for `HEALTH_STEADY`, or after `HEALTH_CAP`. The screen's
sentence waits for that, since saying it early means saying it twice, so the
selected supplement is named first and the sentence follows. The reading is
always the window's fullest: keeping the older value while a rise sat within
tolerance stuck at 93 against a bar reading 95.

**The bar is two colours.** It then said 33 percent for a bar a picture
showed 60 percent full (`bar-0.png`, stage 3 of the user's run). A damaged
bar runs from (91, 254, 39) at the end that empties first to (236, 252, 5) at
the other, over (26, 26, 26); `hud._yellow` wanted red above 170, so only the
yellow half of the fill counted. `hud._bar_lit` takes strong green with little
blue as well, and `tools/test_hud.py` paints bars in those colours and checks
they read as themselves. The full-health frames still read 95, 94 and 100, the
100 being the shine-free one. A full bar is all gold, which is why the first
picture read right and the damaged one did not.

**The bar is measured off the game's picture, not the screen.** On
2026-09-28 the user passed on a tester's report that health did not read
properly after every fight. The tester's spoken-log.txt from 2026-09-16 (in
`Friend-Logs/`) said "Health 0 percent" after every stage of a Survival run,
Full Health Recovery included, and their Graphics Settings read "Resolution.
1920 x 1200", "Full Screen Mode. OFF". The game keeps a 16 by 9 picture and
fills a taller window with black bars above and below, 60 rows each at 1920 by
1200, and a window's title bar moves it further; capture is of the whole
screen, and `hud` scaled its 1920 by 1080 positions to the screen's size, so
it looked above the bar and found nothing. `game.find_window` now also gives
the window's client area (`GameWindow.client`), asked for in the screen's own
pixels (`_screen_pixels`, since the mod is not DPI aware and a scaled laptop
screen would shrink every position), and `GameWindow.picture` is the 16 by 9
box inside it (`game.picture_box`). `App._frames` cuts that box out of each
capture (`capture.crop`, black where it runs off the screen), so the HUD, the
pixel reader and Alt S snapshots all see the picture as on a 16 by 9 screen;
on the user's full screen 1920 by 1080 the box is the whole frame and nothing
changes. `App._picture_box` looks the window up at most once a second
(`PICTURE_RECHECK`) and notes each change in scaleform-log.txt ("game window
..., picture 1920 by 1080 at 0, 60"), so the next tester log shows what
their machine did. And a bar with nothing lit is now no reading at all
(`App._health_share`), since the player has just won and always has some
left: the sentence goes without health rather than saying 0. Checked with
painted screens in `tools/test_hud.py` (a 1920 by 1200 screen, a 1280 by 720
window with a title bar, a window pushed off the bottom), which also shows
the old measurement reading the tall screen as 0; not yet heard in play on a
machine like the tester's.

**Survival's health is read from the run, not the screen.** The user then
said they never wanted a pixel reading mod, because of exactly this, so the
health on the supplement screen now comes from memory. The reflected
`KWReSurvivalProgressData` (VitalGauge, VitalGaugeMax and the rest in
`KWSurvivalPlayerParameterData`) turned out to be the suspended-run save
(`GameProgressSave.SurvivalProgressData`), which did not change during play.
The live numbers sit in `SurvivalIterationState_0` (in the Entry level,
made as the SURVIVAL MODE TIPS screen shows), in memory the game does not
describe: +0x408 the health, +0x40C the most it can be, +0x400 the total
score, +0x404 the total before the last stage, +0x3FC the run's time in
frames. Found with a watcher logging that object's memory while the user
played on 2026-09-28, and checked against the bar: 645 of 975 after stage 7
(the bar said 66 percent), 975 at once on buying Health Recovery High, 711
after stage 8 (73 percent). The numbers change the moment a fight ends, some
nine seconds before the supplement screen. `memory_narration.SurvivalHealth`
finds the object in the background as `KeyConfig` does (1.6 to 1.9 seconds
the first time here, then one small read), and `survival_share` rejects
anything that is not a health within its most. The narrator asks on the
tips screen so the run is found before the first stage, takes the first
reading on the supplement screen, and waits at most `HEALTH_CAP` (3 s)
before saying the sentence without health. The old waiting for the bar to
settle is gone, and with it the sentences that went missing when the user
moved on within two seconds (stages 2, 3 and 6 said nothing that day). The
sentence keeps the arrival reading; Alt R reads again
(`Narrator.health_words(fresh=True)`), so it gives the new health after a
recovery is bought. Not yet heard in play with the mod's own code.

That last part was wrong, and is gone: the watcher showed the recovery
applied at 18:45:22, the moment the player said Yes to starting the next
stage on the Battle Items screen, score taken at the same moment, not when
it was chosen. So nothing changes on the supplement screen. At the user's
request a rise in the run's health within `HEALTH_RISE_WINDOW` of leaving
the supplement or Battle Items screen is said as "Health now at 100
percent" (`Narrator`, `health_known`, which reads the run only once it is
known and never starts a search). A fall (the next fight's damage) and a
rise long after (a new run starting full) say nothing.

**The fight's gauges come from the fighters' records (`fight.py`).** Alt H
measured the bars off the screen, which read a full health bar as 83
percent even on the user's own screen. Each fighter has a record in battle
code the engine does not describe, found on 2026-09-28 with watchers while
the user played Training and Versus against the CPU (the first two tries
failed: a full bar is not 100 percent on screen, and copying all memory
took two seconds while the bars moved; the third matched only which bar
moved, with reads straight into kept buffers). What was found, all in
`fight.py`'s docstring: the records start with a pointer to module +
`VTABLE_RVA` (0x2C51680), exactly two of them, the same two through
Training and five matches; 16.16 fixed point in 4-byte slots, health +0xD0
of +0xD4, the Critical Art gauge +0xDC of +0xE0 (300 a stock, checked
against the stocks lit on screen), the V-Gauge +0xF4 of +0xF8 (600 or 900,
300 a bar), stun +0x138 of +0x13C (Ken's reached its 1050 as he was
stunned). Also seen and not used: a second health at +0xC0 that moves on its
own for a moment (recoverable damage, perhaps), and +0x300, which looked
like a side number until it read 0 for both at a match's start and turned 1
on the fighter knocked out. Which record is player 1 is not in the record
as far as was found: a CPU's `KBP_BattlePlayerController_C` holds its own
fighter's record at +0x6B0 (a player's holds -1), its `NetPlayerIndex` the
side, so against the CPU that decides it (`fight.order`); two people leave
no link and the order seen all that day is used, player 1's record at the
higher address. The code never steps by the distance between the two
(0xBF40), so that order is not built in and is the thing to check first if
Alt H ever swaps the two. Each finding and how the side was decided goes to
scaleform-log.txt ("fight: ..."). `tools/test_fight.py` builds records by
hand. The Critical Art gauge in the Survival record (+0x410 in
`SurvivalIterationState`) and V-Gauge (+0x414) are the same numbers, copied
at the stage's end. Alt H confirmed working in play by the user on
2026-09-28 (sixteen Versus matches against the CPU as player 1 from 22:37,
the side decided by the CPU's link). Not yet tried: two people against each
other.

**Which side is the player's.** Later that night the user chose CPU VS
PLAYER 1 and found both the VS screen ("Opponent, GUILE", their own fighter)
and Alt H taking them for the left. Nothing on the VS screen or in a fight
says which side is the player's, offline; Versus's list does ("PLAYER 1 VS
PLAYER 2", "PLAYER 1 VS CPU", "CPU VS PLAYER 1" at (503, 274 to 358), the
choice gold), so `Narrator.player_side` takes the side of the selected entry
(`scaleform.versus_side_choice`), goes back to the left when a main menu mode
is selected (every other mode starts there), and online takes the side
carrying the player's Fighter ID (`versus_my_side`). `versus_summary` names
the other side against the CPU, and Alt H calls the record on the player's
side "You" (`App.on_read_hud`). That match also showed two things about the
records: they were new ones, at new addresses (found again, the old ones
having lost their marker), and no controller linked either, so the side came
from their order in memory, which was right again: Ken on the left at the
higher address. The +0x300 flag read 1 for the left fighter there, who lost,
settling that it follows the knock-out and not the side.

Remembering the list was not enough: the user restarted the mod on the
result screen (23:16:24), it had never seen the list, and Alt H gave them
the CPU's 0 health. The game has the side: the live `KWBattleSetting`
(under `KiwiGameSingleton_0`; the one under
`Default__KWBattleSettingPseudoSave` is Training's saved setting, which read
USER against DUMMY) points through `m_player_setting` to the players' table,
and `GetCtrlType`'s code reads each player's `EKWCtrlType` at +0x21C of its
0x590-byte entry: 0 USER, 1 NET, 2 COM, 3 DUMMY. CPU VS PLAYER 1 read COM
then USER. `Fight.side` gives the side of the one USER (`fight.player_side`),
None for two players on one machine; Alt H asks it at every press, and the
narrator asks it on the VS screen (`scaleform.on_versus_screen`), keeping
the side seen in the list or by Fighter ID for when it says None. Online the
remote player should read NET, so it should work there too; not tried.
Confirmed in play by the user the same night: Alt H from the right, the mod
restarted mid-session (23:25, "controllers [2, 0], the player's side 1").
The VS screen's side from the settings went unheard, Play Again skipping it.

**Health warning beeps (`beeps.py`, `App._watch_fight`).** Asked for by
the user the same night: "A higher beep at 75%, another highish beep at 50%,
a lower beep at 25%, then maybe 2 short low beeps at 10%", player 1 in the
left speaker and player 2 in the right ("like in a stereo field"), once per
crossing. The tones (1047, 784 and 523 Hz, then 392 Hz twice) are made as
WAV data and played by `winsound.PlaySound` from memory on a thread of their
own, which does not touch the speech. A level sounds as health drops below
it and again only once health is back above it by `REARM` (a new round); a
combo past several sounds only the lowest; the first reading of a fight
sounds nothing. The fight is known by the labels over the health bars in
memory (`scaleform.fight_on_screen`: "PLAYER 1" at (167, 90) and "CPU" at
(1834, 90), either way round, or "PLAYER 2"), which in both memory logs
of the day never matched anything but a fight, so the fighters are only
looked for while a fight shows (every `FIGHT_POLL`, `FIGHT_RETRY` after a
failed sweep). `tools/test_beeps.py` checks the levels, the speakers and the
labels; `tools/beep_demo.py` plays every level on each side. Heard in a
fight by the user the same night: "It works pretty good", though "a bit
loud". So F5 and Shift F5 (`beeps_louder`, `beeps_quieter`, at the user's
choice of keys) move the volume `VOLUME_STEP` percent at a time, 0 to 100, kept as
`beep_volume` in settings.json (`buttons.beep_volume`,
`change_beep_volume`), saying "Beeps 40 percent." or "Beeps off." and
playing the 75 percent beep in both speakers at the new volume. The
percent is heard, not measured: a tone's peak is the square of the share
(`beeps.loudness`), so the steps sound alike; the first beeps were about 59
on that scale. The default was 50 and the step 10 until the user found 50
still loud and asked for 40 and steps of 5.

**Counter hits, and new sounds (2026-09-30).** The user asked whether the
mod could say when a counter hit lands. The banner ("COUNTER", gold, on the
attacker's side at about (200, 596), saved by a watcher at a hit) is a
picture: no text field holds it, even hidden, and the game's strings have
no "COUNTER" or "CRUSH COUNTER" on their own. The fighter records hold it
instead. A recorder kept both records (0x2D00 bytes each; they sit 0x1FE0
apart, so reading more from the second runs off its memory) every 2 ms and
saved a window round each drop in health, while the user landed hits on
Training's dummy with its Counter setting ON (27, crush counters among
them) and Normal (8). One byte told them apart: +0x2F8 of the fighter hit
goes 0 to 1 as the hit lands and holds 0.37 to 0.7 s, back to 0 at once if
a follow-up hit lands, which is never a counter; +0x2FC is set with it on a
crush counter, for the whole of its longer stagger (`fight.COUNTER`,
`CRUSH`, `counter_marks`). +0x2F3 looked like a crush mark at first but
stayed set through the normal hits. `App._watch_counters` reads only those
marks, every `COUNTER_POLL` (10 ms, about 0.06 ms a read), from the records
`Fight.read` last ordered, and plays `beeps.counter_sound` in the speaker of
the side that landed it (the side opposite the record marked). Crush
counters sound nothing, at the user's request, the game's own sound being
distinct. F6 and Shift F6 set its own volume (`counter_volume`, default
40). The user chose the sound from five played to them (a 6 ms click and a
50 ms high tone at 2637 Hz) because it is quick enough to react to, and
the health beeps' style from eleven: a xylophone, its third partial dying
first, three semitones below the first beeps. The demos were played from
a script with each candidate's number said through the screen reader
first, which worked well for choosing. They asked about the Python audio
library Synthizer for the sounds; it was archived in 2023 with builds only
up to Python 3.11, and the sounds are made here in a few lines instead.
Not yet heard in a fight.

**Online the beeps were silent (2026-09-29, fixed, not yet heard).** The
user played Battle Lounge matches that evening and heard no beeps. The
fight's display online labels the player's own bar alone, "YOU" at (167,
90), with nothing over the opponent's, so `fight_on_screen`, wanting a label
at both corners, never saw a fight. It now also takes "YOU" alone at either
corner of that row (`ONLINE_FIGHT_LABEL`). In that night's memory log "YOU"
there was only ever that label, in 197 screens across the online fights; the
Lounge's "MENU", "STANDBY" and "SELECT" sit on the same row at x 190 outside
a fight, hence the name and not any lone label. The records themselves read
online: Alt H swept two of them at 22:52, 23:24 and 23:32, and the settings
said controllers [0, 1], USER and NET, as expected (on the VS screen, a
moment earlier, they said [0, 0]). No note of the order changing was logged,
so it was settled by character as offline. The user confirmed Alt H read
correctly online, checked by a sighted friend watching the screen. Between
rounds online the display
hides for about three seconds while "YOU" / "P1" shows over the player's
fighter at (394, 557), which resets the levels; health is full then, so
nothing is lost. Unknown: where "YOU" sits when the player is on the right
(either corner is accepted).

**The tests wrote over the player's Fighter ID.** `tools/test_scaleform.py`
moved `buttons.SETTINGS` to a temporary file only halfway down, after the
narrator had stepped through pretend main menus whose card says "Dengster";
the narrator saves the card's Fighter ID, so every run put "Dengster" in the
user's settings.json, and the mod put it back only on the next visit to the
main menu. Found on 2026-09-28 when a run changed the file; the move now
happens before the first test, and the file is left as it was. The Survival
changes above (the sentence's health from the run, "Health now at") went
unheard that night too: no Survival run was played after the mod was
restarted with them.

**Which fighter record is player 1 (2026-09-29, fixed).** After the zip
SFV-Access-2026-09-29-712ddef was built, the user played Survival and found
Alt H and the beeps reversed (Alt R, from the Survival record, was right).
`fight.order` falls back to "player 1's record at the higher address", and
that is chance: Survival's stage 1 pair (0x2516A85CC00 the user's G, 783 of
1025, 76 percent carried; 0x2516A85E580 the CPU) had player 1 lower, the
stage 2 pair (0x251671F0CC0 the user, 683 of 1025; 0x2515FAEB280 the CPU)
higher, which is why "halfway through the fight, the mod corrected itself".
The side from the settings (`Fight.side`) was right throughout (0). The
controller link was absent. Ruled out as a player-1 marker: +0x300 (knock-out
flag), +0x2F4 (2/0 in two pairs, then 0/0), and past about +0x158 the records
hold different things for different characters. No list in memory holds both
records near each other. Next: `KWBattlePlayerSetting` has GetCharaCode
(0xD14040), GetStartSide (0xD18E60), GetStartPosition (0xD18DD0) and
GetVTriggerID (+0xDC); read the live table's entries 0 and 1 and look for the
character (or V-Trigger) in the records' shared part, to match record to
side, with a mirror match as the case needing a fallback. Other routes: the
health bars in the Scaleform display tree (the labels "PLAYER 1"/"CPU" at
y 90 are its texts), whose drawn size gives each side's share to match
against the records. The work stopped a while because the command tool's
safety check kept failing.

Fixed by character: each record points at +0x98 to its character's data,
which holds the code ("Z30", G) at +0x1C0; the live settings entry holds
each player's code at +0x90 (`GetCharaCode`'s code reads there; `GetStartSide`
reads +0x190, which was -1 for both). `fight.order_by_character` puts the
record with player 1's code first, and `Fight.read` notes "by character";
a mirror match, or a code that will not read, falls back to the controller
link and then the address, and the note says the characters did not settle
it. Read live in Survival: player 1 Z30 (G, the user, USER), player 2 Z40
(COM).

Still confused once in play (00:44 on 2026-09-29): Survival's settings move
on to the next stage's opponent before the fight ends (in stage 3 against
Ken they said Z23, Menat), and between stages they read as nothing for a
moment (controllers [0, 3], no codes). So `order_by_character` now goes by
player 1's code when exactly one record has it, player 2's only when player
1's cannot decide; `Fight.read` keeps the order it settled by character
(`_decided`) while the same two records last and the settings say nothing;
and `Fight.certain` is false while the order is only a guess, when
`App._watch_fight` sounds nothing and starts the levels afresh, since a
guess that swapped the two would sound as a sudden drop. A mirror match
counts as certain, nothing better being known. Not yet heard in play.

**Two Survival runs in memory.** The same night Alt R, and every stage's
sentence, said "Health 70 percent" whatever happened: an earlier run's
`SurvivalIterationState_1` (the user's G, 719 of 1025) outlived it, and
`SurvivalHealth` took the first found while the Seth run was
`SurvivalIterationState_2`. The live run is `GameScene_0`'s `CurrentState`
(reflected, on `KiwiGameScene`), so `SurvivalHealth._find` takes that,
keeps the scene and checks at each reading that it still points at the run,
and only with no scene on a run falls back to the newest by object index.
Confirmed in play by the user (01:00 onward: 91, 82, 35, 55 percent, and a
fresh run's `SurvivalIterationState_3` followed), with Alt H and the beeps
settled by character throughout.

"Health now at" had never yet been heard: bought at 01:07:39 (Health
Recovery Low, 35 to 55 percent), nothing was said. The rise lands at the
Yes, while the Battle Items screen is still fading, and the narrator took
that reading as the one before. It now keeps the lowest reading seen on the
supplement and Battle Items screens (`health_armed`); `tools/test_scaleform.py`
lands a recovery on the fading screen. Not yet heard in play.

**The screen a run ends on.** Read live on 2026-09-15 from a run the user
lost on purpose at stage 7, having heard only fragments of it ("RESULT.
SURVIVAL. EASY. Konggster. 0:00'34''400", then "RESULT. Match History. STAGES
CLEARED"): it arrives in pieces and `on_results` does not hold, there being no
WIN or LOSE on it. Down the left each label has its value under it (SURVIVAL /
EASY / the player, STAGES CLEARED "6", CLEAR TIME "-:--'--''---" when the run
was not finished, SCORE "69014" under "NEW" for a record); down the right,
Match History pairs every opponent with the time that fight took, which is the
only place Survival names them. `survival_result_summary` says "Survival
result, EASY. Stages cleared 6. Score 69014, a new record. Press any button"
through `screen_summary`, waiting until the stages and score are there so it
is said whole; `survival_result` gives the seven fights on Alt R. "Press any
button" is said because a screen silently waiting for one sounds like nothing
happening.

The opponent's name during a run is still unsaid: Survival has no VS screen, its
display names only PLAYER 1 and CPU, and the name sits in memory hidden
(18:41:03 on 2026-09-15 logged 'CHUN-LI' among the hidden), so it wants the
live-state route through `live.py`, as character select did.

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
" Sub Menu", a button hint shown alone on a black frame, at every launch; the
user asked about it on 2026-09-15, and `landed_on` no longer names a changed
text that `is_button_hint` (a leading picture space, a few words, low on the
screen; the logs hold "  Fighter Profile", "  Hold to close", "  Icon Info",
"  Character List", "  Change Style" too). Status lines went
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
to 13:46:36 on 2026-09-14), and every five on 2026-09-22 while the user sat
on Gallery: the banner keeps the cursor's mark ("+" in the log) as it names
the icon, then goes back to its adverts about thirty seconds later, and each
advert was a new selection. A move changes the description line with the
banner, an advert does not, so `Narrator.step` drops a sentence made only of
`banner_texts` once the description has stood `BANNER_CATCHUP` (1 s).
Replaying that evening's log said LOGIN, EXIT, LOGIN, GALLERY and none of
the adverts. The next day the adverts were read again with the cursor on
Battle Settings: the mode the cursor is on leaves its place in the list for
the banner, and once the banner went back to adverts its name was nowhere,
so the main menu went unrecognised. `banner_texts` now wants all but one of
eight modes (`MAIN_MENU_ENTRIES`). Then they were read after coming back from
the shop, which leaves the cursor on the banner itself: there each advert
brings its own description line ("Begin the game mode displayed in the
Information section.", "In a mysterious palace run by Rose, Menat awaits..."),
so the description moved with it. `Narrator.step` now also drops an advert
that follows an advert, what the banner showed a read ago holding no mode's
or icon's name (`MAIN_MENU_NAMES`) and what it shows now none either. Arriving
on the banner still says the advert showing, and Alt R the current one.
Replaying the log of both says every move and no rotation. Confirmed in play
by the user the same day, idling on the main menu after a Versus match.

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

**Training's Controller Setting.** Fourteen action rows (x 804, y 199 on, 44
apart: Light, Medium, Hard Punch, Light, Medium, Hard Kick, Throw, V-Skill,
V-Trigger, V-Shift, Button Combo 1 to 4) with each button drawn as a picture
at about (1120, row + 21) and no text, so only the action was said. What did
not work, so nobody tries it again: the profile's `KWUserProfileDetails.
KeyConfigData` (`/Script/GameProgressSave...MainUserProfileDetails` +0xB0,
the struct `KWKeyConfigs`: `Data` fifteen bytes and `TypeData`) changes only
when the screen is left; the `ButtonConfig` script objects (found by the
pointer to their class name string at their start: label +0xA0, action code
+0xE0 such as "LPLK", picture URL node +0x100) are filled when the screen
opens and ignore edits; the picture loaders' URLs (+0x208 of the loader,
script object +0x2C8) point one row ahead, as the flag loaders did; matching
the pictures by their pixels confuses X, Y, A and B and fails on the selected
row, whose dark bar changes the icon. What works: searching all memory for
the layout the user had just made found `WSKeyConfigGFxPlayer_1`
(`/Game/Maps/Entry.Entry.PersistentLevel`) holding, in native memory past
its properties, the layout the screen opened with at +0x467 and the one being
edited at +0x477, each fifteen bytes and a type byte. A byte per action in
the enum order LP, MP, LK, MK, P3, HP, K3, HK, LPLK, MPMK, HPHK, LPMP, LKMK,
MKHP, MPLK, each the pad key number (up 0, down 1, left 2, right 3, X 4, Y 5,
A 6, B 7, LB 8, RB 9, LT 10, RT 11, L3 12, R3 13, Start 14, Back 15, none
17). The rows' actions came from the ButtonConfig codes: Throw LPLK, V-Skill
MPMK, V-Trigger HPHK, V-Shift MKHP, Button Combo 1 LPMP, 2 LKMK, 3 P3, 4 K3.
`memory_narration.KeyConfig` finds the instance through `live.find_by_class`
on a thread (about five seconds, once; the instance with a GFxMovie and a
layout that makes sense) and reads +0x477 each read; `mark_controller_buttons`
notes each row's button, and `landed_on` says a note that changes on the
selected row with the row it was taken from ("left bumper, moved from Button
Combo 3"), the note having joined `selection_key`. A note appearing where
there was none is the layout arriving, not an edit, and is not said. The
user's hitbox button they call left trigger is the game's left bumper.
Checked live; not yet heard.

The user asked for the buttons in their own controller's names, and chose
Xbox, PlayStation and keyboard (not hitbox positions). Alt B cycles them,
saved in `settings.json` beside run.py (git-ignored); `sfv_access/buttons.py`
names a pad key number in the chosen style. Keyboard names come from the
game's `%LOCALAPPDATA%\StreetFighterV\Saved\Config\WindowsNoEditor\Input2.ini`,
`[AssignKeyboard]` `KeyboardKeys_0` to 15, read again when the file changes.
Their order, up, down, right, left, A, B, X, Y, LB, RB, LT, RT, L3, R3,
Start, Back, was worked out from the defaults the user knows (punches G, H,
J, kicks B, N, M) against the controller defaults; the directions' order is
a guess from WASD. The same file keeps each player's XInput and DirectInput
button remaps under `[AssignButton]`, not used yet. At the user's request,
arriving on Controller Setting says `CONTROLS_HINT`, "Press Alt B to cycle
through button styles.", once per visit after the row arrived on (or alone
after 0.6 s if nothing is named); leaving for more than `GROUP_MEMORY` starts
a new visit. Any other button configuration screen will need
`on_controller_setting` to recognise it.

Button Preview, opened from Controller Setting, draws the controller with
each button's action as pictures; its only text is "<button_b> Hold to
close" at (642, 867), over the Controller Setting rows (Light Punch's row
covered). `mark_controller_buttons` notes the whole layout on that hint
(`layout_sentence`): "Button Preview. X, light punch. Y, medium punch. right
bumper, heavy punch. left bumper, all three punches. A, light kick. ...  Hold
B to close." Buttons go in `PREVIEW_ORDER`, the top row X, Y, RB, LB then A,
B, RT, LT, and actions by `ACTION_WORDS` (the button combos as what they
press); keyboard style closes with Escape. That was said on opening at first;
the user did not want it, but each button's action as it is pressed, which
is the point of the screen. Now opening says only "Button Preview. Press a
button to hear what it does. Hold B to close.", Alt R gives the layout, and
`pads.PressWatcher` runs while `preview_open`: every 10 ms it reads XInput
for all four controllers (buttons, triggers past 100, the left stick past
16000 as directions) and `GetAsyncKeyState` for the keys bound in Input2.ini,
turns them into pad key numbers, and says `press_words` for each new press
("light punch", "Start, no action", "up") from the layout at the last read.
Whatever is held when watching starts is not a press. The user's hitbox is
XInput controller 0. DirectInput-only pads would not be seen. Not yet heard.

**Keyboard Settings (Options, Other Settings).** Sixteen keys in a column at x
796 (from y 109, about 42 apart, alpha 0.5) beside pictures of the buttons
they stand for, over "Redo keyboard mapping" and "Close", the only selectable
entries, and only those were said. The pictures the screen loads are the pad
icons up, down, right, left, A, B, X, Y, RB, LB, RT, LT, RS, LS, Start, Back,
and the user's keys W, S, D, A, B, N, G, H, J, K, M, comma, slash, period,
Enter, Escape agree with Input2.ini in that order (`KEYBOARD_ROW_BUTTONS`).
Arriving adds "Press Alt R to hear which key does what." once per visit, and
Alt R says each key with what its button does in the saved layout, "B, light
kick". The saved layout comes from the profile (`memory_narration.
SavedLayout`: the `KWUserProfileDetails` named MainUserProfileDetails whose
path has no `Default__`, its `KeyConfigData` property). Redo keyboard
mapping asks, from the game's text, "Press the key to be assigned to
{button_A}." and "... {CMD_8}. (You can press Up/Down/Left/Right to skip.)":
button pictures in a text about assigning are marked with their number in
`_with_pictures` and `fill_pad_marks` makes them "the A button, light kick".
The Alt R list was checked live. Seen live next: Redo keyboard mapping
clears every key to "-", lights the row being assigned, and puts the
instruction in the description line (110, 992), "Press the key to be
assigned to <cmd_8>. (You can press Up/Down/Left/Right to skip.)", so all
that was said was "-". `keyboard_prompt` reads that line; the narrator says
each new instruction, the skip note at the first step only, with any key
just assigned before it ("W. Press the key to be assigned to down."), and
drops the lit "-"; Alt R says the current step. The user went through the
whole mapping with it on 2026-09-15, button steps and end included, and
reported everything working.

It was not working, and the game is why. Later that day the user found D
moving left in the Tutorial, having pressed it at the step the game draws as
the right arrow. The game fills the rows in their order (up, down, right,
left, A, B, X, Y, right bumper, left bumper, right trigger, left trigger, ...)
while its instructions go up, down, left arrow, right arrow, A, B, X, Y,
right bumper, right trigger, left bumper, left trigger (`ID_SYS_Set_PCset_0209`
on), so left and right arrive swapped, and so do the right trigger and left
bumper steps. The lit row (gold "-") is the one being filled: gold at the third
row while "back" was asked. Proven with Training's Key Display, which draws
the game's reading of each press as pictures and is not in memory: a quiet
watcher polled `GetAsyncKeyState` and saved the Key Display's newest entry a
quarter second after each key, and gave A right arrow, D left arrow, G H J
light, medium and heavy punch, B N light and medium kick, K heavy kick, M all
three punches, comma all three kicks, for keys pressed at the left, right,
..., right trigger and left bumper steps. `name_keyboard_step` now rewrites
the instruction from the lit row (`keyboard_step`, `KEYBOARD_ROW_BUTTONS`)
with what that button does, so the game's swapped pictures are never said.
The Alt R key list was right all along, being read from the rows. That
watcher is the way to check any binding question again: Key Display is the
game's own word on what a press does. Its log also caught the user typing in
the chat window, so only count presses with a frame saved. The user redid the
mapping with the fix the same day ("right", "left", "left bumper button, all
three punches", "right trigger button, heavy kick" in that order), said it
works, and Input2.ini came out W S D A B N G H K J Comma M Period Slash Enter
Escape, the order `buttons.KEYBOARD_SLOT` assumes.

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
game's strings is read too. Both heard in play again on 2026-09-16, the user
confirming the ending read out: "G. The so-called "President of the World"
traveled the globe...", then "Special Artwork: BENGUS". The final opponent's
card after a score line lost its REWARD ("FINAL STAGE. M. BISON. 28000"),
since held-back parts were dropped when found anywhere inside the summary;
now only the summary's own sentences are.

**Demonstrations.** Asked for on 2026-09-15. Choosing one (Challenges,
Demonstrations, VOL. 1, "#01. Basic Controls") loads with a tips screen:
"DEMONSTRATION TIPS" at (135, 257), then a fifth of a second later "TIP 2"
and the tip under the heading's parent, shown for five seconds on the first
load and a tenth of a second on the next. Only the heading was said, nothing
having moved when the tip came. `tips_screen` says heading and tip as one
summary with no settling time, and holds the heading alone back; the headings
of the other modes' tips screens are in `TIPS_HEADINGS`, unseen. Then a page
over the dimmed fight: a title and explanation ("Moving" at (960, 344), its
text at (960, 480)), or later a caption alone at (960, 257) with inputs as
pictures, and about a second later "Start Demonstration" or "Proceed" at (960,
960), waiting for a button, nothing selected. The user sat on the first page
for a minute not knowing it waited. `demonstration_page` says the page's texts
and the button once the button shows. Pictures followed by a comma read
"forward , and" until `describe_inputs` stopped putting a space before
punctuation. The replays between pages show no text of their own, and the
demonstration ends on a Results Menu (Return to Demonstration Select, Go to
Main Menu) that reads as any menu. The user went through every page of the
first demonstrations with it on 2026-09-15 ("Everything during the
demonstrations read out properly"); the tips screen has not been heard yet,
the mod having been restarted after the load.

**Story's Tutorial.** Begun on 2026-09-15. It opens on a scene with
subtitles, speaker at (160, 810) and line at (960, 914) in one holder, which
`ending_summary` had been reading by accident when the line was 60
characters or more ("GOUKEN. Ryu, you'll never find..."; "Ponder my...
fist?" went unsaid). The user's story voices are English, so reading them
talks over the actors; at their request subtitles are said only when turned
on with Alt T (`buttons.subtitles_on`, saved in settings.json, off by
default), every line with its speaker, and never otherwise (`subtitle`,
`Narrator.subtitles`). Ken's line during the fight, "What's wrong? Come over
here!" at (960, 920) in the HUD's movie, is not a subtitle of that shape and
stays unsaid. The fight's instructions sit where a demonstration's caption
does, (960, 257), with no button; `tutorial_instruction` knows them by their
first line, which opens one of the game's `_Stor_Tuto_` strings, and says each
once through `screen_summary`, so Alt R repeats it. The button pictures in
them are the default pad's with the action in brackets, "{button_X} (Light
{punch})", said as the action alone, "pressing either light punch, or light
kick". Between some steps a "TIP" box ("TIP" at (960, 344), the tip at
(960, 480), "Press any button" at (960, 590)) waits for a button, and
`tips_screen` reads it as heading and tip, naming buttons the same way. Each
step done flashes "SUCCESS" at (960, 760), unsaid, the next instruction
following at once. The user went through the whole Tutorial with it on
2026-09-15, every instruction and tip heard, and said it all worked.

General Story (2026-09-22): its scene select reads as chapters already
("Chapter 6, The Black Moon, TIME 0:55"), but with Alt T on its scenes said
nothing. Each line is one text at (960, 920) with no speaker, where the
Tutorial's had one; the game's own hints "  Skip   Select Scene   Hide
Subtitles" come and go at (1222, 1012). Every text in the logs at (960, 920)
is spoken dialogue: these, fighters' lines before a fight in Arcade and
Survival ("My iron body is invincible! So beware!", "Devour-our-our."), and
Ken's in the Tutorial's fight. `subtitle` now takes a line alone there, with
"" for the speaker, so Alt T covers all of them and they stay unsaid with it
off. A scene's first line can come a couple of seconds late: quick reads were
blind for 14 s as that scene opened and a full search found the line.
Confirmed in play by the user the same evening, a scene's lines said one
after another as they came (spoken-log.txt from 22:14). Later that evening
the game froze on answering Yes to "You are about to end the cutscene and
return to Select Scene" (22:22:58), the fourth time that night the prompt was
answered: from then on no text showed anywhere, for the 149 s until the user
closed the game. The user took it for NVDA crashing first, but NVDA's own log
(%TEMP%\nvda-old.log) shows no freeze or error then and a normal exit when
they restarted it at 22:24:55; the silence was the game's. The mod did not
crash either. If the game freezes there again, it is the game.

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

**Or read it.** `buttons.keyboard_keys` took `INPUT_INI` as a default argument,
fixed when the module loaded, so the test that points `INPUT_INI` at a scratch
file read the user's own Input2.ini, and three checks failed once the user
redid their keyboard mapping. It looks the path up when called now.

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

**Counts read once go stale.** `live` took the game's object and name counts
when it attached. Started by hand with the game loaded, fine; started with
the game, it attached during loading, and every object made later was beyond
the count and never searched, so Controller Settings lost its buttons only
when launched from Steam. `Live.refresh_counts` now runs before every search.
Anything cached at attach time is suspect when the mod starts before the game.

**Data made when a screen opens may not follow it.** Controller Settings'
`ButtonConfig` script objects and the player's saved profile both hold the
layout, and neither changes while the user edits; only the screen's own game
object does. Test any source by changing the thing on screen and watching the
source, before building on it.

**Picture loaders point one entry ahead.** On the Home screen and Controller
Settings alike, the URL a picture loader holds (+0x208, or +0x2C8 of its
script object) is the next tile's or row's picture, with gaps. It passed
every check until a screenshot was compared. Name pictures some other way.

**A rule you test alone may pass while the narrator says it twice.** Several
screens this session had a summary or hint and also a raw text that changed
with the screen ("Hold to close", the lit "-" row); `landed_on`'s fallback
said the raw text too. Test through `narrate` with the readings in order, as
the user arrives, and filter what the new line already covers.

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
is kept as the fallback. The gauges moved to memory on 2026-09-28 (below).
What follows is roughly in order of value.

**The session of 2026-09-28 and 29, in short.** It began with a tester's
report that Survival said "Health 0 percent" after every stage (a 1920 by
1200 screen, windowed). The user then said they never wanted a pixel mod
because of exactly that, so the rule since is: replace pixel reading with
memory, do not tune it. Done and confirmed in play, each written up where it
belongs (search for these): Survival's health from the run's own object
(`SurvivalHealth`, the scene's `CurrentState`, since an old run can linger);
Alt H's health, V-Trigger and Critical Art from the fighters' records
(`fight.py`); the player's side from the battle's settings (`Fight.side`,
the one USER), for Alt H and the VS screen, with Versus's list as the
fallback; which record is player 1's by character (`order_by_character`);
the health beeps (`beeps.py`, `App._watch_fight`) at 75, 50, 25 and 10
percent, player 1 left and player 2 right, F5 and Shift F5 for volume (40
to start, steps of 5, 0 off). Also: captures are cut to the game's picture
(`game.picture_box`, `capture.crop`), and the tests no longer write over the
user's Fighter ID. The zip SFV-Access-2026-09-29-6b22afd was built at the
end, the user's go-ahead given; its What's new entry is dated 29 September.

Not yet heard in play, the first things to check: "Health now at X percent"
after a Survival recovery (fixed last, untried); a mirror match, where
characters cannot tell the records apart and `Fight.certain` stays true on
a guess; the beeps online, fixed on the evening of 2026-09-29 (see "Online
the beeps were silent"; the other side does read NET, and Alt H was
confirmed right online by a sighted friend); two players on one
machine, where `Fight.side` says None. Known loose end: `Fight.read` gives
up when the marker sweep finds other than two records. The whole story is
in "The bar is measured off the game's picture", "Survival's health is read
from the run", "The fight's gauges come from the fighters' records", "Which
side is the player's", "Health warning beeps", "Which fighter record is
player 1" and "Two Survival runs in memory". The approach that found the
fighters' records, a watcher matching memory against which bar moved (only
the direction: a full bar measures 83 percent on screen), is there too.

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

   Heard and confirmed up to 2026-09-15: see "What works". The session of
   2026-09-14 and 15 followed the user through starting the game, the shop,
   the Fighter ID and Home change, Guile's, Zangief's, E. Honda's and Blanka's
   command lists, Training's attack data, Controller Settings with Button
   Preview, and Keyboard Settings; the user ended it with everything they had
   tried working. All four that were waiting to be heard (Arcade's final-stage opponent
   card, the Special Artwork credit, `SUMMARY_SETTLE`, the login status line)
   were heard on 2026-09-16. Not yet tried at all:
   character select in Training and Arcade (if one does not read, look for
   its heading in the log; `CHARACTER_SELECT_HEADING` is the only thing
   recognising the screen), the result screen with two players, a draw, or
   Survival, the voice language grid, and anything online past its menus.

   Two more kinds of silent screen turned up in that session, beyond the four
   above. The information is a picture with no text (the Home screen's flags,
   Controller Settings' buttons, Button Preview): look for the thing the
   picture stands for elsewhere in memory, a script object's string or a game
   object's bytes, and when you know what the screen shows right now, search
   all readable memory for those exact bytes (that found the key
   configuration in 20 seconds after a day of pointer chasing). And the
   information is on screen but in the description line or another text that
   selects nothing (keyboard mapping's instructions, the game's short
   messages, status lines, typing into a field): watch that text for changes
   in the narrator.
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
   "Starting with the game" under "Running things". The user put it on hold
   on 2026-09-14 and asked for it on 2026-09-15; the launch options are now
   set in Steam. Sharing the mod with friends is still on hold; do not raise
   it until the user does.

1. **Screens nobody has tried.** Not yet seen from memory: online matches
   past their menus (Ranked, Casual, Battle Lounge rooms, whose password uses
   the same keyboard entry line as the Fighter ID but a field `text_entry`
   does not find); story mode and its chapter select, whose scenes should
   read like the Tutorial's with Alt T; Survival; the player profile;
   the Gallery's contents; Options pages other than Other Settings. Each screen this session took minutes to
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
the screen, and are happy with F keys generally. Alt B, added 2026-09-15,
cycles button names between Xbox, PlayStation and keyboard keys, saved in
`settings.json`. Alt T, added the same day, turns story subtitles on or off,
saved there too.
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
- Keep a screen's arrival short and point to Alt R for a list (Keyboard
  Settings). Button Preview says nothing but a one-line hint on opening, then
  each button's action as it is pressed; the whole layout on opening was too
  much.
- Button names in Xbox, PlayStation or keyboard style, chosen with Alt B; not
  hitbox positions, which they declined. Their hitbox is XInput controller 0,
  and its button they call left trigger is the game's left bumper.
- Frame advantage as "plus 9", "minus 2", "even", after the attack or combo
  is over; a combo said once, never hit by hit.
- A charge is "hold back", the game's word, not "charge".
- Country names in full ("United States"), Fighter ID typing echoed letter by
  letter with capitals named, Alt R spelling it with a count.
- Story subtitles off unless turned on with Alt T: their voices are English
  and reading lines talks over the actors.

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

The 2026-09-14/15 session added some methods worth reusing. A quiet watcher
script in the scratchpad, logging a few texts or bytes every 30 to 100 ms
with millisecond times and no speech or keys, ran beside the mod while the
user played (attack data, key configuration, flag codes); a replay of its log
through `Narrator` tested timing before the user heard it. Screenshots only
work while the game is in front, and the user is usually in the chat window
when you want one, so start a watcher that saves a frame each time something
changes and ask them to go into the game for ten seconds. `live.shared().
find_by_class(name)` finds a game object in a second or two; `tools/
find_properties.py <class>` lists a live object's properties. The pak index
(`tools/pak_index.py`) lists every picture the game has, which is how all 22
command pictures were checked at once.

## Sharing with testers

On 2026-09-15 the user judged it ready for a few friends to test: all NVDA
users, the same Steam Champion Edition, the game in English. They asked for
an installer that does it all in one go. `tools/build_package.py` builds a zip
with its own Python (the base install copied without tests, Tk or docs, plus
the virtual environment's packages less pip and capstone), checked by
importing everything with it in isolated mode; `package/` holds the two batch
files and `Read me first.txt`, the testers' guide. `tools/install.py` copies
the package to `%LOCALAPPDATA%\Programs\SFV Access` (keeping settings,
strings.json, pak_key.txt and snapshots on an update), strips the downloaded
mark from every file so nothing prompts when Steam starts pythonw, closes
Steam with `steam.exe -shutdown` after the player presses Enter, sets the
launch options with `steam_launch_options.change`, and opens Steam again.
Launch options now name the pythonw beside whichever Python runs the tool, so
a development copy keeps its `.venv` and an installed one uses its bundle.

A tester has no strings.json, so `gametext.ensure` makes it the first time the
mod reads any text from the game: the key search over the executable's data
took 2.9 s and the extraction 0.24 s on the user's machine, giving the same
key and the same 50,417 strings. The pak folder comes from the running game's
path, no longer the user's G drive. The repository is private (an
unauthenticated API request gives 404), so testers get the zip, not a clone.

Checked before handing over the first zip (`SFV-Access-2026-09-15-69097bf`,
43 MB): the bundled Python recovered the game's text from the running game
into the staged folder (3.1 s), and `install.main` run with that Python into a
scratch folder, against a made-up localconfig.vdf with Steam, the game and the
mod stubbed as not running, copied the mod and set launch options naming the
installed pythonw. The zip holds no strings.json, key, settings, logs, or the
user's names. Not yet run: the installer on a real machine with Steam open
(closing and reopening Steam), and the mod started by Steam from an installed
copy. The first tester's report is the real check.

**The first tester cannot log in with the launch options (open).** On
2026-09-15 the first tester (Steam in `D:\Games\Steam`, no spaces) got an
"Unable to log into game server" error, heard as "error code 21" (the game's
codes in that family are five characters, like 2100d or 21009). The game logs
in without the mod, and with the mod run from `Start SFV Access.bat` and no
launch options. The same zip installed on the user's machine (Steam closed
during the install, so it was not restarted by the installer) and started from
Steam logged in: text set up, "Logging into the server...", Current Missions.
The process tree there was steam.exe, the bundled pythonw running
`start_with_game.pyw` with the game path unquoted, which started both the mod
and the root StreetFighterV.exe, which started the Win64 one. Nothing under
`--with-game` touches the game, so what differs is the tester's machine. Asked
of the tester: whether the start script went before or after the game, which
security software they run (Kaspersky's application control, Comodo's
containment and the like restrict what an unknown program starts, network
included), the full code, and `console-log.txt` and `spoken-log.txt`. The
tester was happy to start the game first and the start script after, so those
went unanswered and the cause is still unknown; if another tester hits it,
ask them. At that tester's suggestion the installer now asks whether to start
with the game (`ask_yes_no`, Enter takes yes) and always puts a
`Street Fighter V Access.lnk` on the desktop pointing at the start script,
made through `WScript.Shell` with the bundled pywin32 and aimed at the desktop
the registry gives, since OneDrive moves it. Answering no with nothing of ours
set leaves Steam alone and never closes it; answering it the other way on a
later run changes the launch options to match, so either answer can be undone.
The uninstaller removes the shortcut and only closes Steam if the launch
options are ours. All three paths were run with the packaged Python on
2026-09-15: no, yes, then uninstall, each checked against the shortcut and the
launch options. (Piping an answer from PowerShell 5.1 puts a BOM on the first
line, which the prompt rejects; test from bash.) While
testing, the user's launch options point at the installed copy in
`%LOCALAPPDATA%\Programs\SFV Access`; put them back with
`.venv\Scripts\python.exe tools\steam_launch_options.py --apply` (Steam
closed) and delete that folder.

**The extracted folder is cleared after installing.** On 2026-09-24 the user
asked why the mod had two copies of Python. On their own machine that is the
`.venv` launcher starting the real interpreter (see Running things). For
testers, though, the extracted folder kept a whole second copy of the mod
beside the installed one, which is confusing. Now, after copying,
`install.tidy_later` starts the installed copy's pythonw with
`install.py --tidy <folder> <pid>`, detached. It waits for the installer's
process to exit, because Windows holds the Python the installer runs on. Then
it removes from the extracted folder whatever the installed copy also has,
leaving `LEFT_BEHIND`: both batch files, Read me first.txt, What's new.txt
and VERSION.txt. The player's own files (`KEEP`) are never removed. Both
batch files now use the installed copy's Python when the folder has none of
its own. Install prefers the folder's own Python, so a new zip installs over
the old copy. Uninstall prefers the installed copy's. Tested with the built
zip extracted to a scratch folder: the packaged Python ran `install.main`
with Steam, the game and the shortcut stubbed and the target in scratch,
from a hidden console. The folder was down to the five files five seconds
after the window closed, and the tidy process had exited. Both batch files
then reached a scratch installed copy through a stand-in `LOCALAPPDATA`, and
with nothing installed, each said so.

**The bundled Python is kept to its own packages.** A copied Python is a
normal install, not the embeddable one, so it puts `PYTHONPATH` first on
`sys.path` and the player's per-user packages
(`%APPDATA%\Python\Python314\site-packages`) ahead of its own site-packages.
A tester with Python 3.14 and packages installed with `--user` could have
loaded their own numpy and the like in place of the mod's. Now every start of
the bundled Python passes `-E -s` (`slo.ISOLATE`): the three batch files, the
launch options the installer and `--apply` write, the mod started by
`start_with_game.pyw`, and the tidy job. `-I` would also drop the script's
folder from `sys.path`, which `run.py` needs. The venv accepts the switches
too, so the launcher always passes them. `is_ours` goes by the launcher's
name, so launch options from before the switches are still recognised, and a
reinstall replaces them. Until then, a tester's Steam starts the launcher
without them. That's harmless, because it imports only the standard library
and `sfv_access.instance`, and it starts the mod with them.

**The VS screen online names both sides.** It used to call the far side the
opponent, which is right against the CPU and wrong online: the user played a
friend from the second player side on 2026-09-15 and heard their own fighter,
AKIRA, named as the opponent. Nothing on that screen says which side is
theirs (no "YOU" tag; the fight's own display has one, at (167, 90) or
(1834, 90), but that comes after). Each side's Fighter ID sits on the row at
y 901, under the fighter and over the title, and only an online match fills
it, so when both are there `versus_summary` says "jamestoh, CAMMY, V-Skill 1,
V-Trigger 1. Konggster, AKIRA, V-Skill 2, V-Trigger 1. The Grid." and the
user picks out their own ID. At the user's request the mod now learns whose
game it is: `player_card` reads the main menu's own card at (1379, 53), where
across every logged screen only their Fighter ID has ever been drawn (1,930
readings of "Konggster" and nothing else), `buttons.remember_fighter_id` keeps
it in settings.json, and with it known the VS screen names the opponent alone
again, from either side: "Opponent, jamestoh, CAMMY, V-Skill 1, V-Trigger 1.
The Grid." Both sides are still said when the ID is unknown or on neither
side. The game's `KWUserProfileDetails` objects were tried first and gave no
strings.

**Battle Lounge chat.** One text field at the top right holds the whole log,
newest entry first: "[11:45 PM] jamestoh" with the message indented under it,
or a line of its own for what the room does ("... has entered the room.",
"... have begun a match."). Nothing selects it, so the user heard nothing
while their friend typed (2026-09-15). `scaleform.lounge_chat` turns it into
"jamestoh says, Thanks for the match!"; `Narrator` counts the log that is
there on arriving as history and says what appears after it, oldest of the
new entries first. Beware the two texts at (153, 35) and (1567, 35) in a
match: those are the players' titles ("I'm Too Sexy for This Battle",
"Attack Attack Attack!"), not anything anyone sent.

**The online result screen, done.** After a lounge match nothing was
said until Play Again appeared. It carries RESULT and a WIN, so `on_results`
holds and `result_summary` is asked, but the screen is laid out differently
from the offline one and it gives up: "YOU" at (1432, 129) and "PLAYER 2" at
(262, 156), one "WIN" at (274, 231) over the winner's panel, and a TOTAL panel
on the right with "1 WIN", "0 LOSSES" and the rule ("First To 10"), plus the
player's title, Fight Money, EXP and levels. Dumps of both are at
scaleform-log.txt 23:43:44 (won) and the scratchpad recorder at 23:56:40
(lost) on 2026-09-15: the outcome sits in the same place either way, over the
player's own panel, the screen showing only their side. So
`online_result_summary` says "You lose. Total 1 win, 3 losses. First To 10",
waiting for the totals so it is said whole. It is tried both under
`on_results` and in the general chain, since the first wants the heading and
the outcome in one movie and this screen need not be built that way.

Better still, a match ends with a banner across the middle of the stage, "YOU
WIN" at (960, 540) or "YOU LOSE" at (960, 520), and nothing said it: the user
heard nothing at all after a match until "Play Again". `match_banner` takes a
text of that wording within `MATCH_BANNER_MIDDLE` of the stage's middle, so a
title in a corner cannot pass for one, and `screen_summary` says it.

**A tester's crashes, and the stall dump that caused them.** On 2026-09-16 a
tester reported the mod crashing and sent snapshots (kept in `Friend-Logs/`,
which .gitignore keeps out of the repository, since tester logs carry their
Fighter IDs and chat). No error was logged anywhere, but three of their six
sessions ended partway through writing a thread dump to hang-log.txt, cut off
mid-line, out of 112 dumps; the user's own log had none. The dump was
`faulthandler.dump_traceback_later`, and its threshold had been lowered from
five seconds to two the evening before (097c5b3). It reads every thread's
stack without the interpreter's lock while they run, which Python's
documentation warns can crash, and on the tester's slower machine passes ran
past two seconds constantly: their log is full of "empty check, 0 texts"
passes of about a second, the quick read finding nothing and
`refresh_pages` walking the address space (memory.regions) every
`EMPTY_CHECK`. `App._watch_stalls` now takes only the stuck thread's stack,
through `sys._current_frames` with the lock held, once per long pass. And
`App._install_crash_log` writes whatever kills the mod to crash-log.txt
however it was started (from the desktop shortcut an error reached only the
console window): `faulthandler.enable` for a crash in native code, and
`sys.excepthook` and `threading.excepthook` for errors nothing caught.
`tools/test_watchdog.py` checks both. Still open: why that machine is blind so
often and its empty checks so slow.

**The keys are the mod's only while the game is in front.** RegisterHotKey
takes a combination from every program, so while the mod ran, Alt D stopped
reaching a browser's address bar and the rest did nothing anywhere else; the
user asked on 2026-09-16 for them to work only in the game. `Hotkeys` takes
an `active` condition, and its pump, which now waits with
MsgWaitForMultipleObjects rather than blocking in GetMessage, asks it every
`CHECK_MS` and registers or unregisters the lot to match. The mod passes
`game.in_front`, which looks at the foreground window's process alone rather
than enumerating windows. A clash with another program is found when the keys
are first taken up, not at start, so `App._keys_taken` says it then (once for
each different set), including the "another copy is running" case. F10 now
needs the game in front, which the testers' guide says. The tools still hold
their keys throughout. `tools/test_hotkeys.py` flips the condition and watches
a combination nobody presses get taken and given back.

**Arcade's bonus stage card.** On 2026-09-16 the result screen offering NEXT
STAGE before a bonus stage said nothing: its card, "BONUS STAGE", "PERFECT",
"10000", "Normal" (at (1192, 608) and along y 667), is gold and faded by alpha
alone, exactly as the final opponent's card was, so nothing on it counted as
showing. `_show_final_opponent` now also takes a gold BONUS STAGE under NEXT
STAGE as a card to show; a fighter's name still counts only under FINAL
STAGE, since with two opponents the NEXT STAGE cards show normally. Read live,
arriving says "BONUS STAGE. PERFECT. 10000. Normal." What "Normal" stands
for, without an amount of its own, is not known. The bonus stage itself read
already: its tips, then its barrel count.

Arcade's result screens never said their scores, only the next opponent's
cards; the user heard them with Alt A. Down the left each label has its points
a row lower and further right, the rows slanting ("REWARD" "22140", "TIME"
"1000", "VITALITY" "440", "STRAIGHT VICTORY" "6000", then "SCORE" "+29980"
"158650"); after the bonus stage the first row is "x12" with its points, the
barrels broken, drawn beside a picture. A value with no label above it
("400" at (536, 736)) is left out. `arcade_result_summary` says "REWARD 22140.
TIME 1000. STRAIGHT VICTORY 6000. Score plus 29980, total 158650" (VITALITY
left out at the user's request, `ARCADE_UNSAID`, since it comes back in full
for the next fight) or "12 barrels, 6000. Score plus 6000, total 168270", waiting for the
total, and before the final stage FINAL STAGE follows it. It is tried under
`on_results` and in the general chain, the bonus result having no WIN on it.

The same evening Arcade's VS screen said "Opponent, REWARD, ABIGAIL": the
online change took the word REWARD, on the CPU's side of the name row, for a
Fighter ID. `_versus_player` now refuses anything the game has as text and
bare numbers, and the stage rule ignores that row.

**Character Story's chapters.** Story, Character Story, then a fighter:
their chapters down the middle, each a number at x 517 with what sits under
it, and their profile at x 1197 (name, Height, Weight, Job / Affiliation,
Likes). A fight's chapter holds its title, "VS" and the opponent, the name
drawn a few pixels above "VS"; an epilogue its title alone; a locked chapter
"???"; and Oro's chapter 2 nothing but its number. Read in screen order they
came out as "3. Apprentice Alley. DHALSIM. VS", "1. ???" and "2" (2026-09-17).
`story_chapter` makes "Chapter 3, Apprentice Alley, versus DHALSIM", "Chapter
4, Epilogue", "Chapter 1, locked" and "Chapter 2"; `Narrator.step` swaps it in
for the pieces a move names, and Alt R gives it with `story_profile`. The
opponent is told from a title by `fighter_names`, since an epilogue's title
sits in the opponent's column. What Oro's chapter 2 is, with no title drawn,
is not known. Confirmed in play by the user on 2026-09-17.

**Sliders drawn as cells.** Options, Screen Settings, Screen Brightness read as
its label alone (2026-09-17): no text gives its level, unlike Sound Settings'
volumes. Found by dumping every display object under its row before and after
the user pressed right three times: the row holds ten empty track cells 28
pixels apart along x, and two groups laid over them (one showing, which one
swaps with focus), each holding a marker just short of the last filled cell
and one filled cell per level at the track's places, 5 before and 8 after,
the marker moving from 110 to 194. `ScaleformText._slider_level` finds a track
of at least `SLIDER_MIN_CELLS` evenly spaced children within `SLIDER_DEPTH`
of the row and counts the showing group's cells on its places;
`_mark_sliders` gives the selected label its level as a note, "8 of 10", only
when nothing else sits on its row, and remembers rows holding no slider for
`SLIDER_MISS_FOR`. Being a note, arriving says "Screen Brightness. 8 of 10"
and a change says the new level alone, through `landed_on`'s renoted rule. A
walk costs about a millisecond. Other sliders drawn this way should read the
same without more work; none is known yet. Confirmed in play by the user on
2026-09-17.

Adjust Upper and Lower HUD Position, beside it, are quiet by design: choosing
one leaves the menu up with the entry gold, adds a button hint " : Reset
Position" at (510, 596), which `is_button_hint` keeps unsaid, and moves a
sample fight display (names, "Rank ---", "DOJO ID", a 9:59:59.99 timer,
columns of fighters' names) whose position is not text. Offered on 2026-09-17:
announcing the mode with its controls, and saying the position from the
display data as the slider's level is read. The user declined both for now.

**What's new.txt.** At the user's request (2026-09-17) the package carries a
changelog for testers, `package/What's new.txt`, newest version first, in the
guide's plain style, written from the user's side ("Survival: between stages
you hear..."), never commit messages. Add an entry, headed with the day
("17 September 2026"), before building a zip; `build_package` warns when
today has none. Entries written after the fact for the zips of 15 and 16
September came from `git log` between the builds.

**The Message Log.** Asked for on 2026-09-22 with CFN. Every message is one
text of two lines in the column at x 316, "[Sep 16, 2026, 11:57:48 PM]" and
then what it says, newest first, under a tab ("All") with the description
line at the foot. Nothing on it is gold and no layer switches on: the row the
cursor is on is marked only by its text sitting inside an extra container,
one step deeper in the tree than every other row's, found by dumping each
row's objects before and after the user moved down two (the reused row
objects make the diff noisy; the depth is the clean signal). So the screen
said nothing but its description line. `mark_message_log` marks the deeper
row, refusing when every row is alike, as while the list arrives;
`message_log_entry` gives what it says and `_spoken_date` of when it arrived.
Moving says the message alone and Alt R adds the date. Not looked at yet: the
tab above the list, and opening a message.

**CFN's menu is pictures.** Moving through it, the only text that changes is
the description line, so the mod said what an entry does without ever naming
it (2026-09-22). The game's own text holds both, the name immediately above
the description: "Blacklist" at KW/ID_SYS_CFN_Menu_1006 and its description
at _1007, and so on through Favorites, Replays, Pending CFN Friend Requests,
Rival Search, Replay Search, Ranking and Tournament. `_title_index` pairs
every description in the table with the name above it, taking a name that is
short, one line, not a sentence and not what a setting is set to
(`TITLE_NEVER`, after "OFF" claimed a description about sponsored content),
and a description that is a sentence longer than its name; a description two
names claim is dropped. `landed_on` uses it only where it falls back to the
description line, which is reached only when nothing at all is selected, so a
menu whose entries are text names them as before. 209 pairs. Not every menu
is paired this way: Story's "View storylines that focus on each individual
character." has no name key above it, and reads by its own text anyway.

The user then heard half a second between each press and the speech: a move
with nothing selected waits `SETTLE` for the rest of it to arrive, which is
there for the main menu's icon row, where the banner can come a frame after
the description. On a menu of pictures the description line is the whole
move, so `_only_the_description_moved` (the footer is the only text that
changed, and it names an entry) skips the wait; anything else still settles.
Both the naming and the promptness were confirmed in play by the user on
2026-09-22.

The user then asked what "Received 500 ." meant: the coin is drawn there as
"fm", where everywhere else it is "icon_FM", so `ICON_WORDS` had no words for
it and `unknown_pictures` logged it. Both names are in now. One message also
read "Reward: 500 Fight MoneyFM", the game writing its own abbreviation after
an amount it has already drawn the picture for, so `_icon_amounts` drops an
`ICON_ABBREVIATIONS` one and closes up the space a picture leaves before a
full stop.

**A Fighter Profile's match-up.** Pending CFN Friend Requests, a player,
View Fighter Profile: the profile's pages down the left ("Win Ratio", "Win
Ratio by Character", "KO Ratio", "KO'd Ratio", each over Overall, Ranked,
Casual and Battle Lounge entries) read already, the selected one drawn black
on a lit bar and marked by the highlight bar rule. Choosing a KO or KO'd
Ratio page moves the cursor to a match-up picked on two rows, the fighter
(855, 359) over the opponent (855, 408), "All Characters" until one is
picked, and that was silent (2026-09-22). The row the cursor is on is drawn
black and the other white; its highlight bar part shows too, but so do the
arrows, and the left arrow hides on "All Characters" alone, so on that row
two parts differ, pointing at different rows, and the short-list rule could
not decide (a watcher logging the rows' parts while the user moved showed
it). `grid_tiles` also missed the two rows, their container's children
tying on part counts. `_mark_dark_label` takes the one black label in a
group of white ones; no black text shows in any recording or log, the
testers' included. Moving says the name alone; Alt R gives
`matchup_details`, "ZEKU versus RYU. ROUND K.O. Normal Attack 0 ...", each
label with the figure under it, "---" as no data. Only while the cursor is
in the picker, since that is where the rows are marked. Said in the user's
next run the same evening, names on both rows (spoken-log.txt from 21:08:33);
they have not yet said whether it is right, nor tried Alt R.

Win Ratio by Character lists fighters, each row the name at x 644 beside
"WINS: " and "MATCH: " with a percentage and a count under them. The name's
holder has a part more (3 against 2) and the name sits a layer deeper, the
shape of a prompt's chosen answer, so `_mark_by_layers` marked every name
and gave each row a group, which the narrator took for prompts opening:
"WINS: MATCH: 42.86%. 378. ... RYU. KEN. CHUN-LI ..." on every move. It now
refuses when another label in the group is a figure or ends with a colon
(`_label_or_figure`); replayed over every recording, the only prompts it
marks are Yes and No, 6 parts against 2, beside words. Nothing on that page
marks a row yet, and whether the cursor ever goes into the list is unknown.

The profile's pages (2026-09-23). Its tabs (Profile, Discipline and more,
the tab's name at (319, 165)) each list their pages on the left, entries
under a heading at x 350 (three parts a row) and entries that are headings
themselves at x 320 ("Character Level", "Fight Money Earned", four parts);
the highlight bar, the second part, shows on the cursor's row. `grid_tiles`
keeps only the usual size, so the cursor on a heading entry went unsaid;
`highlighted_mixed_row` compares the parts every row has, only when the
one-size rows found nothing, and in every recording it never fires. Its first
version read every fighter out on each page change: a table's row (name,
level, experience bar) is parts of different sizes too, one of them shown
alone, in every row. The rows must now be built alike in the parts they share
(the page list's are all two children each). The user found it working in
play the same day: each page named as the cursor reaches it, and moving
through Character Level's rows says each ("EXP 750/1600. Lv. 12. KEN"). At
the user's request a row lit by its highlight bar is now said as drawn, left
to right, "KEN. Lv. 12. EXP 750/1600": `_mark_highlighted_rows` notes the row
on each text (`TextItem.row`), and `left_to_right_rows` orders them in
`landed_on` and `selection_phrase`; texts within `ROW_SAME_COLUMN` across
keep top to bottom, as a Command List move's name over its command. Not yet
heard. Character
Level lists each fighter beside "Lv. 20" and "EXP 1781/3700" ("Lv. ---",
"EXP ---/---" with no data), which the prompt rule took for answers beside a
chosen one; `_label_or_figure` now counts any text with a digit or "---".
Alt R on any page but the match-up gives `profile_page_details`: the page's
name, then the right-hand panel's texts outside the player's panel (the one
holding Steam ID and Player Level), each label with the figure under it, rows
left to right: "Fight Money Earned. Total Fight Money Earned 378830 Fight
Money". Not yet heard. Moving through a table page's rows (Fight Money Earned
by Character, Battle Count by Character Match-Up) says a row's texts in
screen order, "20000 Fight Money. 7.00%. RYU", "0. 0.00%. VS RYU", the name
last; not changed yet.

Also seen: the player's name at the top, (642, 119), was said once each time
a page was chosen, a mark lasting one read while the page's figures are
swapped out (scaleform-log 21:09:27). Its group at every level has either a
text over `CHOICE_TEXT_LIMIT` or a slot of many texts, so which rule marks it
is not known; a watcher wrapping each rule failed to catch it at 50 ms.

**Random Stage Settings (Battle Settings).** A popup like Favorite Stage's:
a tab at (1196, 237) ("ALL", "SFV Main Stages", switched with LB and RB), a
grid of stage pictures, and the stage's name at (1058, 811), five levels from
the grid where the tab is seven. Nothing was said (2026-09-23). Each tile has
six parts: the cursor's outline (shown on its tile alone), an empty holder,
the picture, and three badge places, the fifth holding a shopping cart for a
stage not owned. A stage left out of random selection has its picture dimmed
to 0.4 and confirm switches it; Dojo is dimmed, and confirm there gives the
toast "Your selection is currently unavailable." A watcher logging tile
states with a screenshot per change while the user moved and switched Ring
of Destiny off and on settled all of this. `selected_tile` wants one tile
drawn differently and several are, so `_mark_picture_grids` falls back to
`highlighted_row`, the one part shown on one tile alone; replayed over every
recorded grid it agrees wherever `selected_tile` decides and decides nowhere
else. On this screen (its description line, `RANDOM_STAGE_LINE`) the stage's
name gets `ticked` from `random_stage_state`, or the note "Not owned", and
`_mark_ticks` no longer overwrites a tick already set. On both stage grids
(`STAGE_GRID_LINES`) the tab is marked too, so switching says it; not on
other picture grids, where a heading could sit at that distance. Arriving
says "ALL. The Grid. Ticked", moving the stage and its state, confirm
"Ticked" or "Not ticked" alone. Confirm on The Grid opened a "Setting" popup
(DEFAULT, Setting 1) that reads as a menu; after it the tile read "The Grid
Alternative", so some stages have versions chosen there. Heard in play the
same day, right but for one burst while moving quickly: "The Grid. Not
ticked", "Dojo. Ticked", each stage with its neighbour's tick. The outline and
the name under the grid change a read apart, so for a read the name was one
tile's and the tick another's. On this screen `_mark_picture_grids` now names
a stage only once tile, name and tab have held for two reads running
(`_grid_pairs`), about a tenth of a second; an unchanged tab stays marked
meanwhile, and a new one waits to be said with its stage, since speech
interrupts itself and the stage would cut it off. The user confirmed moving,
switching and tabs in play the same day.

B (the user's confirm) on some stages opens a "Setting" menu instead of
switching them: a checklist of the stage's versions, DEFAULT and Setting 1,
each with a green tick, both ticked by default, saying which versions "???"
may pick. The tick box is the menu music list's (a holder whose second part
holds three children ticked, two not), but `tick_state` wanted two other rows
alike and this list has one; on this screen (`RANDOM_STAGE_LINE`) it asks for
one. With only Setting 1 ticked, the name under the grid becomes the
version's: "Estate at Noon" for Kanzuki Estate, "The Grid Alternative" for
The Grid. `Content/Stage/DA_StageArrange` (a KWStageArrangeDataAsset) lists
the ten stages with a Setting 1 as pairs of stage numbers, base then version:
3/26, 4/25, 5/39, 8/44, 2/45, 16/58, 52/59, 1/60, 48/61, 10/67 (IntProperty
tags BaseStageId and ArrangeStageId). Each stage folder's
`DA_<code>_Personal` names its stage (TRN The Grid, S25 The Grid
Alternative, KZK Kanzuki Estate, KZ2 Estate at Noon, NZL Forgotten Waterfall,
NZ1 Mysterious Cove, RUS Underground Arena, RU2 Spooky Arena, SHA Shadaloo
Base, SH4 Shadaloo Base at Night, SX2 Suzaku Castle, S17 Suzaku Castle at
Night, ...). What turns a stage number into a folder was not found: not in
any data asset or ini in the paks; the game has a native `LoadStageIdTable`
and `GetStageID`. So "Setting 1" is said as the game says it. The user chose
to leave it so (2026-09-23). If it comes back: the profile's
`KWUserProfileDetails.RandomStageSelectSetting` (a struct `live` does not
read yet) probably holds these settings by stage number, and Kanzuki
Estate's Setting 1 was left unticked, which would pick out its number; or
the user unticks DEFAULT on each of the ten and the name under the grid
gives each version's name.

**CFN's timeline.** Heavy punch in the CFN menu opens a list of what followed
players have done, each entry a date, the player and what happened, one under
another at x 1662 ("Sep 17, 2026, 7:14:31 AM", "jamestoh", "Lost to
Ryosei0308... [Rank Match 1-2]"), a " Move Cursor" hint, no description line.
Nothing was said (2026-09-23). Every entry, seven parts, has its frame and
background switched on, but with alpha 0 except on the cursor's entry (which
also sits 33 pixels left and at full alpha where the rest are at 0.65, the
bottom ones 0.3). `highlighted_row` now counts a part at or under
`PART_SHOWN_ALPHA` as off; replayed over every recorded list (4,993 of them)
it decides exactly as before. `timeline_entry` gives who and what for a move
and the date, as `_spoken_date` says it, on Alt R: "jamestoh. Is online!",
then "September 22, 2026, 9:38 PM". In play the list scrolls under a cursor
that stays put, so saying what changed dropped the player when two entries in
a row were one player's, the event when it was the same event, and all of it
when only the date differed (spoken-log.txt from 14:56:21). `Narrator.step`
now says the entry whole whenever it is another, once it has held for a read
(`timeline_seen`, `timeline_said`), and drops the entry's own texts from
anything else said. Confirmed in play by the user the same day, every entry
said whole, repeats included.

**Replay controls.** A replay (CFN, Replays) shows its controls at (510, 902)
for five seconds as playback starts or resumes, as button pictures each
before what it does: button_lt "Previous Scene", button_lb and button_rb side
by side "Change Playback Speed", button_y "Pause"; with the speed changed,
"Return to Normal Playback" is added; paused, "1 Frame Forward" and "Resume".
Controller pictures are silent everywhere (`SILENT_PICTURES`), so the line
said what the buttons do and not which (2026-09-23). `_with_pictures` now
notes each pad picture with the words after it (`TextItem.buttons`, by
DocView in `hint_buttons`), leaving the text as it was so button hints keep
their leading space and stay unsaid on moves elsewhere. `replay_controls`
recognises the line by "Playback" in a label; `button_hint_words` names each
button in the Alt B style, buttons side by side joined by "or": "L2, Previous
Scene. L1 or R1, Change Playback Speed. triangle, Pause". The narrator says
that in place of the line as drawn and keeps it while "Ver. 07.002" (the
replay's recorded version, (960, 174), `in_replay`) shows, so Alt R gives it
at any point in the replay, after anything else and not in the pause menu.
The pictures were caught by a watcher that had to use full reads: quick
reads without the page refresh thread missed the line. The user found Alt R
working; the line's arrival mid-replay went unsaid, being no change of
selection with nothing selected, so the narrator said it whenever it appeared
or changed. The user found that too much, at every resume, pause and change
of speed, and asked for it once: now said the first time it appears in a
replay (`controls_announced`, reset once `in_replay` is false), and Alt R
gives the current line at any time. Confirmed in play by the user the same
day.

**Next, at the user's request (2026-09-22): the menus inside CFN's tabs.**
The tabs themselves now read, but nothing under them has been looked at:
Favorites, Replays, Pending CFN Friend Requests, Blacklist, Rival Search,
Replay Search, Ranking and Tournament. Expect more screens whose entries
carry no text, as the menu itself did, and lists whose cursor is marked by
structure rather than colour, as the Message Log's is. Also still open there:
the tab above the message list, and opening a message.

## Running things

Setup from a clean clone is in `SETUP.md`. Since 2026-09-15 the user's mod
starts with the game from Steam (see "Starting with the game" below), with no
console window: what it prints goes to `snapshots/console-log.txt`, and what
it reads and says to `scaleform-log.txt` and `spoken-log.txt` as before. To
have the user run a change, ask them to press F10 and start `Start SFV
Access.bat` (the game can stay open), or quit the game and launch it again.
Day to day:

```bash
.venv\Scripts\python.exe run.py
```

```bash
.venv\Scripts\python.exe tools\test_screens.py
```

The other suites are `selftest.py`, and `test_correction.py`, `test_learning.py`,
`test_memory.py`, `test_scaleform.py`, `test_launch.py`, `test_fight.py` and `test_beeps.py` under `tools/`. All
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
`"<repo>\.venv\Scripts\pythonw.exe" -E -s "<repo>\start_with_game.pyw" %command%`,
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
the stand-in ended, mutex released. On 2026-09-15, with the user's go-ahead
and the game and mod closed, Steam was shut down with `steam.exe -shutdown`,
`--apply` run (the copy is `localconfig.vdf.before-sfv-access`), and Steam
started again; the launch options were still there once it was up. Not yet
heard from a real launch. `--remove`, with Steam closed, takes it out.
The user then launched from Steam: the mod started and read, but
Controller Setting said no buttons, where started by hand it had. A fresh
process found `WSKeyConfigGFxPlayer_1` in a second, so the mod's own `live`
cache was at fault; the likely cause, not reproduced, is that started with
the game, the pixel fallback's character select lookup built `live`'s name
table while the game was still loading, and a name or class not found was
cached as missing for the whole session. Misses are now looked for again
after `live.MISS_RETRY` (15 s), and `KeyConfig` notes in the screen log
whether it found the object, found none showing, or failed and why. That was
not it, or not all of it: the next launch logged "0 instances" on Versus's
Controller Settings while a fresh process found the class. The real fault was
that `live` took the object and name counts once, on attaching; started with
the game it attaches while the game loads, so every object made later lay
beyond the count and was never scanned. `Live.refresh_counts` reads both
counts again (the flat array's count at +8, the name table's after its chunk
table) before each class search, instance search and name table read. In
Versus the key configuration objects exist only while their screen is open
(`WSVersusBattleSettingGFxPlayer.KeyConfigGFxPlayers` +0x4C8 is null after);
with two players' screens open, `KeyConfig` would take the first with a
movie, which may be the wrong player's. Confirmed by the user on 2026-09-15:
started with the game from Steam, Controller Settings reads each button
again.
