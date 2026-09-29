#!/usr/bin/env python3
"""Splice generated function tables into the hand-written walkthrough prose.

Prose file contains {{TABLE:stmlab/trace.py}} placeholders. Each is replaced by
a markdown table of every class/def in that file, straight from inventory.json
(so line numbers and signatures cannot drift from the source).
"""
import json, re, sys
from pathlib import Path

INV = json.load(open(Path(__file__).parent / "inventory.json"))
SRC = Path(__file__).parent / "walkthrough_src.md"
OUT = Path(sys.argv[1])


def esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def cell(s: str, n: int) -> str:
    s = esc(s).strip()
    if len(s) > n:
        s = s[: n - 1].rsplit(" ", 1)[0] + "…"
    return s or "—"


def table(rel: str) -> str:
    info = INV["files"][rel]
    rows = ["| Line | Definition | What it does | Igor |",
            "|---:|---|---|---|"]
    for e in info["entries"]:
        indent = "  " * e["name"].count(".")
        rows.append(
            f"| {e['line']} | {indent}`{esc(e['sig'])}` "
            f"| {cell(e['summary'], 150)} | {cell(e['igor'], 60)} |")
    return "\n".join(rows)


def header(rel: str) -> str:
    info = INV["files"][rel]
    return f"*{info['lines']} lines, {len(info['entries'])} definitions.*"


text = SRC.read_text()
text = re.sub(r"\{\{TABLE:(.+?)\}\}", lambda m: table(m.group(1)), text)
text = re.sub(r"\{\{SIZE:(.+?)\}\}", lambda m: header(m.group(1)), text)
text = text.replace("<!--NEXT-->", "")

missing = re.findall(r"\{\{.+?\}\}", text)
if missing:
    print("UNRESOLVED:", missing, file=sys.stderr)

OUT.write_text(text)

# coverage check
cited = set()
for rel in INV["files"]:
    if f"{{{{TABLE:{rel}}}}}" in SRC.read_text():
        cited.add(rel)
tot = sum(len(INV["files"][r]["entries"]) for r in cited)
allf = set(INV["files"])
print(f"tabled {len(cited)}/{len(allf)} files, {tot} definitions", file=sys.stderr)
if allf - cited:
    print("NO TABLE FOR:", sorted(allf - cited), file=sys.stderr)
print(f"wrote {OUT} ({len(text.splitlines())} lines)", file=sys.stderr)
