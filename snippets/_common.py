"""Shared helpers for the stmlab snippets. Not part of the package.

Every snippet is standalone and runnable:

    cd python_code_entire_igor
    python snippets/01_numbers.py

They import ``stmlab`` from the parent directory, so the path insertion
below lets them run from anywhere.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _check_dependencies():
    """Fail with an instruction, not a traceback.

    The snippets need numpy (and h5py for 07). A bare ModuleNotFoundError
    six frames deep inside the package tells you nothing about which
    interpreter to use instead, which is the only thing you need to know.
    """
    import importlib.util
    missing = [m for m in ("numpy", "h5py")
               if importlib.util.find_spec(m) is None]
    if not missing:
        return

    venv = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32"
                             else "bin/python")
    script = Path(__file__).resolve().parent / \
        (Path(sys.argv[0]).name or "01_numbers.py")

    print(f"This interpreter is missing: {', '.join(missing)}\n")
    print(f"  interpreter: {sys.executable}")
    print(f"  snippet:     {script.name}\n")

    # ONE absolute command. An earlier version printed a `cd` line followed
    # by a relative command, and running only the second line -- which is
    # what anyone does -- fails with "no such file or directory".
    if venv.exists():
        print("Use the project virtualenv. Copy this whole line:\n")
        print(f"    {venv} {script}\n")
        print("It is absolute, so it works from any directory.")
    else:
        print("Create the project virtualenv first. Copy these three lines:\n")
        print(f"    cd {ROOT}")
        print("    python3 -m venv .venv")
        print("    ./.venv/bin/pip install -r requirements.txt\n")
        print("then run:\n")
        print(f"    {venv} {script}")
    print("\n(On macOS, plain `pip install` into the system Python fails with")
    print(" 'externally-managed-environment' -- the venv is the way.)")
    raise SystemExit(1)


_check_dependencies()

OUT = ROOT / "snippets" / "figures"


def rule(title=""):
    print(f"\n{'-' * 72}")
    if title:
        print(title)
        print('-' * 72)


def sim_config():
    """A RigConfig wired for the simulator, with a second card pretended.

    ``low_res_device`` is set so the EChem and X-piezo snippets can run: in
    simulate nothing touches it, but the modules refuse when it is None,
    which is exactly the refusal you would get on this one-card rig.
    """
    from stmlab.config import RigConfig
    cfg = RigConfig()
    cfg.simulate = True
    cfg.channels.low_res_device = "Dev2"
    cfg.actuator.kind = "simulated"
    return cfg


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    print(f"\n  wrote {path.relative_to(ROOT)}")


def have_matplotlib():
    import importlib.util
    if importlib.util.find_spec("matplotlib") is not None:
        return True
    print("\n  (matplotlib not installed; skipping the plot)")
    return False
