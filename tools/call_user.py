"""Get the user's attention and say what is needed, for when they must act.

A two-second beep through the speakers, then the message through Prism, so
NVDA says it, repeated a few times in case they were away. The user asked for
exactly this whenever they need to press a key or do something in the game,
and after hearing it shortened the beep from five seconds and lowered it an
octave, to 440 Hz.
If nothing happens afterwards, stop and ask in the chat whether they did it.

    .venv\\Scripts\\python.exe tools\\call_user.py "Press Alt S in the game, please."
    .venv\\Scripts\\python.exe tools\\call_user.py --times 1 "..."
"""

from __future__ import annotations

import argparse
import sys
import time
import winsound
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.speech import PrismVoice  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("message")
    parser.add_argument("--times", type=int, default=3, help="how often to say it")
    parser.add_argument("--gap", type=float, default=10.0, help="seconds between repeats")
    args = parser.parse_args()

    voice = PrismVoice()
    print(f"speaking through {voice.name}")
    winsound.Beep(440, 2000)
    for i in range(args.times):
        if i:
            time.sleep(args.gap)
        voice.speak(args.message, interrupt=True)
    # Prism hands the text to the screen reader and returns; give it time to finish.
    time.sleep(min(args.gap, 0.08 * len(args.message) + 1))


if __name__ == "__main__":
    main()
