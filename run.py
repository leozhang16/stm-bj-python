#!/usr/bin/env python3
"""Dispatcher: run any experiment in this folder by name.

    python run.py list
    python run.py constant_bias --simulate -n 200
    python run.py iv_sweep --simulate -n 20
    python run.py 03 --simulate            # numbers work too

Each experiment lives in experiments/<NN>_<name>/run_experiment.py and is a
standalone script -- this file only finds it and hands over the remaining
arguments, so ``python experiments/03_iv_sweep/run_experiment.py --simulate``
is always equivalent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE / "experiments"


def discover() -> dict[str, Path]:
    out = {}
    for d in sorted(EXPERIMENTS.iterdir()):
        if d.is_dir() and (d / "run_experiment.py").exists():
            number, _, name = d.name.partition("_")
            out[name] = d
            out[number] = d
    return out


def main(argv: list[str]) -> int:
    table = discover()
    if not argv or argv[0] in ("list", "-h", "--help"):
        print(__doc__)
        print("  gui                      The Igor panels (python run.py gui --simulate)")
        print("Experiments:")
        seen = set()
        for d in sorted(set(table.values()), key=lambda p: p.name):
            if d.name in seen:
                continue
            seen.add(d.name)
            first = (d / "README.md").read_text(encoding="utf-8") \
                .splitlines()[0].lstrip("# ") if (d / "README.md").exists() \
                else ""
            print(f"  {d.name:<24} {first}")
        return 0

    key = argv[0]
    if key == "gui":
        # The Igor panels. ``python run.py gui --simulate`` == ``python gui.py --simulate``
        return subprocess.call([sys.executable, str(HERE / "gui.py"), *argv[1:]])
    if key not in table:
        print(f"unknown experiment {key!r}; try: python run.py list")
        return 2

    script = table[key] / "run_experiment.py"
    return subprocess.call([sys.executable, str(script), *argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
