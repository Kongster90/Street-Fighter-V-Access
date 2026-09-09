"""Speech output, with several backends tried in order of preference.

Tolk first, because it covers NVDA, JAWS, SuperNova, System Access, ZoomText
and Window-Eyes behind one interface, and falls back to SAPI on its own.
Then the NVDA controller client directly, then accessible_output2's bundled
copy of that same client, then SAPI 5.

Announcements are serialised on a worker thread so a long read can be cut off
by the next hotkey without blocking the caller.
"""

from __future__ import annotations

import ctypes
import os
import queue
import struct
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pe_machine(path: Path) -> str:
    """Read a DLL's target architecture, so a mismatch gets a clear message."""
    try:
        with path.open("rb") as fh:
            head = fh.read(0x400)
        off = struct.unpack_from("<I", head, 0x3C)[0]
        machine = struct.unpack_from("<H", head, off + 4)[0]
    except Exception:
        return "unknown"
    return {0x8664: "x64", 0x14C: "x86", 0xAA64: "arm64"}.get(machine, hex(machine))


_HOST_ARCH = "x64" if ctypes.sizeof(ctypes.c_void_p) == 8 else "x86"


class Backend:
    name = "none"

    def speak(self, text: str, interrupt: bool) -> None: ...
    def silence(self) -> None: ...


class TolkBackend(Backend):
    """github.com/dkager/tolk - one interface over every Windows screen reader."""

    def __init__(self, dll_path: Path) -> None:
        arch = _pe_machine(dll_path)
        if arch != _HOST_ARCH:
            raise OSError(
                f"Tolk.dll is {arch} but Python is {_HOST_ARCH}. "
                f"Use the {_HOST_ARCH} build from the Tolk release."
            )
        # Tolk loads the screen reader client DLLs sitting beside it.
        os.add_dll_directory(str(dll_path.parent))
        self._dll = ctypes.CDLL(str(dll_path))
        self._dll.Tolk_DetectScreenReader.restype = ctypes.c_wchar_p
        self._dll.Tolk_IsLoaded.restype = ctypes.c_bool
        self._dll.Tolk_HasSpeech.restype = ctypes.c_bool
        self._dll.Tolk_Output.restype = ctypes.c_bool
        self._dll.Tolk_Output.argtypes = [ctypes.c_wchar_p, ctypes.c_bool]
        self._dll.Tolk_Silence.restype = ctypes.c_bool
        self._dll.Tolk_Load()
        if not self._dll.Tolk_IsLoaded():
            raise OSError("Tolk_Load failed")
        reader = self._dll.Tolk_DetectScreenReader()
        if not reader and not self._dll.Tolk_HasSpeech():
            raise OSError("Tolk found no screen reader and no speech")
        self.name = f"Tolk ({reader or 'SAPI'})"

    def speak(self, text: str, interrupt: bool) -> None:
        self._dll.Tolk_Output(text, interrupt)

    def silence(self) -> None:
        self._dll.Tolk_Silence()


class NvdaClientBackend(Backend):
    """The NVDA controller client, called directly."""

    def __init__(self, dll_path: Path) -> None:
        arch = _pe_machine(dll_path)
        if arch != _HOST_ARCH:
            raise OSError(f"{dll_path.name} is {arch} but Python is {_HOST_ARCH}")
        self._dll = ctypes.windll.LoadLibrary(str(dll_path))
        if self._dll.nvdaController_testIfRunning() != 0:
            raise OSError("NVDA is not running")
        self.name = "NVDA"

    def speak(self, text: str, interrupt: bool) -> None:
        if interrupt:
            self._dll.nvdaController_cancelSpeech()
        self._dll.nvdaController_speakText(ctypes.c_wchar_p(text))

    def silence(self) -> None:
        self._dll.nvdaController_cancelSpeech()


class AccessibleOutputBackend(Backend):
    def __init__(self) -> None:
        from accessible_output2.outputs.auto import Auto

        self._out = Auto()
        chosen = self._out.get_first_available_output()
        if chosen is None:
            raise OSError("no accessible_output2 backend available")
        self.name = f"accessible_output2 ({type(chosen).__name__})"

    def speak(self, text: str, interrupt: bool) -> None:
        self._out.speak(text, interrupt=interrupt)

    def silence(self) -> None:
        self._out.silence()


def _build_backend(notes: list[str]) -> Backend | None:
    tolk = ROOT / "Tolk.dll"
    if tolk.exists():
        try:
            return TolkBackend(tolk)
        except Exception as exc:
            notes.append(f"Tolk unavailable: {exc}")

    nvda = ROOT / "nvdaControllerClient64.dll"
    if nvda.exists():
        try:
            return NvdaClientBackend(nvda)
        except Exception as exc:
            notes.append(f"NVDA client unavailable: {exc}")

    try:
        return AccessibleOutputBackend()
    except Exception as exc:
        notes.append(f"accessible_output2 unavailable: {exc}")

    return None


class Speaker:
    """Speech on a dedicated thread.

    Everything touching the backend runs on one thread and nothing else does.
    Tolk is not thread-safe, and loading it initialises COM on whichever thread
    calls it, which then stops Desktop Duplication from setting the apartment
    model it needs. Confining it to this thread settles both problems.
    """

    def __init__(self) -> None:
        self.notes: list[str] = []
        self._backend: Backend | None = None
        self._q: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        threading.Thread(target=self._pump, daemon=True).start()
        self._ready.wait(10.0)
        for note in self.notes:
            print(f"[speech] {note}")

    @property
    def backend(self) -> str:
        self._ready.wait(10.0)
        return self._backend.name if self._backend else "none"

    def say(self, text: str, interrupt: bool = True) -> None:
        """Queue `text`. With interrupt=True, drop anything still pending."""
        if not text:
            return
        if interrupt:
            self._drain()
        self._q.put(("say", text, interrupt))

    def say_lines(self, lines, interrupt: bool = True) -> None:
        """Queue several lines separately so each can be cut off."""
        lines = [ln for ln in lines if ln]
        if not lines:
            return
        if interrupt:
            self._drain()
        for i, line in enumerate(lines):
            self._q.put(("say", line, interrupt and i == 0))

    def stop(self) -> None:
        self._drain()
        self._q.put(("silence", "", False))

    def _drain(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    def _pump(self) -> None:
        try:
            self._backend = _build_backend(self.notes)
        except Exception as exc:
            self.notes.append(f"speech setup failed: {exc}")
        finally:
            self._ready.set()

        while True:
            kind, text, interrupt = self._q.get()
            try:
                if self._backend is None:
                    if kind == "say":
                        print(f"[speech] {text}")
                elif kind == "say":
                    self._backend.speak(text, interrupt)
                else:
                    self._backend.silence()
            except Exception as exc:  # never let a speech error kill the loop
                print(f"[speech error] {exc}: {text}")
