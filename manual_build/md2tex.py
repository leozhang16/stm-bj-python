#!/usr/bin/env python3
"""Convert the manual's Markdown chapters to LaTeX, in two parts.

Adapted from ../../manual_entire/md2tex.py (the stmlab manual). Same
deliberately small Markdown subset; two additions: chapters are grouped
into \\part{}s, and a figure marker may name a path under manual/
(``!FIG[figures/gui/HighRes.png]{caption}``) as well as a snippets figure
(``!FIG[name.png]{caption}``).

Markdown understood:
    # NN. Title              chapter (the number is stripped)
    ## / ###                 section / subsection
    *italic line* right after the H1   -> the source-note box
    paragraphs, - bullets, 1. numbered items (continuation lines gathered)
    | tables | with a header row
    ``` fenced code (python -> highlighted, anything else -> plain)
    > blockquote             -> key box, or warning box if it contains a warn word
    !FIG[path]{caption}
    `code`, **bold**, *emph*, [text](link) -> text
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "manual"

PARTS = [
    ("Start here: the map of the code", ["05_structure_map"]),
    ("The GUI", [
        "40_gui_overview", "41_gui_lab_flow", "42_gui_main_panel",
        "43_gui_offset_panel", "44_gui_echem_panel", "45_gui_graphs",
        "46_gui_macros", "47_gui_data_files", "48_gui_architecture",
        "49_gui_troubleshooting", "50_gui_quick_reference",
        "51_gui_binding_table"]),
    ("The core: stmlab and the experiments", [
        "00_overview", "01_architecture", "02_config_reference",
        "03_hardware", "04_snippets", "10_constant_bias", "11_push_pull",
        "12_iv_sweep", "13_ac_hold", "14_high_bias_hold", "15_echem_gate_cv",
        "16_lateral_monolayer", "17_bias_series", "20_keithley",
        "21_vzero", "30_quick_reference"]),
]

WARN_WORDS = ("never", "refus", "danger", "damage", "destroy", "warning",
              "must not", "do not", "retract before")


def esc(text: str) -> str:
    spans: list[str] = []

    def stash(m):
        spans.append(r"\texttt{" + tt_esc(m.group(1)) + "}")
        return f"\x01{len(spans) - 1}\x02"

    c = re.sub(r"`([^`]*)`", stash, text)
    c = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", c)      # [text](link) -> text

    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        c = c.replace(a, b)
    c = c.replace("—", "---").replace("–", "--")
    c = c.replace("→", r"$\rightarrow$").replace("×", r"$\times$")
    c = c.replace("±", r"$\pm$").replace("≈", r"$\approx$")
    c = c.replace("µ", r"\textmu{}").replace("μ", r"\textmu{}")
    c = c.replace("Ω", r"$\Omega$")
    c = c.replace("Å", r"\AA{}").replace("ångström", "\\aa{}ngstr\\\"om")
    c = c.replace("∓", r"$\mp$").replace("≥", r"$\geq$").replace("≤", r"$\leq$")
    c = c.replace("₀", r"$_0$").replace("²", r"$^2$").replace("⁹", r"$^9$")
    c = c.replace("“", "``").replace("”", "\'\'")
    c = c.replace("‘", "`").replace("’", "\'")
    c = c.replace("…", r"\ldots{}").replace("·", r"$\cdot$")
    c = c.replace("✓", r"$\checkmark$").replace("✗", r"$\times$")
    c = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", c)
    c = re.sub(r"(?<![\*\w])\*([^*]+?)\*(?!\*)", r"\\emph{\1}", c)

    return re.sub(r"\x01(\d+)\x02", lambda m: spans[int(m.group(1))], c)


BREAK = r"\discretionary{}{}{}"
_MARK = "\x00"


def tt_esc(text: str) -> str:
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        text = text.replace(a, b)
    for after in (r"\_", "/", ".", ","):
        text = text.replace(after, after + _MARK)
    # CamelCase identifiers (CurrentSuppressCheckProc) may break before an
    # inner capital; without this they overflow narrow table cells.
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", _MARK, text)
    return text.replace(_MARK, BREAK)


def convert_table(rows: list[str]) -> str:
    header = [c.strip() for c in rows[0].strip().strip("|").split("|")]
    body = [[c.strip() for c in r.strip().strip("|").split("|")]
            for r in rows[2:]]
    n = len(header)
    # Column widths from the separator row: |---|-------|--| gives 3:7:2.
    dashes = [c.count("-") for c in rows[1].strip().strip("|").split("|")]
    if len(dashes) == n and len(set(dashes)) > 1 and sum(dashes) > 0:
        widths = [0.92 * d / sum(dashes) for d in dashes]
        spec = "@{}" + "".join(
            f">{{\\raggedright\\arraybackslash}}p{{{w:.3f}\\linewidth}}"
            for w in widths) + "@{}"
    elif n == 2:
        spec = "@{}>{\\raggedright\\arraybackslash}p{0.34\\linewidth}" \
               ">{\\raggedright\\arraybackslash}p{0.58\\linewidth}@{}"
    elif n == 3:
        spec = "@{}>{\\raggedright\\arraybackslash}p{0.26\\linewidth}" \
               ">{\\raggedright\\arraybackslash}p{0.30\\linewidth}" \
               ">{\\raggedright\\arraybackslash}p{0.34\\linewidth}@{}"
    elif n == 6:
        # The binding table: identifier, title, path, kind, limits, default.
        widths = (0.21, 0.17, 0.23, 0.10, 0.13, 0.08)
        spec = "@{}" + "".join(
            f">{{\\raggedright\\arraybackslash}}p{{{w:.3f}\\linewidth}}"
            for w in widths) + "@{}"
    else:
        width = 0.92 / n
        spec = "@{}" + "".join(
            f">{{\\raggedright\\arraybackslash}}p{{{width:.3f}\\linewidth}}"
            for _ in range(n)) + "@{}"

    size = "\\small" if n <= 4 else "\\footnotesize"
    out = [f"{size}\\setlength{{\\LTleft}}{{0pt}}\\setlength{{\\LTright}}{{\\fill}}",
           f"\\begin{{longtable}}{{{spec}}}", "\\toprule"]
    if any(header):
        out.append(" & ".join(f"\\textbf{{{esc(c)}}}" for c in header)
                   + " \\\\")
        out.append("\\midrule\\endhead")
    for row in body:
        row = (row + [""] * n)[:n]
        out.append(" & ".join(esc(c) for c in row) + " \\\\")
    out += ["\\bottomrule", "\\end{longtable}", "\\normalsize"]
    return "\n".join(out)


def figure_path(name: str) -> str:
    if "/" in name:
        return "../manual/" + name
    return "../snippets/figures/" + name


def convert(md: str, title: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("\\end{enumerate}" if in_list == "enum"
                       else "\\end{itemize}")
            in_list = False

    while i < len(lines):
        line = lines[i]

        m_fig = re.match(r"^!FIG(L?)\[([^\]]+)\]\{(.*)\}$", line.strip())
        if m_fig:
            close_list()
            landscape = bool(m_fig.group(1))
            path = figure_path(m_fig.group(2))
            if not (HERE / path).exists():
                print(f"warning: {title}: figure not found: {path}",
                      file=sys.stderr)
            if landscape:
                # !FIGL: a wide figure on its own page, rotated to fill it.
                out.append("\\begin{figure}[p]\\centering")
                out.append("\\includegraphics[angle=90,height=0.9\\textheight,"
                           "width=\\linewidth,keepaspectratio]{" + path + "}")
                if m_fig.group(3):
                    out.append("\\\\[4pt]{\\small " + esc(m_fig.group(3)) + "}")
                out.append("\\end{figure}\\clearpage")
            else:
                out.append("\\begin{center}")
                out.append("\\includegraphics[width=0.9\\linewidth]{" + path + "}")
                if m_fig.group(3):
                    out.append("\\\\[2pt]{\\small " + esc(m_fig.group(3)) + "}")
                out.append("\\end{center}")
            i += 1
            continue

        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            close_list()
            style = "py" if lang in ("python", "py") else "out"
            out.append(f"\\begin{{lstlisting}}[style={style}]")
            out.extend(block)
            out.append("\\end{lstlisting}")
            continue

        if line.strip().startswith("|") and i + 1 < len(lines) \
                and set(lines[i + 1].strip()) <= set("|-: "):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            close_list()
            out.append(convert_table(rows))
            continue

        if line.startswith(">"):
            block = []
            while i < len(lines) and lines[i].startswith(">"):
                block.append(lines[i].lstrip(">").strip())
                i += 1
            close_list()
            text = " ".join(b for b in block if b)
            env = "warnbox" if any(w in text.lower() for w in WARN_WORDS) \
                else "keybox"
            out.append(f"\\begin{{{env}}}")
            out.append(esc(text))
            out.append(f"\\end{{{env}}}")
            continue

        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_list()
            level, text = len(m.group(1)), m.group(2)
            m_num = re.match(r"^(\d+)\.\s*", text)
            text = re.sub(r"^\d+\.\s*", "", text)
            if level == 1:
                if m_num:
                    # Chapter numbers in print equal the file numbers, so
                    # "see chapter 47" means the same on disk and on paper.
                    out.append(f"\\setcounter{{chapter}}{{{int(m_num.group(1)) - 1}}}")
                out.append(f"\\chapter{{{esc(text)}}}")
            elif level == 2:
                out.append(f"\\section{{{esc(text)}}}")
            else:
                out.append(f"\\subsection{{{esc(text)}}}")
            i += 1
            continue

        if line.startswith("*") and line.rstrip().endswith("*") \
                and not line.startswith("**") and not line.startswith("* "):
            close_list()
            out.append("\\begin{keybox}\\small "
                       + esc(line.strip().strip("*")) + "\\end{keybox}")
            i += 1
            continue

        m_b = re.match(r"^\s*[-*]\s+", line)
        m_n = re.match(r"^\s*\d+\.\s+", line)
        if m_b or m_n:
            want = "enum" if m_n else True
            if in_list and in_list != want:
                close_list()
            if not in_list:
                out.append("\\begin{enumerate}[leftmargin=*]" if m_n
                           else "\\begin{itemize}[leftmargin=*]")
                in_list = want
            item = [line[m_n.end() if m_n else m_b.end():]]
            i += 1
            while i < len(lines) and lines[i].strip() \
                    and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) \
                    and not lines[i].startswith(("#", ">", "|", "```")):
                item.append(lines[i].strip())
                i += 1
            out.append("\\item " + esc(" ".join(item)))
            continue

        if not line.strip():
            close_list()
            out.append("")
            i += 1
            continue

        close_list()
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() \
                and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) \
                and not lines[i].startswith(("#", ">", "|", "```", "!FIG")) \
                and not (lines[i].startswith("*")
                         and lines[i].rstrip().endswith("*")):
            para.append(lines[i].strip())
            i += 1
        out.append(esc(" ".join(para)))

    close_list()
    return "\n".join(out)


def main() -> int:
    wanted = [c for _, chapters in PARTS for c in chapters]
    missing = [c for c in wanted if not (SOURCE / f"{c}.md").exists()]
    if missing:
        print(f"warning: missing chapters skipped: {missing}", file=sys.stderr)
        if "--strict" in sys.argv:
            return 1
    body = []
    for part_title, chapters in PARTS:
        body.append(f"\\part{{{esc(part_title)}}}")
        for name in chapters:
            if name in missing:
                continue
            md = (SOURCE / f"{name}.md").read_text(encoding="utf-8")
            body.append(f"% ==== {name} ====")
            body.append(convert(md, name))
            body.append("")
    (HERE / "chapters.tex").write_text("\n".join(body), encoding="utf-8")
    print(f"wrote chapters.tex from {len(wanted)} chapters in {len(PARTS)} parts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
