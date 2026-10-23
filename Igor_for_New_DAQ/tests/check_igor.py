#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_igor.py -- static regression checker for Igor Pro procedure files (.ipf).

    python3 -I check_igor.py <folder> [--baseline <folder>] [--json out.json]
                                      [--no-info] [--port-mode | --no-port-mode]
                                      [--dump-calls] [--dump-defs]

Written for the port in Igor_for_New_DAQ (read PORTING_SPEC.md: sections 5-7 list the
removed globals, waves and functions). Igor's compiler is not available on this Mac, so
this script is the first line of defence. It never modifies a file.

What it does
  * lexes every *.ipf in <folder> (NOT recursive; the tests/ sub-folder is left alone):
    '//' comments (not inside "strings"), "strings" with backslash escapes,
    ';'-separated statements, case-insensitive keywords, CRLF or LF, UTF-8 or Latin-1;
  * check 1  block balance per file (Function/Macro/Window/Menu/Proc/Structure, if/for/
             do-while/switch/try, #if/#endif) with the line of the unmatched opener;
  * check 2  forbidden tokens from the spec (module constant FORBIDDEN) outside comments,
             string literals included (error in port mode, info otherwise);
  * check 3  a definitions index across the folder: functions (param counts), macros/
             windows, constants, globals (Variable/G, String/G), waves created by
             Make/Duplicate ($-indirect targets are recorded as dynamic);
  * check 4  undefined references: proc=Name, CtrlNamedBackground proc=Name,
             Execute "Name()", and identifiers followed by '(' that are neither defined
             in the folder nor in the built-in allowlist (baseline-relative, see below);
             plus argument-count checks against folder definitions and the DAQmx XOP;
  * check 5  NVAR/SVAR to a global no Variable/G / String/G declares (error); 'Wave x'
             and Display/AppendToGraph naming a wave never created by Make/Duplicate
             (warning; baseline-relative); panel controls whose value=/variable= names
             a global or constant that does not exist (error);
  * check 6  K_* constants and the channel Strconstants used but not defined (error);
  * check 7  duplicate local declarations inside one function (warning; info when the
             baseline has the same duplicate);
  * check 8  MXReadAnalogF64(task, t, N, wave) paired with the most recent Redimension/
             Make of that wave in the same function (info), and in port mode: N literal
             1 or 2 on task G_ID1 is an error, N=K_NumAIChans without K_NumAIChans in the
             wave size is a warning;
  * check 9  (port mode) marking audit: counts of [NEWDAQ-REMOVED: Keithley|Actuator|
             LowRes] and [NEWDAQ] lines, '#pragma TextEncoding' on line 1, the [NEWDAQ]
             banner, and [NEWDAQ-REMOVED ...] lines that are not fully commented out;
  * also: #include targets that do not exist, files not reached by any #include, file
             encoding / line-ending notes, statements outside any block.

Baseline-relative checks (--baseline <original folder>)
  The baseline is analysed with the same code. A call to an unknown name is reported
  only when the name WAS defined in the baseline (error: definition removed by the port)
  or NEVER appeared in the baseline (warning: new unknown name). Without --baseline every
  unknown name is an info (Igor's built-in list is huge; the allowlist is small).
  The same idea is used for waves. The REGRESSIONS section lists target findings whose
  key (kind + message, line numbers stripped) does not occur in the baseline.

Port mode is on when --baseline is given or when any file carries a [NEWDAQ] tag;
--port-mode / --no-port-mode override that.

Exit code: 1 if any error in the target folder, else 0.
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

# ---------------------------------------------------------------------------
# Spec constants (PORTING_SPEC.md sections 0, 5, 6, 7)
# ---------------------------------------------------------------------------
FORBIDDEN_TOKENS = [
    # second card / its channels / its read waves
    "dev2", "Dev2",
    "LowResPiezoIn", "LowResCurrentIn", "LowResVoltageIn", "LowResXPiezoOut",
    "LowResCounterElectrodeOut",
    "LowResReadWave", "LowResReadWaveBkgd", "CurrentInLowRes", "VoltageInLowRes",
    "XPiezoVoltage",
    # removed globals (section 5)
    "G_ID2", "G_ID3", "G_ID6", "G_OD5", "G_DeviceUD", "G_BoardUD", "G_KeithleyBiasEnabled",
    "G_ActuatorStepSize", "G_ActuatorCounter", "G_XPiezoPosition", "G_XPiezoVoltage",
    # GPIB / serial XOP operations, thermocouple channels
    "GPIB2", "GPIBWrite2", "NI4882", "VDT2", "VDTWrite2", "VDTOperationsPort2",
    "TCchan4", "TCchan5",
]

# section 7: functions removed by the port (no call may remain outside comments)
REMOVED_FUNCTIONS = [
    "SetUpLRTaskID3", "ClearLRTaskID3", "GetLowHighOffset", "TestVirtualGround",
    "CurrentSuppressCheckProc", "ZeroCheckProc", "ZeroCorrectProc", "SetCurrentSuppress",
    "FindSuppress",
    "SetUpGPIB_Keithley", "LocalGPIB", "RemoteGPIB", "KeithleyFilter", "KeithleyFilterRiseTime",
    "KeithleyBias", "KeithleyBiasVolt",
    "StepActuatorApart", "StepActuatorCloser", "SetupXPiezo", "MoveXPiezo", "MoveXPiezoToZero",
    "StopXPiezo", "LateralEXPT",
]

FORBIDDEN = FORBIDDEN_TOKENS + REMOVED_FUNCTIONS
FORBIDDEN_LOWER = {t.lower() for t in FORBIDDEN}
_forbidden_alts = sorted({t.lower() for t in FORBIDDEN}, key=len, reverse=True)
RE_FORBIDDEN = re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(re.escape(t) for t in _forbidden_alts)
                          + r")(?![A-Za-z0-9_])", re.I)

# DaqMxFunctions.xop (legitimate on the lab PC): name -> arity, inferred from every call site
XOP_FUNCTIONS = {
    "mxcreatetask": 1, "mxcreateaivoltagechan": 4, "mxcreateaovoltagechan": 4,
    "mxcfgsampclktiming": 4, "mxreadanalogf64": 4, "mxwriteanalogf64": 4,
    "mxstarttask": 1, "mxstoptask": 1, "mxcleartask": 1, "mxresetdevice": 1,
}

# Igor built-ins seen in this code base plus common ones (lower case). Igor's real list is
# huge; unknown names are therefore handled baseline-relatively (see module doc).
BUILTIN_ALLOWLIST = {
    # numeric / string functions
    "num2str", "num2istr", "str2num", "numpnts", "dimsize", "dimoffset", "dimdelta", "mean",
    "round", "abs", "floor", "ceil", "trunc", "mod", "exists", "stringmatch", "grepstring",
    "controlnamelist", "getkeystate", "stopmstimer", "startmstimer", "sum", "log", "ln", "exp",
    "sqrt", "sin", "cos", "tan", "atan", "atan2", "poly", "sign", "min", "max", "limit",
    "datetime", "secs2date", "secs2time", "date", "time", "ticks", "strsearch", "strlen",
    "cmpstr", "lowerstr", "upperstr", "itemsinlist", "stringfromlist", "whichlistitem",
    "waveexists", "nvar_exists", "svar_exists", "getrterror", "getrtermessage", "igorinfo",
    "igorversion", "functionlist", "winlist", "winname", "wintype", "nameofwave", "wavename",
    "getwavesdatafolder", "datafolderexists", "getdatafolder", "printf", "sprintf", "fprintf",
    "selectnumber", "selectstring", "numtype", "wavetype", "wavedims", "pnt2x", "x2pnt",
    "leftx", "rightx", "deltax", "waveunits", "note", "replacestring", "removeending",
    "parsefilepath", "uniquename", "cleanupname", "possiblyquotename", "interp", "binarysearch",
    "faverage", "area", "variance", "wavemax", "wavemin", "enoise", "gnoise", "sawtooth",
    "gauss", "chr", "char2num", "num2char", "hcsr", "vcsr", "pcsr", "xcsr", "zcsr",
    "strvarordefault", "numvarordefault", "panelresolution", "screenresolution",
    "getdimlabel", "finddimlabel", "wavelist", "variablelist", "stringlist", "pathlist",
    "indexedfile", "indexeddir", "sinh", "cosh", "tanh", "hypot", "magsqr", "real", "imag",
    "cmplx", "conj", "gammln", "erf", "erfc", "besselj", "factorial", "binomial",
    "wavecrc", "wavehash", "stringbykey", "numberbykey", "removebykey", "replacestringbykey",
    "replacenumberbykey", "addlistitem", "removelistitem", "removefromlist", "sortlist",
    "listmatch", "padstring", "textfile", "specialdirpath", "parsefilepath",
    # operations named in the task's suggested allowlist (never followed by '(' in Igor
    # code, listed so that an odd 'Op(...)' spelling is not reported)
    "findlevels", "findlevel", "wavestats", "curvefit", "histogram", "smooth", "redimension",
    "make", "duplicate", "killwaves", "save", "print", "beep", "doupdate", "dowindow",
    "execute", "sleep", "slider", "button", "checkbox", "setvariable", "valdisplay",
    "groupbox", "tabcontrol", "popupmenu", "modifygraph", "modifypanel", "modifycontrol",
    "modifycontrollist", "display", "appendtograph", "label", "setaxis", "textbox",
    "newpanel", "newpath", "setdatafolder", "setscale", "deletepoints", "controlinfo",
    "ctrlnamedbackground", "pauseupdate", "silent", "setdrawlayer", "open", "close",
    "saveexperiment", "abort",
    # pseudo-functions / special variables that may appear with parentheses
    "v_flag", "p", "q", "r", "x", "y", "z", "inf", "nan", "pi",
}

# Igor control-flow keywords: an identifier followed by '(' that is one of these is not a call
CONTROL_KEYWORDS = {
    "if", "elseif", "else", "endif", "while", "do", "for", "endfor", "switch", "strswitch",
    "endswitch", "case", "default", "return", "break", "continue", "try", "catch", "endtry",
    "function", "macro", "window", "proc", "menu", "submenu", "structure", "endstructure",
    "picture", "end", "endmacro", "static", "threadsafe", "override", "variable", "string",
    "nvar", "svar", "wave", "struct", "funcref", "dfref", "constant", "strconstant",
}

# Strconstant / constant names that must resolve (spec section 2 + K_* pattern)
NAMED_CONSTANTS = {
    "highrespiezoout", "highresbiasout", "highresvoltagein", "highrescurrentin", "piezosensein",
    "counterelectrodeout", "daqdevice", "setupid", "datadir", "setup",
}
RE_KCONST = re.compile(r"(?<![A-Za-z0-9_])(K_[A-Za-z0-9_]+)")

MARK_TAGS = ["[NEWDAQ-REMOVED: Keithley]", "[NEWDAQ-REMOVED: Actuator]",
             "[NEWDAQ-REMOVED: LowRes]", "[NEWDAQ]"]
MARK_REASONS = {"Keithley", "Actuator", "LowRes"}
BANNER = "[NEWDAQ] Ported"

# Waves Igor itself creates (CurveFit, FindLevels, WaveStats, Histogram ...): a 'Wave' to one
# of them is an info, not a warning
AUTO_WAVE_NAMES = {"w_coef", "w_sigma", "w_findlevels", "w_hist", "w_wavestats",
                   "w_paramconfidenceinterval", "w_statsminmax", "w_fitconstants"}
AUTO_WAVE_PREFIXES = ("w_", "m_", "fit_", "res_", "t_")

# block grammar ---------------------------------------------------------------
TOP_KINDS = {"function", "macro", "proc", "window", "menu", "structure", "picture"}
OPENERS = {
    "function": "function", "macro": "macro", "proc": "proc", "window": "window",
    "menu": "menu", "submenu": "submenu", "structure": "structure", "picture": "picture",
    "if": "if", "for": "for", "do": "do", "switch": "switch", "strswitch": "switch", "try": "try",
}
CLOSERS = {
    "end": {"function", "macro", "proc", "menu", "submenu", "picture"},
    "endmacro": {"window", "macro", "proc"},
    "endif": {"if"}, "endfor": {"for"}, "while": {"do"}, "endswitch": {"switch"},
    "endtry": {"try"}, "endstructure": {"structure"},
}
MIDS = {"elseif": {"if"}, "else": {"if"}, "case": {"switch"}, "default": {"switch"},
        "catch": {"try"}}
PP_OPEN = {"#if", "#ifdef", "#ifndef"}
PP_MID = {"#else", "#elif"}
PP_CLOSE = {"#endif"}
TOPLEVEL_OK = {"constant", "strconstant", "#pragma", "#include", "#define", "#undef"}

SEV_ORDER = {"error": 0, "warning": 1, "info": 2}


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
class Finding(object):
    __slots__ = ("file", "line", "severity", "kind", "message", "func")

    def __init__(self, file, line, severity, kind, message, func=None):
        self.file, self.line, self.severity, self.kind, self.message, self.func = \
            file, line, severity, kind, message, func

    # annotations that depend on the baseline comparison itself must not change the key
    _ANNOTATIONS = (" (same in the baseline)", " (new in the port)", " (Igor-created wave)",
                    " (same duplicate exists in the baseline)",
                    " (Igor creates it: CurveFit/FindLevels/WaveStats output)")

    def key(self):
        msg = self.message
        for a in self._ANNOTATIONS:
            msg = msg.replace(a, "")
        msg = re.sub(r"\b(?:line|L)\s*\d+\b", "line N", msg)
        return self.kind + "|" + msg

    def to_dict(self):
        return {"file": self.file, "line": self.line, "severity": self.severity,
                "kind": self.kind, "message": self.message, "func": self.func}


# ---------------------------------------------------------------------------
# Lexing helpers
# ---------------------------------------------------------------------------
def split_comment(line):
    """(code, comment): '//' starts a comment unless inside a double-quoted string."""
    i, n, in_str = 0, len(line), False
    while i < n:
        c = line[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "/" and i + 1 < n and line[i + 1] == "/":
                return line[:i], line[i:]
        i += 1
    return line, ""


def mask_strings(code):
    """Same length as code; the contents of string literals replaced by spaces."""
    out, i, n, in_str = [], 0, len(code), False
    while i < n:
        c = code[i]
        if in_str:
            if c == "\\":
                out.append("  ")
                i += 2
                continue
            if c == '"':
                in_str = False
                out.append(c)
            else:
                out.append(" ")
        else:
            if c == '"':
                in_str = True
            out.append(c)
        i += 1
    return "".join(out)[:n]


def split_statements(code, masked):
    """Split on ';' outside strings/brackets. Returns [(col, stmt, masked_stmt)]."""
    parts, start, depth = [], 0, 0
    for i, c in enumerate(masked):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        elif c == ";" and depth == 0:
            parts.append((start, code[start:i], masked[start:i]))
            start = i + 1
    parts.append((start, code[start:], masked[start:]))
    return parts


def match_bracket(s, i):
    """s[i] is an opening bracket; return index of its match or -1."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = []
    for j in range(i, len(s)):
        c = s[j]
        if c in pairs:
            stack.append(pairs[c])
        elif c in ")]}":
            if not stack or c != stack[-1]:
                return -1
            stack.pop()
            if not stack:
                return j
    return -1


def split_top(s, seps=","):
    """Split s at top level (outside brackets) on any char in seps; drop empty items."""
    items, buf, depth = [], [], 0
    for c in s:
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        if depth == 0 and c in seps:
            item = "".join(buf).strip()
            if item:
                items.append(item)
            buf = []
        else:
            buf.append(c)
    item = "".join(buf).strip()
    if item:
        items.append(item)
    return items


def read_value(s, m):
    """Read a flag value starting at s[m]; returns (value, next_index)."""
    n = len(s)
    if m >= n:
        return "", m
    if s[m] in "([{":
        e = match_bracket(s, m)
        if e < 0:
            return s[m:], n
        return s[m:e + 1], e + 1
    if s[m] == '"':
        e = s.find('"', m + 1)
        e = n - 1 if e < 0 else e
        return s[m:e + 1], e + 1
    k = m
    while k < n and s[k] not in " \t/,":
        k += 1
    return s[m:k], k


def parse_flags(s):
    """s = text after an operation name. Returns ([(flag, value|None)], remainder)."""
    i, n, flags = 0, len(s), []
    while True:
        j = i
        while j < n and s[j] in " \t":
            j += 1
        if j < n and s[j] == "/":
            k = j + 1
            while k < n and (s[k].isalnum() or s[k] == "_"):
                k += 1
            name, val = s[j + 1:k], None
            m = k
            while m < n and s[m] in " \t":
                m += 1
            if m < n and s[m] == "=":
                m += 1
                while m < n and s[m] in " \t":
                    m += 1
                val, k = read_value(s, m)
            flags.append((name, val))
            i = k
            continue
        break
    return flags, s[i:]


def last_path_component(name):
    """root:folder:wave -> wave ; also strips a trailing [..] index."""
    name = name.strip()
    name = re.sub(r"\[.*$", "", name).strip()
    if ":" in name:
        name = name.split(":")[-1].strip()
    return name


def ident_or_none(text):
    m = re.match(r"\s*(" + IDENT + r")\s*$", text)
    return m.group(1) if m else None


def split_top_spans(s, seps=","):
    """Like split_top but returns (start, end) spans of the non-empty items."""
    spans, start, depth = [], 0, 0
    for i, c in enumerate(s):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth = max(0, depth - 1)
        if depth == 0 and c in seps:
            if s[start:i].strip():
                spans.append((start, i))
            start = i + 1
    if s[start:].strip():
        spans.append((start, len(s)))
    return spans


def block_label(e):
    return "'%s%s'" % (e["tok"], (" " + e["name"]) if e.get("name") else "")


def count_params(param_str):
    """'a, b, [c, d]' -> (min=2, max=4, names)"""
    names = []
    optional = 0
    for grp in re.findall(r"\[(.*?)\]", param_str):
        items = [x.strip() for x in grp.split(",") if x.strip()]
        optional += len(items)
        names += [re.sub(r"^&", "", x) for x in items]
    rest = re.sub(r"\[.*?\]", "", param_str)
    req = [x.strip() for x in rest.split(",") if x.strip()]
    names += [re.sub(r"^&", "", x) for x in req]
    return len(req), len(req) + optional, [n.lower() for n in names]


# ---------------------------------------------------------------------------
# Per-file scan
# ---------------------------------------------------------------------------
class FileInfo(object):
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.findings = []
        self.lines = []
        self.encoding_note = None
        self.cr_count = 0
        # definitions
        self.funcs = OrderedDict()      # lname -> dict
        self.macros = OrderedDict()     # lname -> dict  (window/macro/proc)
        self.consts = OrderedDict()     # lname -> dict
        self.globals = defaultdict(list)       # lname -> [(name, line, type)]
        self.waves_created = defaultdict(list)  # lname -> [(name, line, op)]
        self.waves_dynamic = []                 # (expr, line, op, func)
        self.includes = []              # (name, line, local)
        self.pragmas = []               # (name, line)
        # references
        self.nvars = []        # dict(kind, local, target, line, func, dynamic)
        self.wave_decls = []   # dict(local, target, line, func, dynamic)
        self.calls = []        # dict(name, nargs, line, func)
        self.proc_refs = []    # dict(name, control, line, func)
        self.exec_refs = []    # dict(name, line, func)
        self.const_uses = []   # dict(name, line, func)
        self.forbidden_hits = []  # dict(tok, line, func, snippet)
        self.panel_globals = []   # dict(name, line, func, how)
        self.graph_waves = []     # dict(name, line, func, op)
        self.func_events = defaultdict(list)   # func lname -> [events]
        self.func_locals = {}    # func lname -> {lname: [(kind, line)]}
        self.func_params = {}    # func lname -> set of lname
        self.toplevel_stmts = []  # (line, snippet)
        # marks
        self.mark_counts = OrderedDict((t, 0) for t in MARK_TAGS)
        self.has_textencoding_first = False
        self.has_banner = False
        self.bad_tag_lines = []   # (line, snippet) tag line with live code
        self.bad_reasons = []     # (line, reason)
        self.ctx = None

    # -- reading ------------------------------------------------------------
    def read(self):
        with open(self.path, "rb") as fh:
            raw = fh.read()
        self.cr_count = raw.count(b"\r")
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
            self.encoding_note = "file is not valid UTF-8; decoded as Latin-1 (Igor 7+ wants UTF-8 or a #pragma TextEncoding)"
        self.lines = [ln.rstrip("\r") for ln in text.split("\n")]
        if self.lines and self.lines[-1] == "":
            self.lines.pop()

    def add(self, line, severity, kind, message, func=None):
        self.findings.append(Finding(self.name, line, severity, kind, message, func))

    # -- scanning -----------------------------------------------------------
    def scan(self):
        self.read()
        if self.lines:
            self.has_textencoding_first = bool(
                re.match(r"\s*#pragma\s+TextEncoding\b", self.lines[0], re.I))
        stack = []      # block entries
        pp_stack = []   # preprocessor
        for lineno, rawline in enumerate(self.lines, 1):
            for tag in MARK_TAGS:
                if tag in rawline:
                    self.mark_counts[tag] += 1
            if BANNER in rawline:
                self.has_banner = True
            code, comment = split_comment(rawline)
            if "[NEWDAQ-REMOVED" in rawline and code.strip():
                self.bad_tag_lines.append((lineno, rawline.strip()[:90]))
            for m in re.finditer(r"\[NEWDAQ-REMOVED:\s*([A-Za-z]+)\]", rawline):
                if m.group(1) not in MARK_REASONS:
                    self.bad_reasons.append((lineno, m.group(1)))
            if not code.strip():
                continue
            masked = mask_strings(code)
            for col, stmt, mstmt in split_statements(code, masked):
                s, ms = stmt.strip(), mstmt.strip()
                if not s:
                    continue
                m = re.match(r"(?:(?:static|threadsafe|override)\s+)*(#?[A-Za-z_][A-Za-z0-9_]*)", s, re.I)
                tok = m.group(1).lower() if m else ""
                # --- preprocessor blocks
                if tok in PP_OPEN:
                    pp_stack.append((tok, lineno))
                    continue
                if tok in PP_MID:
                    if not pp_stack:
                        self.add(lineno, "error", "block-stray", "'%s' without #if" % tok)
                    continue
                if tok in PP_CLOSE:
                    if pp_stack:
                        pp_stack.pop()
                    else:
                        self.add(lineno, "error", "block-stray", "'#endif' without #if")
                    continue
                # --- block openers / closers / mids
                if tok in OPENERS:
                    kind = OPENERS[tok]
                    name = self._block_name(kind, s, ms)
                    entry = {"kind": kind, "name": name, "line": lineno, "tok": tok}
                    if kind in TOP_KINDS and stack:
                        inner = stack[-1]
                        self.add(lineno, "error", "block-nested",
                                 "%s starts while %s (opened at line %d) is still open: missing closer"
                                 % (block_label(entry), block_label(inner), inner["line"]))
                        while stack:
                            e = stack.pop()
                            self.add(e["line"], "error", "block-unmatched",
                                     "%s has no matching closer" % block_label(e))
                    stack.append(entry)
                    if len(stack) == 1 and kind in TOP_KINDS:
                        self._open_ctx(entry, s)
                    self._analyze(s, ms, lineno, tok)
                    continue
                if tok in CLOSERS:
                    want = CLOSERS[tok]
                    if not stack:
                        self.add(lineno, "error", "block-stray", "'%s' without an open block" % tok)
                    elif stack[-1]["kind"] in want:
                        stack.pop()
                        if not stack:
                            self.ctx = None
                    elif tok in ("end", "endmacro"):
                        # a top-level closer ends the innermost Function/Macro/Window whatever its kind
                        idx = None
                        for k in range(len(stack) - 1, -1, -1):
                            if stack[k]["kind"] in TOP_KINDS:
                                idx = k
                                break
                        if idx is None:
                            self.add(lineno, "error", "block-stray", "'%s' without an open Function/Macro/Window" % tok)
                        else:
                            for k in range(len(stack) - 1, idx, -1):
                                e = stack[k]
                                self.add(e["line"], "error", "block-unmatched",
                                         "%s is not closed before '%s' at line %d" % (block_label(e), tok, lineno))
                            e = stack[idx]
                            if tok == "end" and e["kind"] == "window":
                                self.add(lineno, "warning", "block-style",
                                         "'End' closes %s; Igor accepts it, but this code base closes windows with 'EndMacro'" % block_label(e))
                            else:
                                self.add(lineno, "error", "block-mismatch",
                                         "'%s' cannot close %s opened at line %d" % (tok, block_label(e), e["line"]))
                            del stack[idx:]
                            if not stack:
                                self.ctx = None
                    else:
                        # control-flow closer that does not match the innermost open block
                        top = stack[-1]
                        idx = None
                        for k in range(len(stack) - 1, -1, -1):
                            if stack[k]["kind"] in want:
                                idx = k
                                break
                            if stack[k]["kind"] in TOP_KINDS:
                                break       # never look past the enclosing function
                        if idx is None:
                            self.add(lineno, "error", "block-mismatch",
                                     "'%s' does not match the open block %s (opened at line %d)"
                                     % (tok, block_label(top), top["line"]))
                        else:
                            for k in range(len(stack) - 1, idx, -1):
                                e = stack[k]
                                self.add(e["line"], "error", "block-unmatched",
                                         "%s is not closed before '%s' at line %d" % (block_label(e), tok, lineno))
                            del stack[idx:]
                    if tok == "while":
                        self._analyze(s, ms, lineno, tok)   # the condition may call functions
                    continue
                if tok in MIDS:
                    if not stack or stack[-1]["kind"] not in MIDS[tok]:
                        self.add(lineno, "error", "block-mismatch",
                                 "'%s' is not inside %s" % (tok, "/".join(sorted(MIDS[tok]))))
                    self._analyze(s, ms, lineno, tok)
                    continue
                # --- ordinary statement
                if not stack and tok not in TOPLEVEL_OK:
                    self.toplevel_stmts.append((lineno, s[:80]))
                self._analyze(s, ms, lineno, tok)
        for e in stack:
            self.add(e["line"], "error", "block-unmatched",
                     "%s has no matching closer before end of file" % block_label(e))
        for tok, ln in pp_stack:
            self.add(ln, "error", "block-unmatched", "'%s' has no matching #endif" % tok)

    def _block_name(self, kind, s, ms):
        if kind in ("function", "macro", "proc", "window", "structure", "picture", "submenu"):
            m = re.match(r"(?:(?:static|threadsafe|override)\s+)*\w+(?:\s*/\s*\w+)*\s+(" + IDENT + ")", ms, re.I)
            return m.group(1) if m else None
        if kind == "menu":
            m = re.search(r'"([^"]*)"', s)
            return m.group(1) if m else None
        return None

    def _open_ctx(self, entry, s):
        self.ctx = entry
        lname = (entry["name"] or ("@%d" % entry["line"])).lower()
        entry["lname"] = lname
        self.func_locals.setdefault(lname, defaultdict(list))
        self.func_params.setdefault(lname, set())

    def _ctxname(self):
        if not self.ctx:
            return None
        return self.ctx.get("name") or ("%s@%d" % (self.ctx["kind"], self.ctx["line"]))

    def _ctxl(self):
        return self.ctx["lname"] if self.ctx else "@top"

    # -- statement analysis -------------------------------------------------
    def _analyze(self, s, ms, lineno, tok):
        func = self._ctxname()
        fl = self._ctxl()

        # definitions -------------------------------------------------------
        if tok == "function":
            m = re.match(r"(?:(?:static|threadsafe|override)\s+)*function(?:\s*/\s*\w+)*\s+(" + IDENT
                         + r")\s*\((.*)\)\s*(?::\s*(\w+))?\s*$", ms, re.I)
            if m:
                name = m.group(1)
                pmin, pmax, pnames = count_params(m.group(2))
                d = {"name": name, "line": lineno, "pmin": pmin, "pmax": pmax,
                     "params": m.group(2).strip(), "subtype": m.group(3), "kind": "function",
                     "file": self.name}
                if name.lower() in self.funcs:
                    self.add(lineno, "error", "dup-definition",
                             "function '%s' defined twice in this file (first at line %d)"
                             % (name, self.funcs[name.lower()]["line"]))
                self.funcs[name.lower()] = d
                self.func_params[name.lower()] = set(pnames)
            else:
                self.add(lineno, "warning", "parse", "could not parse Function header: %s" % s[:80])
            return
        if tok in ("macro", "window", "proc"):
            m = re.match(r"(" + IDENT + r")\s+(" + IDENT + r")\s*\((.*?)\)\s*(?::\s*(\w+))?\s*$", ms, re.I)
            if m:
                self.macros[m.group(2).lower()] = {"name": m.group(2), "line": lineno, "kind": tok,
                                                   "subtype": m.group(4), "file": self.name}
            return
        if tok in ("constant", "strconstant"):
            m = re.match(r"(?:static\s+)?(constant|strconstant)(?:\s*/\s*\w+)*\s+(" + IDENT + r")\s*=\s*(.*)$", s, re.I)
            if m:
                self.consts[m.group(2).lower()] = {"name": m.group(2), "line": lineno,
                                                   "kind": tok, "file": self.name,
                                                   "value": m.group(3).strip()}
            # still scan the right-hand side for K_ uses below (rare); skip self reference
            self._scan_forbidden(s, lineno, func)
            return
        if tok == "#include":
            m = re.match(r'#include\s+"([^"]*)"', s, re.I)
            if m:
                inc = m.group(1)
                self.includes.append((inc[1:] if inc.startswith(":") else inc, lineno, inc.startswith(":")))
            return
        if tok == "#pragma":
            m = re.match(r"#pragma\s+(\w+)", s, re.I)
            if m:
                self.pragmas.append((m.group(1), lineno))
            return
        if tok.startswith("#"):
            return

        # globals / locals ---------------------------------------------------
        if tok in ("variable", "string"):
            mg = re.match(r"(variable|string)\s*/\s*G\b(?:\s*/\s*\w+)*\s+(.*)$", ms, re.I)
            if mg:
                for item in split_top(mg.group(2), ","):
                    nm = item.split("=")[0].strip()
                    if nm.startswith("$"):
                        continue
                    nm = last_path_component(nm)
                    if re.match(IDENT + r"$", nm):
                        self.globals[nm.lower()].append((nm, lineno, tok))
            else:
                ml = re.match(r"(variable|string)(?:\s*/\s*\w+)*\s+(.*)$", ms, re.I)
                if ml and self.ctx:
                    for item in split_top(ml.group(2), ","):
                        nm = item.split("=")[0].strip()
                        nm = re.sub(r"^&", "", nm)
                        if re.match(IDENT + r"$", nm):
                            self.func_locals[fl][nm.lower()].append((tok, lineno))
                            if "=" in item and tok == "variable":
                                self.func_events[fl].append(("assign", nm.lower(), item.split("=", 1)[1].strip(), lineno))
            self._scan_calls(ms, lineno, func)
            self._scan_forbidden(s, lineno, func)
            self._scan_consts(s, ms, lineno, func)
            return

        if tok in ("nvar", "svar"):
            m = re.match(r"(nvar|svar)(?:\s*/\s*\w+)*\s+(.*)$", ms, re.I)
            if m:
                for item in split_top(m.group(2), ","):
                    if "=" in item:
                        local, target = item.split("=", 1)
                    else:
                        local = target = item
                    local, target = local.strip(), target.strip()
                    dyn = target.startswith("$")
                    tname = None if dyn else last_path_component(target)
                    self.nvars.append({"kind": tok.upper(), "local": local, "target": tname or target,
                                       "line": lineno, "func": func, "dynamic": dyn})
                    if re.match(IDENT + r"$", local) and self.ctx:
                        self.func_locals[fl][local.lower()].append((tok.upper(), lineno))
            self._scan_forbidden(s, lineno, func)
            return

        if tok == "wave" and re.match(r"wave(?=\s|/)", ms, re.I):
            m = re.match(r"wave(?:\s*/\s*\w+)*\s+(.*)$", ms, re.I)
            if m:
                for item in split_top(m.group(1), ","):
                    if "=" in item:
                        local, target = item.split("=", 1)
                    else:
                        local = target = item
                    local, target = local.strip(), target.strip()
                    dyn = target.startswith("$")
                    tname = None if dyn else last_path_component(target)
                    self.wave_decls.append({"local": local, "target": tname or target, "line": lineno,
                                            "func": func, "funcl": fl, "dynamic": dyn})
                    if re.match(IDENT + r"$", local) and self.ctx:
                        self.func_locals[fl][local.lower()].append(("Wave", lineno))
            self._scan_forbidden(s, lineno, func)
            return

        if tok == "struct":
            return

        # wave-creating / resizing operations --------------------------------
        if tok in ("make", "duplicate", "redimension"):
            rest = ms[len(tok):]
            flags, remainder = parse_flags(rest)
            nval = None
            for fname, fval in flags:
                if fname.upper() == "N":
                    nval = fval
            if tok == "duplicate":
                toks = split_top(remainder, ", \t")
                for t in toks[1:]:
                    if t.startswith("$"):
                        self.waves_dynamic.append((t, lineno, "Duplicate", func))
                    else:
                        nm = last_path_component(t.split("=")[0])
                        if re.match(IDENT + r"$", nm):
                            self.waves_created[nm.lower()].append((nm, lineno, "Duplicate"))
                            self.func_events[fl].append(("dim", nm.lower(), "(copy of %s)" % toks[0], lineno, "Duplicate"))
            else:
                for item in split_top(remainder, ","):
                    if item.startswith("$"):
                        if tok == "make":
                            self.waves_dynamic.append((item, lineno, "Make", func))
                        continue
                    nm = last_path_component(item.split("=")[0])
                    if re.match(IDENT + r"$", nm):
                        if tok == "make":
                            self.waves_created[nm.lower()].append((nm, lineno, "Make"))
                        self.func_events[fl].append(("dim", nm.lower(), nval, lineno, tok.capitalize()))
            self._scan_calls(ms, lineno, func)
            self._scan_forbidden(s, lineno, func)
            self._scan_consts(s, ms, lineno, func)
            return

        if tok in ("display", "appendtograph"):
            rest = ms[len(tok):]
            flags, remainder = parse_flags(rest)
            for t in split_top(remainder, ", \t"):
                tl = t.lower()
                if tl == "as":
                    break
                if tl == "vs" or t.startswith("$") or t.startswith('"'):
                    continue
                nm = last_path_component(t)
                if re.match(IDENT + r"$", nm):
                    self.graph_waves.append({"name": nm, "line": lineno, "func": func, "op": tok})
            self._scan_forbidden(s, lineno, func)
            return

        # generic statement ----------------------------------------------------
        # simple local assignment 'X= expr' (used to expand wave sizes in check 8)
        ma = re.match(r"(" + IDENT + r")\s*=(?!=)\s*(.+)$", ms)
        if ma and self.ctx:
            self.func_events[fl].append(("assign", ma.group(1).lower(), ma.group(2).strip(), lineno))
        # proc= references (controls, CtrlNamedBackground)
        for m in re.finditer(r"\bproc\s*=\s*(" + IDENT + ")", ms, re.I):
            mc = re.match(r"\s*(" + IDENT + r")\s+(" + IDENT + ")", ms)
            control = ("%s %s" % (mc.group(1), mc.group(2))) if mc else s[:30]
            self.proc_refs.append({"name": m.group(1), "control": control, "line": lineno, "func": func})
        # Execute "Name()"
        for m in re.finditer(r"\bexecute(?:\s*/\s*\w+)*\s+\"(" + IDENT + r")\(\)\"", s, re.I):
            self.exec_refs.append({"name": m.group(1), "line": lineno, "func": func})
        # panel controls: value= G_x / variable= G_x / value= #"root:G_x" / #"K_x"
        for m in re.finditer(r"\b(value|variable)\s*=\s*(G_[A-Za-z0-9_]+)\b", ms, re.I):
            self.panel_globals.append({"name": m.group(2), "line": lineno, "func": func,
                                       "how": "%s=" % m.group(1)})
        for m in re.finditer(r"\bvalue\s*=\s*#\"(?:root:)?(" + IDENT + r")\"", s, re.I):
            self.panel_globals.append({"name": m.group(1), "line": lineno, "func": func,
                                       "how": 'value= #"..."'})
        # MX reads / clock config (check 8)
        for m in re.finditer(r"\b(MXReadAnalogF64|MXCfgSampClkTiming)\s*\(", ms, re.I):
            e = match_bracket(ms, m.end() - 1)
            if e > 0:
                args = split_top(ms[m.end():e], ",")
                if m.group(1).lower() == "mxreadanalogf64" and len(args) == 4:
                    self.func_events[fl].append(("read", args[0], args[2], last_path_component(args[3]), lineno))
                elif len(args) == 4:
                    self.func_events[fl].append(("clk", args[0], args[3], lineno))
        # DAQ channel / device arguments (check 6b): must be a Strconstant, literal or local string
        for m in re.finditer(r"\b(MXCreateAIVoltageChan|MXCreateAOVoltageChan|MXResetDevice)\s*\(", ms, re.I):
            e = match_bracket(ms, m.end() - 1)
            if e > 0:
                inner_m, inner_s = ms[m.end():e], s[m.end():e]
                spans = split_top_spans(inner_m, ",")
                want = 0 if m.group(1).lower() == "mxresetdevice" else 1
                if len(spans) > want:
                    a, b = spans[want]
                    self.func_events[fl].append(("chan", m.group(1), inner_m[a:b].strip(), inner_s[a:b].strip(), lineno))
        self._scan_calls(ms, lineno, func)
        self._scan_forbidden(s, lineno, func)
        self._scan_consts(s, ms, lineno, func)

    def _scan_calls(self, ms, lineno, func):
        for m in re.finditer(r"(?<![A-Za-z0-9_$:.])(" + IDENT + r")\s*\(", ms):
            name = m.group(1)
            lname = name.lower()
            if lname in CONTROL_KEYWORDS:
                continue
            before = ms[:m.start()].rstrip().lower()
            if re.search(r"(?:^|\s)(?:function|macro|window|proc)(?:\s*/\s*\w+)*$", before):
                continue    # definition header
            close = match_bracket(ms, m.end() - 1)
            after = ms[close + 1:].lstrip() if close >= 0 else ""
            if after.startswith("=") and not after.startswith("=="):
                continue    # keyword(arg)= form, e.g. ModifyGraph rgb(w)=...
            if close >= 0:
                inner = ms[m.end():close]
                nargs = len(split_top(inner, ",")) if inner.strip() else 0
            else:
                nargs = None
            self.calls.append({"name": name, "nargs": nargs, "line": lineno, "func": func})

    def _scan_forbidden(self, s, lineno, func):
        seen = set()
        for m in RE_FORBIDDEN.finditer(s):
            if m.group(0).lower() in seen:
                continue        # one finding per token per statement
            seen.add(m.group(0).lower())
            self.forbidden_hits.append({"tok": m.group(0), "line": lineno, "func": func,
                                        "snippet": re.sub(r"\s+", " ", s.strip())[:90]})

    def _scan_consts(self, s, ms, lineno, func):
        for m in RE_KCONST.finditer(s):
            self.const_uses.append({"name": m.group(1), "line": lineno, "func": func})
        for m in re.finditer(r"(?<![A-Za-z0-9_])(" + IDENT + ")", ms):
            if m.group(1).lower() in NAMED_CONSTANTS:
                self.const_uses.append({"name": m.group(1), "line": lineno, "func": func})


# ---------------------------------------------------------------------------
# Folder analysis
# ---------------------------------------------------------------------------
class FolderAnalysis(object):
    def __init__(self, folder, port_mode, label):
        self.folder = os.path.abspath(folder)
        self.port_mode = port_mode
        self.label = label
        self.files = []
        self.findings = []
        for p in sorted(glob.glob(os.path.join(self.folder, "*.ipf")), key=lambda x: os.path.basename(x).lower()):
            fi = FileInfo(p)
            fi.scan()
            self.files.append(fi)
        # indexes
        self.funcs, self.macros, self.consts = {}, {}, {}
        self.globals = defaultdict(list)
        self.waves_created = defaultdict(list)
        self.waves_dynamic = []
        for fi in self.files:
            for k, v in fi.funcs.items():
                if k in self.funcs:
                    self.add(fi.name, v["line"], "error", "dup-definition",
                             "function '%s' is also defined in %s (line %d)"
                             % (v["name"], self.funcs[k]["file"], self.funcs[k]["line"]))
                else:
                    self.funcs[k] = v
            for k, v in fi.macros.items():
                if k in self.macros:
                    self.add(fi.name, v["line"], "error", "dup-definition",
                             "%s '%s' is also defined in %s (line %d)"
                             % (v["kind"], v["name"], self.macros[k]["file"], self.macros[k]["line"]))
                else:
                    self.macros[k] = v
            for k, v in fi.consts.items():
                if k in self.consts:
                    self.add(fi.name, v["line"], "error", "dup-definition",
                             "%s '%s' is also defined in %s (line %d)"
                             % (v["kind"], v["name"], self.consts[k]["file"], self.consts[k]["line"]))
                else:
                    self.consts[k] = v
            for k, v in fi.globals.items():
                self.globals[k].extend(v)
            for k, v in fi.waves_created.items():
                self.waves_created[k].extend(v)
            self.waves_dynamic.extend(fi.waves_dynamic)
        self.defined_names = set(self.funcs) | set(self.macros)
        self.call_names = {c["name"].lower() for fi in self.files for c in fi.calls}
        self.uncreated_wave_names = set()
        self.dup_locals = set()
        self.unknown_calls = set()
        # per-file findings
        for fi in self.files:
            self.findings.extend(fi.findings)

    def add(self, file, line, severity, kind, message, func=None):
        self.findings.append(Finding(file, line, severity, kind, message, func))

    # -- checks --------------------------------------------------------------
    def run_checks(self, baseline=None):
        fnames = {fi.name.lower() for fi in self.files}
        included = set()
        includers = set()
        self.add("(folder)", 0, "info", "index",
                 "definitions: %d functions, %d macros/windows, %d constants, %d globals, %d waves created by Make/Duplicate (+%d $-dynamic targets) in %d files"
                 % (len(self.funcs), len(self.macros), len(self.consts), len(self.globals),
                    len(self.waves_created), len(self.waves_dynamic), len(self.files)))
        for fi in self.files:
            F = fi.name
            if fi.encoding_note:
                self.add(F, 1, "info", "file-encoding", fi.encoding_note)
            if fi.cr_count:
                self.add(F, 1, "info", "file-crlf", "CRLF line endings (%d CR bytes); fine for Igor, handled here" % fi.cr_count)
            for ln, snip in fi.toplevel_stmts:
                self.add(F, ln, "warning", "toplevel-statement",
                         "statement outside any Function/Macro/Window block: %s" % snip)
            # includes
            for inc, ln, local in fi.includes:
                if local:
                    if (inc + ".ipf").lower() in fnames:
                        included.add((inc + ".ipf").lower())
                        includers.add(fi.name.lower())
                    else:
                        self.add(F, ln, "error", "include-missing", '#include ":%s" but %s.ipf is not in the folder' % (inc, inc))
                else:
                    self.add(F, ln, "info", "include-external", '#include "%s" refers to an Igor/User Procedures file (not checked)' % inc)
            # check 2: forbidden tokens
            sev = "error" if self.port_mode else "info"
            for h in fi.forbidden_hits:
                self.add(F, h["line"], sev, "forbidden-token",
                         "forbidden token '%s' in %s: %s" % (h["tok"], h["func"] or "top level", h["snippet"]), h["func"])
            # check 4a/4b
            for r in fi.proc_refs:
                if r["name"].lower() not in self.funcs:
                    self.add(F, r["line"], "error", "undefined-proc",
                             "proc=%s (%s) is not a defined function in the folder" % (r["name"], r["control"]), r["func"])
            for r in fi.exec_refs:
                if r["name"].lower() not in self.macros and r["name"].lower() not in self.funcs:
                    self.add(F, r["line"], "error", "undefined-execute",
                             'Execute "%s()" but no Window/Macro/Function %s is defined in the folder' % (r["name"], r["name"]), r["func"])
            # check 4c: calls
            for c in fi.calls:
                ln_ = c["name"].lower()
                if ln_ in FORBIDDEN_LOWER:
                    continue    # already reported by check 2
                if ln_ in self.funcs:
                    d = self.funcs[ln_]
                    if c["nargs"] is not None and not (d["pmin"] <= c["nargs"] <= d["pmax"]):
                        self.add(F, c["line"], "warning", "arg-count",
                                 "%s() called with %d argument(s) but defined with %s (%s) in %s"
                                 % (c["name"], c["nargs"],
                                    str(d["pmin"]) if d["pmin"] == d["pmax"] else "%d..%d" % (d["pmin"], d["pmax"]),
                                    d["params"], d["file"]), c["func"])
                    continue
                if ln_ in self.macros:
                    continue
                if ln_ in XOP_FUNCTIONS:
                    if c["nargs"] is not None and c["nargs"] != XOP_FUNCTIONS[ln_]:
                        self.add(F, c["line"], "warning", "arg-count",
                                 "%s() called with %d argument(s); the DaqMxFunctions XOP takes %d"
                                 % (c["name"], c["nargs"], XOP_FUNCTIONS[ln_]), c["func"])
                    continue
                if ln_ in BUILTIN_ALLOWLIST:
                    continue
                self.unknown_calls.add(ln_)
                if baseline is None:
                    self.add(F, c["line"], "info", "undefined-call",
                             "call to '%s()' which is neither defined in the folder nor in the built-in allowlist" % c["name"], c["func"])
                elif ln_ in baseline.defined_names:
                    self.add(F, c["line"], "error", "call-removed",
                             "'%s()' is called but its definition was removed by the port (it is defined in the baseline)" % c["name"], c["func"])
                elif ln_ not in baseline.call_names:
                    self.add(F, c["line"], "warning", "undefined-call",
                             "new call to unknown name '%s()' (never appears in the baseline: typo, or a built-in missing from the allowlist)" % c["name"], c["func"])
            # check 5: NVAR/SVAR
            for r in fi.nvars:
                if r["dynamic"]:
                    continue
                t = r["target"].lower()
                if t not in self.globals:
                    want = "Variable/G" if r["kind"] == "NVAR" else "String/G"
                    self.add(F, r["line"], "error", "undefined-global",
                             "%s %s= %s: no '%s %s' anywhere in the folder (function %s)"
                             % (r["kind"], r["local"], r["target"], want, r["target"], r["func"]), r["func"])
                else:
                    types = {x[2] for x in self.globals[t]}
                    if r["kind"] == "NVAR" and types == {"string"}:
                        self.add(F, r["line"], "warning", "global-type",
                                 "NVAR %s= %s but %s is declared with String/G" % (r["local"], r["target"], r["target"]), r["func"])
                    if r["kind"] == "SVAR" and types == {"variable"}:
                        self.add(F, r["line"], "warning", "global-type",
                                 "SVAR %s= %s but %s is declared with Variable/G" % (r["local"], r["target"], r["target"]), r["func"])
            # check 5: Wave declarations
            for r in fi.wave_decls:
                if r["dynamic"]:
                    continue
                t = r["target"].lower()
                if t in self.waves_created:
                    continue
                if t in fi.func_params.get(r["funcl"], set()):
                    continue    # function parameter
                self.uncreated_wave_names.add(t)
                self._wave_finding(baseline, F, r["line"], r["func"], r["target"],
                                   "Wave %s (function %s)" % (r["target"], r["func"]))
            for r in fi.graph_waves:
                t = r["name"].lower()
                if t in self.waves_created:
                    continue
                self.uncreated_wave_names.add(t)
                self._wave_finding(baseline, F, r["line"], r["func"], r["name"],
                                   "%s %s (window %s)" % (r["op"].capitalize() if r["op"] == "display" else "AppendToGraph", r["name"], r["func"]),
                                   kind="graph-wave")
            # check 5: panel globals
            for r in fi.panel_globals:
                t = r["name"].lower()
                if t in self.globals or t in self.consts:
                    continue
                self.add(F, r["line"], "error", "panel-global",
                         "control %s%s refers to %s, which is neither a global (Variable/G) nor a constant in the folder (window %s)"
                         % (r["how"], r["name"] if "#" not in r["how"] else "", r["name"], r["func"]), r["func"])
            # check 6: constants
            seen = set()
            for r in fi.const_uses:
                t = r["name"].lower()
                if t in self.consts:
                    continue
                k = (r["line"], t)
                if k in seen:
                    continue
                seen.add(k)
                self.add(F, r["line"], "error", "undefined-constant",
                         "constant '%s' used in %s but not defined by any Constant/Strconstant in the folder"
                         % (r["name"], r["func"] or "top level"), r["func"])
            # check 6b: DAQ channel / device arguments
            for fl, events in fi.func_events.items():
                fname = next((f["name"] for f in fi.funcs.values() if f["name"].lower() == fl), fl)
                locs = fi.func_locals.get(fl, {})
                for ev in events:
                    if ev[0] != "chan":
                        continue
                    _, op, marg, rarg, ln = ev
                    value = None
                    if marg.startswith('"'):
                        value = rarg.strip().strip('"')
                    elif re.match(IDENT + r"$", marg):
                        la = marg.lower()
                        if la in self.consts:
                            if self.consts[la]["kind"] == "strconstant":
                                value = self.consts[la].get("value", "").strip().strip('"')
                            else:
                                self.add(F, ln, "error", "channel-arg",
                                         "%s(...) channel/device argument '%s' is a numeric Constant, a string is needed [function %s]"
                                         % (op, marg, fname), fname)
                        elif la in locs and any(k[0].lower() in ("string", "svar") for k in locs[la]):
                            pass    # local string: value unknown
                        elif la in fi.func_params.get(fl, set()):
                            pass    # parameter
                        else:
                            self.add(F, ln, "error", "channel-arg",
                                     "%s(...) channel/device argument '%s' is not a Strconstant in the folder, a string literal, or a local String/SVAR [function %s]"
                                     % (op, marg, fname), fname)
                    if self.port_mode and value is not None:
                        v = value.lower()
                        ok = (v == "dev1") if op.lower() == "mxresetdevice" else v.startswith("dev1/")
                        if not ok:
                            shown = rarg if marg.startswith('"') else "%s = \"%s\"" % (marg, value)
                            self.add(F, ln, "warning", "channel-device",
                                     "%s(...) uses %s; the one-card rig puts everything on Dev1 [function %s]"
                                     % (op, shown, fname), fname)
            # check 7: duplicate locals
            for fl, locs in fi.func_locals.items():
                for nm, decls in locs.items():
                    if len(decls) > 1:
                        self.dup_locals.add((fl, nm))
                        kinds = "/".join(sorted({d[0] for d in decls}))
                        lines_ = ", ".join(str(d[1]) for d in decls)
                        sev = "warning"
                        extra = ""
                        if baseline is not None and (fl, nm) in baseline.dup_locals:
                            sev, extra = "info", " (same duplicate exists in the baseline)"
                        fname = next((f["name"] for f in fi.funcs.values() if f["name"].lower() == fl), fl)
                        self.add(F, decls[-1][1], sev, "dup-local",
                                 "'%s' declared %d times (%s) in function %s; first declaration at line %s%s"
                                 % (self._orig_case(fi, fl, nm), len(decls), kinds, fname, decls[0][1], extra), fname)
            # check 8: read sizes
            for fl, events in fi.func_events.items():
                last_dim = {}
                last_clk = {}
                assigns = defaultdict(list)   # local lname -> [(line, expr)] in order
                fname = next((f["name"] for f in fi.funcs.values() if f["name"].lower() == fl), fl)

                def expand(expr, before_line, depth=0):
                    """(X) or X where X is a local assigned earlier -> 'X [= expr]' (recursive, 3 levels)."""
                    if expr is None or depth > 3:
                        return expr
                    inner = expr.strip()
                    if inner.startswith("(") and inner.endswith(")"):
                        inner = inner[1:-1].strip()
                    if not re.match(IDENT + r"$", inner):
                        return expr
                    prev = [a for a in assigns.get(inner.lower(), []) if a[0] < before_line]
                    if not prev:
                        return expr
                    sub = expand(prev[-1][1], prev[-1][0], depth + 1)
                    return "%s [= %s]" % (expr, sub)

                for ev in events:
                    if ev[0] == "assign":
                        assigns[ev[1]].append((ev[3], ev[2]))
                    elif ev[0] == "dim":
                        last_dim[ev[1]] = ev
                    elif ev[0] == "clk":
                        last_clk[ev[1].strip().lower()] = ev
                    elif ev[0] == "read":
                        _, task, N, wave, ln = ev
                        task_s, N_s = task.strip(), N.strip()
                        dim = last_dim.get(wave.lower())
                        clk = last_clk.get(task_s.lower())
                        clk_s = (" clock N=%s (line %d)" % (expand(clk[2].strip(), clk[3]), clk[3])) if clk else ""
                        dim_x = expand(dim[2], dim[3]) if dim else None
                        if dim:
                            size_s = "%s/N=%s (line %d)" % (dim[4], dim_x, dim[3])
                        else:
                            size_s = "no Redimension/Make of %s in this function (sized elsewhere)" % wave
                        self.add(F, ln, "info", "read-size",
                                 "MXReadAnalogF64(%s, numChans=%s, %s) <- wave size %s;%s  [function %s]"
                                 % (task_s, N_s, wave, size_s, clk_s, fname), fname)
                        if self.port_mode and task_s.lower() == "g_id1":
                            if re.match(r"^[12]$", N_s):
                                self.add(F, ln, "error", "read-size-literal",
                                         "MXReadAnalogF64 on G_ID1 reads %s channel(s); the one-card task has K_NumAIChans (3) channels [function %s]"
                                         % (N_s, fname), fname)
                            elif N_s.lower() == "k_numaichans":
                                if dim is None:
                                    self.add(F, ln, "warning", "read-size",
                                             "MXReadAnalogF64(G_ID1, K_NumAIChans, %s): %s is not sized in this function, check that its size includes *K_NumAIChans [function %s]"
                                             % (wave, wave, fname), fname)
                                elif dim_x is None or "k_numaichans" not in dim_x.lower():
                                    self.add(F, ln, "warning", "read-size",
                                             "MXReadAnalogF64(G_ID1, K_NumAIChans, %s) but the last %s of %s is N=%s, which does not contain K_NumAIChans [function %s]"
                                             % (wave, dim[4], wave, dim_x, fname), fname)
                            else:
                                self.add(F, ln, "warning", "read-size",
                                         "MXReadAnalogF64 on G_ID1 with numChans=%s (expected K_NumAIChans) [function %s]" % (N_s, fname), fname)
            # check 9: marks
            if self.port_mode:
                counts = " ".join("%s=%d" % (t.replace("[NEWDAQ-REMOVED: ", "").replace("]", "").replace("[NEWDAQ", "NEWDAQ"), n)
                                  for t, n in fi.mark_counts.items())
                self.add(F, 0, "info", "mark-count", "tagged lines: %s" % counts)
                if not fi.has_textencoding_first:
                    self.add(F, 1, "warning", "mark-encoding", 'first line is not \'#pragma TextEncoding = "UTF-8"\'')
                if not fi.has_banner:
                    self.add(F, 1, "warning", "mark-banner", "file has no '[NEWDAQ] Ported ...' banner")
                for ln, snip in fi.bad_tag_lines:
                    self.add(F, ln, "error", "mark-live-code",
                             "line carries a [NEWDAQ-REMOVED ...] tag but still contains live code: %s" % snip)
                for ln, reason in fi.bad_reasons:
                    self.add(F, ln, "warning", "mark-reason", "unknown [NEWDAQ-REMOVED: %s] reason (expected Keithley, Actuator or LowRes)" % reason)
        # reachability
        if includers:
            for fi in self.files:
                nl = fi.name.lower()
                if nl not in included and nl not in includers:
                    self.add(fi.name, 0, "info", "unreachable-file",
                             "not #included by any file in the folder (Igor only compiles it if it is opened or included by hand)")
        if self.port_mode:
            tot = OrderedDict((t, 0) for t in MARK_TAGS)
            for fi in self.files:
                for t, n in fi.mark_counts.items():
                    tot[t] += n
            self.add("(folder)", 0, "info", "mark-count",
                     "total tagged lines: " + " ".join("%s=%d" % (t, n) for t, n in tot.items()))
        self.findings.sort(key=lambda f: (self._file_order(f.file), SEV_ORDER[f.severity], f.line))
        return self.findings

    def _orig_case(self, fi, fl, nm):
        for r in fi.nvars + fi.wave_decls:
            if r.get("local", "").lower() == nm:
                return r["local"]
        return nm

    def _wave_finding(self, baseline, F, line, func, name, what, kind="undefined-wave"):
        auto = name.lower() in AUTO_WAVE_NAMES or name.lower().startswith(AUTO_WAVE_PREFIXES)
        base_msg = "%s is never created by Make/Duplicate anywhere in the folder" % what
        if baseline is None:
            if auto:
                self.add(F, line, "info", kind, base_msg + " (Igor creates it: CurveFit/FindLevels/WaveStats output)", func)
            else:
                self.add(F, line, "warning", kind, base_msg, func)
            return
        t = name.lower()
        if t in baseline.waves_created:
            self.add(F, line, "error", "wave-removed",
                     "%s: its Make/Duplicate exists in the baseline but was removed by the port" % what, func)
        elif t in baseline.uncreated_wave_names or auto:
            self.add(F, line, "info", kind, base_msg + (" (same in the baseline)" if t in baseline.uncreated_wave_names else " (Igor-created wave)"), func)
        else:
            self.add(F, line, "error", kind, base_msg + " (new in the port)", func)

    def _file_order(self, name):
        if name == "(folder)":
            return 999
        for i, fi in enumerate(self.files):
            if fi.name == name:
                return i
        return 998

    def summary(self):
        c = {"error": 0, "warning": 0, "info": 0}
        for f in self.findings:
            c[f.severity] += 1
        return c

    def keys(self, severities=("error", "warning")):
        return {f.key() for f in self.findings if f.severity in severities}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def print_findings(an, show_info=True, out=sys.stdout):
    byfile = OrderedDict()
    for f in an.findings:
        byfile.setdefault(f.file, []).append(f)
    for fname, items in byfile.items():
        shown = [f for f in items if show_info or f.severity != "info"]
        c = {"error": 0, "warning": 0, "info": 0}
        for f in items:
            c[f.severity] += 1
        out.write("\n== %s  (errors=%d warnings=%d infos=%d) ==\n" % (fname, c["error"], c["warning"], c["info"]))
        for f in shown:
            out.write("  %-7s L%-5s %-20s %s\n" % (f.severity.upper(), f.line if f.line else "-", f.kind, f.message))


def dump_calls(an, out=sys.stdout):
    cat = defaultdict(set)
    for fi in an.files:
        for c in fi.calls:
            ln_ = c["name"].lower()
            if ln_ in an.funcs or ln_ in an.macros:
                cat["defined"].add(c["name"])
            elif ln_ in XOP_FUNCTIONS:
                cat["xop"].add(c["name"])
            elif ln_ in BUILTIN_ALLOWLIST:
                cat["builtin"].add(c["name"])
            elif ln_ in FORBIDDEN_LOWER:
                cat["forbidden"].add(c["name"])
            else:
                cat["UNKNOWN"].add(c["name"])
    for k in ("defined", "xop", "builtin", "forbidden", "UNKNOWN"):
        out.write("%s (%d): %s\n" % (k, len(cat[k]), ", ".join(sorted(cat[k], key=str.lower))))


def dump_defs(an, out=sys.stdout):
    out.write("functions (%d):\n" % len(an.funcs))
    for k, d in sorted(an.funcs.items()):
        out.write("  %-32s params=%s..%s  %s:%d\n" % (d["name"], d["pmin"], d["pmax"], d["file"], d["line"]))
    out.write("macros/windows (%d):\n" % len(an.macros))
    for k, d in sorted(an.macros.items()):
        out.write("  %-32s %s %s  %s:%d\n" % (d["name"], d["kind"], d["subtype"] or "", d["file"], d["line"]))
    out.write("constants (%d):\n" % len(an.consts))
    for k, d in sorted(an.consts.items()):
        out.write("  %-32s %s  %s:%d\n" % (d["name"], d["kind"], d["file"], d["line"]))
    out.write("globals (%d):\n" % len(an.globals))
    for k, v in sorted(an.globals.items()):
        out.write("  %-32s %s\n" % (v[0][0], ", ".join("%s:%d" % (x[2], x[1]) for x in v)))
    out.write("waves created (%d):\n" % len(an.waves_created))
    for k, v in sorted(an.waves_created.items()):
        out.write("  %-32s %s\n" % (v[0][0], ", ".join("%s:%d" % (x[2], x[1]) for x in v)))
    out.write("dynamic wave targets (%d):\n" % len(an.waves_dynamic))
    for expr, ln, op, func in an.waves_dynamic:
        out.write("  %-32s %s line %d in %s\n" % (expr, op, ln, func))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Static checker for Igor Pro .ipf files (see module doc).")
    ap.add_argument("folder", help="folder with the .ipf files to check (not recursive)")
    ap.add_argument("--baseline", help="original folder; enables baseline-relative checks and the REGRESSIONS section")
    ap.add_argument("--json", dest="json_out", help="write all findings to this JSON file")
    ap.add_argument("--no-info", action="store_true", help="hide info-level lines (still counted)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--port-mode", action="store_true", help="force port mode (forbidden tokens are errors, marking audit on)")
    g.add_argument("--no-port-mode", action="store_true", help="force plain mode")
    ap.add_argument("--dump-calls", action="store_true", help="debug: list every call name by category and exit")
    ap.add_argument("--dump-defs", action="store_true", help="debug: print the definitions index and exit")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.folder):
        sys.stderr.write("not a folder: %s\n" % args.folder)
        return 2
    if not glob.glob(os.path.join(args.folder, "*.ipf")):
        sys.stderr.write("no .ipf files in %s\n" % args.folder)
        return 2

    # decide port mode
    probe = FolderAnalysis(args.folder, False, "probe")
    has_marks = any(any(fi.mark_counts.values()) for fi in probe.files)
    port_mode = bool(args.baseline) or has_marks
    if args.port_mode:
        port_mode = True
    if args.no_port_mode:
        port_mode = False

    target = FolderAnalysis(args.folder, port_mode, "target")
    if args.dump_calls:
        dump_calls(target)
        return 0
    if args.dump_defs:
        dump_defs(target)
        return 0

    baseline = None
    if args.baseline:
        if not os.path.isdir(args.baseline):
            sys.stderr.write("baseline is not a folder: %s\n" % args.baseline)
            return 2
        baseline = FolderAnalysis(args.baseline, False, "baseline")
        baseline.run_checks(None)
    target.run_checks(baseline)

    out = sys.stdout
    out.write("check_igor.py  folder=%s\n" % target.folder)
    out.write("mode=%s  files=%s\n" % ("port (forbidden tokens are errors, marking audit on)" if port_mode else "plain (forbidden tokens reported as info)",
                                        ", ".join(fi.name for fi in target.files)))
    if baseline:
        bs = baseline.summary()
        out.write("baseline=%s  (baseline findings: errors=%d warnings=%d infos=%d; files=%s)\n"
                  % (baseline.folder, bs["error"], bs["warning"], bs["info"], ", ".join(fi.name for fi in baseline.files)))
    print_findings(target, show_info=not args.no_info, out=out)

    regressions, resolved = [], []
    if baseline:
        bkeys = baseline.keys(("error", "warning", "info"))
        tkeys = target.keys(("error", "warning", "info"))
        regressions = [f for f in target.findings
                       if f.severity in ("error", "warning") and not f.kind.startswith("mark-")
                       and f.key() not in bkeys]
        resolved = [f for f in baseline.findings
                    if f.severity in ("error", "warning") and f.key() not in tkeys]
        out.write("\n== REGRESSIONS (in target, not in baseline): %d ==\n" % len(regressions))
        for f in regressions:
            out.write("  %s:%s  %-7s %-20s %s\n" % (f.file, f.line, f.severity.upper(), f.kind, f.message))
        out.write("\n== RESOLVED (error/warning in baseline, not in target): %d ==\n" % len(resolved))
        for f in resolved:
            out.write("  %s:%s  %-7s %-20s %s\n" % (f.file, f.line, f.severity.upper(), f.kind, f.message))

    s = target.summary()
    out.write("\nerrors=%d warnings=%d infos=%d%s\n" % (s["error"], s["warning"], s["info"],
                                                     ("  regressions=%d" % len(regressions)) if baseline else ""))

    if args.json_out:
        data = {
            "target": {"folder": target.folder, "port_mode": port_mode,
                       "files": [fi.name for fi in target.files],
                       "summary": s, "findings": [f.to_dict() for f in target.findings]},
            "baseline": None if not baseline else {
                "folder": baseline.folder, "files": [fi.name for fi in baseline.files],
                "summary": baseline.summary(), "findings": [f.to_dict() for f in baseline.findings]},
            "regressions": [f.to_dict() for f in regressions],
            "resolved": [f.to_dict() for f in resolved],
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)
        out.write("json written: %s\n" % args.json_out)

    return 1 if s["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
