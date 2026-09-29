#!/bin/sh
# Rebuild the stmlab + stmgui manual PDF from the Markdown chapters.
#
# ../manual/*.md is the source of truth. gen_binding_table.py regenerates
# chapter 51 from the code, make_figures.py regenerates the GUI figures
# from a simulated session (needs Tk), md2tex.py converts everything, and
# xelatex runs three times (TOC + refs). The PDF lands in the folder root
# and a copy beside the other two manuals at the project root.
set -e
cd "$(dirname "$0")"
PY=../.venv/bin/python
[ -x "$PY" ] || PY=python3
"$PY" gen_binding_table.py
"$PY" gen_structure.py | grep -v "^  "
if [ "$1" = "--figures" ]; then "$PY" make_figures.py; fi
"$PY" md2tex.py
for i in 1 2 3; do xelatex -interaction=nonstopmode stmgui_manual.tex > /dev/null || true; done
grep -q "^!" stmgui_manual.log && { echo "LaTeX errors:"; grep -A3 "^!" stmgui_manual.log | head -40; exit 1; }
cp stmgui_manual.pdf ../STMLAB_GUI_Manual.pdf
cp stmgui_manual.pdf ../../STMLAB_GUI_Manual.pdf
echo "wrote ../STMLAB_GUI_Manual.pdf and ../../STMLAB_GUI_Manual.pdf ($(grep -c . chapters.tex) lines of LaTeX)"
