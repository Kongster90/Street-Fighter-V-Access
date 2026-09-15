"""Check starting with the game: the launcher, the single copy check, closing
with the game, and the edit to Steam's launch options.

Nothing here starts the mod or the game, or touches Steam's real files. The
launcher's process starts are replaced, its log is pointed at a scratch file,
and the Steam edits run on text built here.
"""

import importlib.machinery
import importlib.util
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import instance  # noqa: E402
from sfv_access.app import GAME_GONE_SECONDS, GAME_WAIT_SECONDS, GameWatch  # noqa: E402
from tools import steam_launch_options as slo  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


# ------------------------------------------------------------ closing with the game
w = GameWatch(started=0.0)
check("waits for the game to start", w.step(False, GAME_WAIT_SECONDS - 1) is None)
check("gives up if it never starts", w.step(False, GAME_WAIT_SECONDS) == "never started")

w = GameWatch(started=0.0)
w.step(False, 5.0)
w.step(True, 10.0)
check("stays while the game runs", w.step(True, 500.0) is None)
check("stays through a moment's absence", w.step(False, 500.0 + GAME_GONE_SECONDS - 0.5) is None)
w.step(True, 503.0)
check("the game coming back starts the count again", w.step(False, 503.0 + GAME_GONE_SECONDS - 0.5) is None)
check("closes once the game has gone", w.step(False, 503.0 + GAME_GONE_SECONDS) == "closed")
check("a long game never counts as not starting", GameWatch(0.0).step(True, 10_000.0) is None)

# -------------------------------------------------------------------- one copy only
name = f"Local\\StreetFighterVAccessTest{id(w)}"
check("an unclaimed name is not running", not instance.already_running(name))
holder = subprocess.Popen(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, sys.argv[1]); from sfv_access import instance; "
     "instance.claim(sys.argv[2]); print('ready', flush=True); sys.stdin.read()",
     str(ROOT), name],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
)
check("another process's claim is seen", holder.stdout.readline().strip() == "ready"
      and instance.already_running(name))
holder.stdin.close()
holder.wait(10)
check("the claim ends with the process", not instance.already_running(name))
check("the real name differs from the test's", name != instance.NAME)

# ------------------------------------------------------------------------ launcher
loader = importlib.machinery.SourceFileLoader("start_with_game", str(ROOT / "start_with_game.pyw"))
spec = importlib.util.spec_from_loader("start_with_game", loader)
launcher = importlib.util.module_from_spec(spec)
loader.exec_module(launcher)

scratch = Path(tempfile.mkdtemp(prefix="sfv-launch-test-"))
launcher.LOG = scratch / "console-log.txt"
check("launcher log points at scratch", scratch in launcher.LOG.parents)

started = []
launcher.subprocess = types.SimpleNamespace(
    Popen=lambda command, **kw: started.append(command),
    call=subprocess.call,
    DEVNULL=subprocess.DEVNULL,
    STDOUT=subprocess.STDOUT,
)
running = [False]
launcher.instance = types.SimpleNamespace(already_running=lambda: running[0])

sys.argv = ["start_with_game.pyw", sys.executable, "-c", "raise SystemExit(7)"]
code = launcher.main()
check("runs the game command and returns its exit code", code == 7, str(code))
check("starts the mod told it is with the game",
      len(started) == 1 and started[0][-2:] == [str(ROOT / "run.py"), "--with-game"]
      and started[0][0].lower().endswith("pythonw.exe"), repr(started))

started.clear()
running[0] = True
launcher.main()
check("starts no second copy", started == [])

started.clear()
running[0] = False
sys.argv = ["start_with_game.pyw"]
check("with no game command returns at once", launcher.main() == 0)
check("and starts the mod to stay open", started and started[0][-1].endswith("run.py"), repr(started))

# ------------------------------------------------------------- Steam launch options
SAMPLE = (
    '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
    '\t\t\t\t"apps"\n\t\t\t\t{\n'
    '\t\t\t\t\t"310950"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LastPlayed"\t\t"1789417275"\n'
    '\t\t\t\t\t\t"cloud"\n\t\t\t\t\t\t{\n\t\t\t\t\t\t\t"last_sync_state"\t\t"synchronized"\n'
    '\t\t\t\t\t\t}\n\t\t\t\t\t}\n'
    '\t\t\t\t\t"413150"\n\t\t\t\t\t{\n'
    '\t\t\t\t\t\t"LaunchOptions"\t\t"\\"G:\\\\Steam\\\\Stardew\\\\StardewModdingAPI.exe\\" %command%"\n'
    '\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n'
    '\t"WebStorage"\n\t{\n\t\t"apps"\n\t\t{\n\t\t\t"310950"\n\t\t\t{\n'
    '\t\t\t\t"LaunchOptions"\t\t"not the real place"\n\t\t\t}\n\t\t}\n\t}\n}\n'
)

