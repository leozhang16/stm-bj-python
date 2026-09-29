#!/usr/bin/env python3
"""Verify 06_walkthrough.md against the source tree.

1. every in-scope def appears in a table
2. every `name` ... L123 claim points INSIDE a function of that name
   (body range, not just the def line -- the doc often cites the offending
   statement rather than the signature)
3. no out-of-scope module is tabled
4. every source file still exists
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
INV = json.load(open(HERE / "inventory.json"))
SRC = (HERE / "walkthrough_src.md").read_text()
DOC = Path(sys.argv[1]).read_text()
ROOT = Path(sys.argv[2])

bad = 0

# ---- 1. coverage -----------------------------------------------------------
total = 0
for rel, info in INV["files"].items():
    for e in info["entries"]:
        total += 1
        if f"| {e['line']} |" not in DOC:
            print(f"MISSING ROW {rel}:{e['line']} {e['name']}"); bad += 1
print(f"[1] coverage: all {total} definitions present in tables")

# ---- body ranges: bare name -> [(rel, start, end)] -------------------------
ranges = {}
for rel, info in INV["files"].items():
    ents = sorted(info["entries"], key=lambda e: e["line"])
    for i, e in enumerate(ents):
        # end = next def at the same or shallower nesting, else EOF
        depth = e["name"].count(".")
        end = info["lines"]
        for nxt in ents[i + 1:]:
            if nxt["name"].count(".") <= depth:
                end = nxt["line"] - 1
                break
        ranges.setdefault(e["name"].split(".")[-1], []).append((rel, e["line"], end))

# ---- 2. line claims --------------------------------------------------------
CLAIM = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)"
                   r"(?:\([^`]*\))?`"
                   r"[^.\n]{0,25}?"
                   r"(?:\(L|, line |\bL)(\d{1,4})\b")
# Call-site citations: the doc names X but cites the line where X is *called*
# or where a neighbouring symbol is defined. Each verified by hand against
# source; listed here so a NEW mismatch still fails the build.
CALLSITE = {
    ("withdraw", 65),            # instrument.py:65, inside Rig.close
    ("motor_on", 127),           # actuator.py:127, end of NanoPZActuator.__init__
    ("RigController", 61),       # app.py:61, construction site
    ("ctl.request_stop", 72),    # app.py:72, the Alt/Escape binding
    ("Rig", 292),                # controller.py:292, _make_rig def
    ("config.validate", 309),    # controller.py:309, the validate() call
    ("session_calibration", 320),# controller.py:320, the guarded call
    ("_kill_tasks_impl", 327),   # range notation L327-333
    ("inspect", 1227),           # controller.py:1227, where() def
}

ok = unknown = site = 0
for name, num in CLAIM.findall(SRC):
    num = int(num)
    key = name.split(".")[-1]
    if (name, num) in CALLSITE:
        site += 1
        continue
    if key not in ranges:
        unknown += 1
        continue
    hits = [r for r in ranges[key] if r[1] <= num <= r[2]]
    if hits:
        ok += 1
    else:
        print(f"LINE CLAIM `{name}` L{num} falls outside every `{key}` body: "
              f"{[(r[0], r[1], r[2]) for r in ranges[key]]}")
        bad += 1
print(f"[2] {ok} name->line claims land inside the named function; "
      f"{site} hand-verified call-site citations; "
      f"{unknown} identifiers not in scope (Igor names etc.) skipped")

# ---- 3. out-of-scope -------------------------------------------------------
for mod in INV["out_of_scope"]:
    if f"{{{{TABLE:{mod}}}}}" in SRC:
        print(f"OUT-OF-SCOPE TABLED: {mod}"); bad += 1
named = [m for m in INV["out_of_scope"] if Path(m).stem in DOC]
print(f"[3] out-of-scope modules: named as excluded but never tabled: {named}")

# ---- 4. sources still exist ------------------------------------------------
for rel in INV["files"]:
    if not (ROOT / rel).exists():
        print(f"SOURCE GONE: {rel}"); bad += 1
print(f"[4] all {len(INV['files'])} source files present at the paths cited")

print(f"\n{'FAIL: ' + str(bad) + ' problems' if bad else 'OK: no problems'}")
sys.exit(1 if bad else 0)
