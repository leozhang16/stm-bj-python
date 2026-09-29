"""Make ``import stmlab`` work no matter where pytest is launched from.

The package lives one directory above this ``tests`` folder and is not
installed into the venv; pytest imports conftest before any test module, so
the path insertion here covers the whole suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

import gc        # noqa: E402

import pytest    # noqa: E402


@pytest.fixture(autouse=True)
def _collect_tk_garbage_on_the_main_thread():
    """Finalise Tk objects here, not on the controller's worker thread.

    A Tk Variable's __del__ calls into Tcl. If the cyclic collector runs it
    on the worker thread while the main thread is blocked in a wait, the
    Tcl call waits for a main thread that never services it -- a deadlock
    that showed up as one controller test hanging after the window tests.
    Collecting after every test keeps Tk garbage on the thread that owns Tk.
    """
    yield
    gc.collect()
