"""Compare what Igor read from a Python-written day folder with the files themselves.

    python3 igor_scheme_roundtrip_compare.py <day folder> <igor result file>

The Igor side (RoundTrip_IgorScheme.ipf, run through run_compile_test_mac.sh) loads the
folder with the lab's own analysis-macro loaders and writes INFO lines with numbers. This
script reads the same files with igor2 (independent of the stmlab code that wrote them),
recomputes those numbers, and reports PASS/FAIL per quantity. Run it with the repo's venv
python (it has igor2):

    /Users/ly666/STM_Git/python_code_entire_igor_w_GUI/.venv/bin/python -I igor_scheme_roundtrip_compare.py ...
"""
import re
import sys
from pathlib import Path

import numpy as np
from igor2 import binarywave


def load(path):
    w = binarywave.load(str(path))["wave"]
    return np.asarray(w["wData"]), w["wave_header"]


def trace(folder, number):
    """Trace `number` (1-based, day numbering) as the macro's LoadCond gives it."""
    k, c = (number - 1) // 100 + 1, (number - 1) % 100
    blk, _ = load(folder / f"PullOutConductanceBlock_{k}.ibw")
    n = blk.shape[0] - 22
    return blk[:n, c].astype(float), blk[n + 2:, c].astype(float), n


def main(argv):
    folder, result = Path(argv[1]), Path(argv[2])
    text = result.read_text(errors="replace").replace("\r", "\n")
    info = {}
    for line in text.splitlines():
        m = re.match(r"INFO (trace \d+|voltage 1|current 1|hist file|conductance block 1|extension block|block 2): (.*)", line)
        if m:
            info[m.group(1)] = dict(re.findall(r"(\w+)=([-+.\deE]+)", m.group(2)))
    ok_all = True

    def check(what, igor, mine, rel=1e-5, atol=1e-9):
        nonlocal ok_all
        igor, mine = float(igor), float(mine)
        ok = abs(igor - mine) <= atol + rel * abs(mine)
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'} {what}: igor={igor:.7g} python={mine:.7g}")

    for num in (1, 100, 101, 120):
        key = f"trace {num}"
        if key not in info:
            print(f"FAIL {key}: not in Igor's result"); ok_all = False; continue
        g, p, n = trace(folder, num)
        check(f"{key} first", info[key]["first"], g[0])
        check(f"{key} last", info[key]["last"], g[-1])
        check(f"{key} sum", info[key]["sum"], np.sum(g, dtype=np.float64), rel=1e-4)
        if num == 1:
            check("trace 1 N", info[key]["N"], n, rel=0)
            check("trace 1 size_nm (slot 0)", info[key]["size_nm"], p[0])
            check("trace 1 rate (slot 1)", info[key]["rate"], p[1])
            check("trace 1 bias_mV (slot 10)", info[key]["bias_mV"], p[10])
            check("trace 1 conv (slot 9)", info[key]["conv"], p[9])
            check("trace 1 Rs (slot 12)", info[key]["Rs"], p[12])
            check("trace 1 thr (slot 13)", info[key]["thr"], p[13])
    v, hv = load(folder / "PullOutVoltageBlock_1.ibw")
    if "voltage 1" in info:
        # the macro's LoadVoltage drops the last 2 points (its own quirk): compare what remains
        check("voltage 1 first", info["voltage 1"]["first"], v[0, 0])
        check("voltage 1 npnts", info["voltage 1"]["npnts"], v.shape[0] - 2, rel=0)
    c, _ = load(folder / "PullOutCurrentBlock_1.ibw")
    if "current 1" in info:
        check("current 1 first", info["current 1"]["first"], c[0, 0])
    h, hh = load(folder / "PullOutConductanceBlockHist_1.ibw")
    if "hist file" in info:
        check("hist sum", info["hist file"]["sum"], np.sum(h, dtype=np.float64), rel=1e-4)
        check("hist dx", info["hist file"]["dx"], hh["sfA"][0], rel=1e-9)
        check("hist leftx", info["hist file"]["leftx"], hh["sfB"][0], rel=0)
    b, hb = load(folder / "PullOutConductanceBlock_1.ibw")
    if "conductance block 1" in info:
        check("block rows", info["conductance block 1"]["rows"], b.shape[0], rel=0)
        check("block cols", info["conductance block 1"]["cols"], b.shape[1], rel=0)
        print(f"{'PASS' if b.dtype == np.float32 else 'FAIL'} block dtype float32 (is {b.dtype})")
        ok_all &= b.dtype == np.float32
    fails = [l for l in text.splitlines() if l.startswith("FAIL")]
    for l in fails:
        print("IGOR", l)
    ok_all &= not fails
    print("OVERALL", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
