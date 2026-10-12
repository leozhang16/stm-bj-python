"""Moved: the pull-out program is ``pullout.py`` at the top of the repo.

    python pullout.py --simulate --config configs/labpc_rig.json

This file only forwards to it, so the old command keeps working.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pullout import main            # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
