#!/usr/bin/env python3
"""Launch the Igor STM-BJ panels.

    python gui.py --simulate          # laptop: simulated rig, no drivers
    python gui.py                     # lab PC: real card, Keithley, NanoPZ
    python gui.py --config my.json    # start from a saved RigConfig

Igor equivalent: Macros > "STM Break Junction Measurement"
(InitializeExperiment, Setup1_STMBJ.ipf:55).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _check_tk() -> None:
    try:
        import tkinter  # noqa: F401
        import _tkinter  # noqa: F401
    except ImportError:
        print("This interpreter has no Tk support.\n"
              "  macOS Homebrew:  brew install python-tk@3.12  (or use the\n"
              "                   python.org installer, which bundles Tk)\n"
              "  Windows:         the python.org installer bundles Tk\n"
              "  Debian/Ubuntu:   sudo apt install python3-tk\n"
              "then recreate .venv with that interpreter.")
        raise SystemExit(1)


if __name__ == "__main__":
    _check_tk()
    from stmgui.app import main
    raise SystemExit(main())
