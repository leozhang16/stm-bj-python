"""Moved to ``stmlab/plots.py``; this name keeps old commands working.

    python rigtests/plots.py <session>.h5 --trace 0
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stmlab.plots import *          # noqa: E402,F401,F403
from stmlab.plots import main       # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