check("no launch options before", slo.launch_options(SAMPLE) is None)
applied = slo.with_launch_options(SAMPLE, slo.OURS)
check("applied reads back", slo.launch_options(applied) == slo.OURS, repr(slo.launch_options(applied)))
added = [ln for ln in applied.split("\n") if ln not in SAMPLE.split("\n")]
check("adds exactly one line, indented with the game's entries",
      len(added) == 1 and added[0].startswith("\t" * 6 + '"LaunchOptions"'), repr(added))
check("the quotes and backslashes are escaped",
      '\\"' in added[0] and "\\\\pythonw.exe" in added[0], added[0])
check("launch options use the pythonw beside the Python running the tool",
      slo.PYTHONW.parent == Path(sys.executable).parent and slo.PYTHONW.exists(), str(slo.PYTHONW))
check("another game's launch options are untouched",
      "StardewModdingAPI.exe\\\" %command%" in applied)
check("applying twice changes nothing", slo.with_launch_options(applied, slo.OURS) == applied)
check("recognised as ours", slo.is_ours(slo.launch_options(applied)))
check("Stardew's are not ours", not slo.is_ours('"G:\\Steam\\StardewModdingAPI.exe" %command%'))
check("removing restores the file exactly", slo.without_launch_options(applied) == SAMPLE)
replaced = slo.with_launch_options(slo.with_launch_options(SAMPLE, "-old"), slo.OURS)
check("replaces a value rather than adding a second",
      replaced.count('"LaunchOptions"') == SAMPLE.count('"LaunchOptions"') + 1
      and slo.launch_options(replaced) == slo.OURS)
try:
    slo.launch_options('"UserLocalConfigStore"\n{\n}\n')
    check("a file without the game says so", False)
except LookupError:
    check("a file without the game says so", True)

# Changing a real file's launch options, on a scratch copy.
scratch_config = scratch / "localconfig.vdf"
assert scratch in scratch_config.parents
scratch_config.write_text(SAMPLE, encoding="utf-8", newline="")
check("setting on a file says so", slo.change(scratch_config, slo.OURS) == "set")
check("and keeps a copy of the file as it was",
      (scratch / ("localconfig.vdf" + slo.BACKUP_SUFFIX)).read_text(encoding="utf-8") == SAMPLE)
check("setting again says it already is", slo.change(scratch_config, slo.OURS) == "already")
check("taking it out says so, and leaves the file as it was",
      slo.change(scratch_config, None) == "removed" and scratch_config.read_text(encoding="utf-8") == SAMPLE)
other = scratch / "other.vdf"
other.write_text(slo.with_launch_options(SAMPLE, "-dx11"), encoding="utf-8", newline="")
check("another tool's launch options are left alone either way",
      slo.change(other, slo.OURS) == "not ours" and slo.change(other, None) == "not ours"
      and slo.launch_options(other.read_text(encoding="utf-8")) == "-dx11")
never = scratch / "never.vdf"
never.write_text('"UserLocalConfigStore"\n{\n}\n', encoding="utf-8", newline="")
check("an account that never played the game says so", slo.change(never, slo.OURS) == "no game")

# ----------------------------------------------------------------------- installer
from sfv_access import gametext  # noqa: E402
from tools import install  # noqa: E402

check("the paks are found from wherever the game runs",
      gametext.paks_for(r"D:\Games\steamapps\common\StreetFighterV\StreetFighterV\Binaries\Win64\StreetFighterV.exe")
      == Path(r"D:\Games\steamapps\common\StreetFighterV\StreetFighterV\Content\Paks"))
check("the installer's target is its own folder under the player's programs",
      install.TARGET.name == "SFV Access" and install.TARGET.parent.name == "Programs")
package = scratch / "package"
(package / "sfv_access").mkdir(parents=True)
(package / "sfv_access" / "app.py").write_text("new", encoding="utf-8")
(package / "run.py").write_text("new", encoding="utf-8")
installed = scratch / "installed"
(installed / "sfv_access").mkdir(parents=True)
(installed / "sfv_access" / "old_module.py").write_text("old", encoding="utf-8")
(installed / "snapshots").mkdir()
(installed / "snapshots" / "spoken-log.txt").write_text("log", encoding="utf-8")
(installed / "settings.json").write_text("{}", encoding="utf-8")
(installed / "strings.json").write_text("text", encoding="utf-8")
install.copy_package(package, installed)
check("updating replaces the code and keeps the player's settings, game text and logs",
      (installed / "run.py").read_text(encoding="utf-8") == "new"
      and not (installed / "sfv_access" / "old_module.py").exists()
      and (installed / "settings.json").exists() and (installed / "strings.json").exists()
      and (installed / "snapshots" / "spoken-log.txt").exists())
marked = installed / "run.py"
with open(f"{marked}:Zone.Identifier", "w", encoding="utf-8") as fh:
    fh.write("[ZoneTransfer]\nZoneId=3\n")
install.unblock(installed)
try:
    open(f"{marked}:Zone.Identifier", encoding="utf-8").close()
    still_marked = True
except OSError:
    still_marked = False
check("the downloaded mark is taken off installed files", not still_marked and marked.exists())

print()
print("ALL PASS" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
