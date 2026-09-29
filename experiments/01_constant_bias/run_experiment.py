#!/usr/bin/env python3
"""Constant-bias STM break-junction acquisition -- thin delegator.

This experiment IS the validated stmlab core: the constant-bias loop that the
whole package was translated and validated against lives in ``stmlab/main.py``
(sub-commands ``run`` / ``check`` / ``summarise`` / ``dump-config`` /
``bringup``).  This script adds nothing of its own; it only maps the
``experiments/<NN>_<name>/run_experiment.py`` folder convention onto that CLI:
if the first argument is not a known sub-command, ``run`` is inserted in
front, so both of these work::

    python run_experiment.py --simulate -n 50          # -> stmbj run ...
    python run_experiment.py summarise data/smoke.h5   # -> stmbj summarise ...

Igor original: ``MeasureBreakJunctions()``, Functions_STMBJ.ipf:1664 (the
acquisition loop), with the ramp from ``CreateInputs`` (:1601), per-trace
capture from ``GenerateTrace`` (:284) and selection from ``TestTrace``
(:1180) -- all already translated inside stmlab.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from stmlab.main import main  # noqa: E402  (path bootstrap must come first)

# Keep in sync with the sub-parsers in stmlab.main.build_parser().
SUBCOMMANDS = ("run", "check", "summarise", "dump-config", "bringup")


def delegated_argv(argv: list[str]) -> list[str]:
    """Map folder-convention argv onto the stmlab.main CLI.

    A leading known sub-command (or a bare help request) passes through
    untouched; anything else is treated as arguments to ``run``.
    """
    if argv and argv[0] not in SUBCOMMANDS \
            and argv[0] not in ("-h", "--help"):
        return ["run", *argv]
    return argv


if __name__ == "__main__":
    raise SystemExit(main(delegated_argv(sys.argv[1:])))
