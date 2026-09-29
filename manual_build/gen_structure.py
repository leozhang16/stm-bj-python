#!/usr/bin/env python3
"""Generate the structure map: which file calls which function in which file.

Parses every source file with ``ast`` -- nothing is typed by hand except
the one-line purpose of each module, the layer each module sits in, and a
few variable-name hints (``rig`` is a ``Rig``, ``writer`` a
``SessionWriter``) that a static reader cannot know. Writes:

    manual/05_structure_map.md              the chapter (tables + figures)
    manual/figures/structure/layers.png     the whole system, by layer
    manual/figures/structure/click.png      one GUI click, top to bottom
    manual/figures/structure/trace.png      one constant-bias trace
    manual/figures/structure/graph.json     the graph, for the HTML explorer

    ./.venv/bin/python manual_build/gen_structure.py
"""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "manual" / "figures" / "structure"
OUT_MD = ROOT / "manual" / "05_structure_map.md"

# --------------------------------------------------------------------------
# The hand-written part: purposes, layers, name hints
# --------------------------------------------------------------------------

PURPOSE = {
    "gui.py": "Launcher for the panels: checks Tk, calls stmgui.app.main",
    "run.py": "Dispatcher: python run.py <experiment> or gui",
    "stmlab/__init__.py": "Package marker and version",
    "stmlab/config.py": "Every number, as dataclasses (RigConfig); validate() refuses unsafe configs",
    "stmlab/safety.py": "Limits and interlocks: check_bias, clamp_piezo, require_retracted, SafeSession, park_all_outputs",
    "stmlab/daq.py": "The real NI card: DaqSession.play() writes a waveform and reads both inputs",
    "stmlab/sim.py": "The fake card: SimulatedDaqSession with a junction model (gold plateau, molecule, tunnelling)",
    "stmlab/instrument.py": "Rig: the one funnel to the card -- play(), hold(), tracked piezo position, coarse_step() behind the interlock",
    "stmlab/approach.py": "engage() = separate + close_in; smash(); coarse_approach(); recover_headroom()",
    "stmlab/trace.py": "build_ramp() the constant pull; capture() play + align at the spike; single_trace(); trace_loop()",
    "stmlab/ramps.py": "The four mode waveforms: build_push_pull, build_iv, build_ac_hold, build_hb_hold",
    "stmlab/analysis.py": "Volts to physics: to_conductance, select_trace (Igor TestTrace), log_histogram, peak_position",
    "stmlab/storage.py": "HDF5 files: SessionWriter / Session, save_cv_cycles / CVSession, Igor .ibw readers",
    "stmlab/calibrate.py": "measure_zero, measure_group_delay, session_calibration",
    "stmlab/actuator.py": "The coarse actuator: NanoPZ over serial, simulated, or none",
    "stmlab/keithley.py": "Keithley 428 over GPIB, find_suppress (Igor TestVirtualGround)",
    "stmlab/vzero.py": "measure_offset (Igor OffsetVoltage) and VzeroTracker (SaveOffset)",
    "stmlab/echem.py": "CounterElectrode gate; CV ramp builders and run_cv",
    "stmlab/xpiezo.py": "XPiezo: the lateral piezo on the second card",
    "stmlab/bringup.py": "Hardware bring-up checks: devices, timing, hold, preamp, actuator",
    "stmlab/main.py": "The command line: run / check / summarise / dump-config / bringup",
    "stmgui/__init__.py": "Package docstring",
    "stmgui/state.py": "GuiOptions (Igor globals without a config home), Param, PARAMS binding table",
    "stmgui/controller.py": "RigController: every button as a method; one worker thread owns the Rig; events out; COMMAND_MAP",
    "stmgui/widgets.py": "SetVariable, ValDisplay, CheckBox, button, Tooltip, Inspector binding",
    "stmgui/graphs.py": "The nine Igor graph windows (matplotlib in Tk) and GraphSet routing",
    "stmgui/app.py": "App: builds panels, menus, the 50 ms event pump; InitializeExperiment",
    "stmgui/panels/__init__.py": "Panel exports",
    "stmgui/panels/main_panel.py": "The BreakJunctionMeasurement panel",
    "stmgui/panels/voltage_offset.py": "The Voltage_Offset panel",
    "stmgui/panels/echem_panel.py": "The EChem panel",
    "stmgui/panels/history.py": "The History window",
    "stmgui/panels/button_map.py": "The Button map and Inspector windows",
}

EXPERIMENT_PURPOSE = {
    "01_constant_bias": "delegates to stmlab.main (the reference loop)",
    "02_push_pull": "loop: engage, ramps.build_push_pull, capture, save",
    "03_iv_sweep": "loop: engage, ramps.build_iv, capture, save; iv_analysis.py reads it back",
    "04_ac_hold": "loop: engage, ramps.build_ac_hold, capture, save",
    "05_high_bias_hold": "loop: engage, ramps.build_hb_hold (optionally at Vzero), capture, save",
    "06_echem_gate_cv": "gate / cv / traces sub-commands over echem.py",
    "07_lateral_monolayer": "per site: trace_loop, withdraw, xpiezo.move_nm, approach",
    "08_bias_series": "Igor rungo: one trace_loop per bias, resumable",
}

# Layer of each module in the big picture (top to bottom).
LAYERS = [
    ("Entry points", ["gui.py", "run.py", "experiments/*/run_experiment.py",
                      "stmlab/main.py"]),
    ("The GUI (stmgui)", ["stmgui/app.py", "stmgui/panels/*.py",
                          "stmgui/graphs.py", "stmgui/widgets.py",
                          "stmgui/state.py", "stmgui/controller.py"]),
    ("Recipes (stmlab)", ["stmlab/trace.py", "stmlab/approach.py",
                          "stmlab/ramps.py", "stmlab/analysis.py",
                          "stmlab/vzero.py", "stmlab/calibrate.py",
                          "stmlab/keithley.py", "stmlab/echem.py",
                          "stmlab/xpiezo.py", "stmlab/storage.py",
                          "stmlab/bringup.py"]),
    ("The rig (stmlab)", ["stmlab/instrument.py", "stmlab/safety.py",
                          "stmlab/config.py", "stmlab/actuator.py"]),
    ("Card and instruments", ["stmlab/daq.py", "stmlab/sim.py",
                              "nidaqmx / pyvisa / pyserial"]),
]

# Variable names (or self.attr chains) whose type a static reader cannot
# know. Maps to "module.Class".
NAME_HINTS = {
    ("rig",): "stmlab.instrument.Rig",
    ("self", "rig"): "stmlab.instrument.Rig",
    ("writer",): "stmlab.storage.SessionWriter",
    ("self", "_writer"): "stmlab.storage.SessionWriter",
    ("session",): "stmlab.storage.Session",
    ("s",): "stmlab.storage.Session",
    ("amp",): "stmlab.keithley.Keithley428",
    ("self", "amp"): "stmlab.keithley.Keithley428",
    ("keithley",): "stmlab.keithley.Keithley428",
    ("ce",): "stmlab.echem.CounterElectrode",
    ("self", "gate"): "stmlab.echem.CounterElectrode",
    ("xp",): "stmlab.xpiezo.XPiezo",
    ("self", "xp"): "stmlab.xpiezo.XPiezo",
    ("tracker",): "stmlab.vzero.VzeroTracker",
    ("self", "vzero_tracker"): "stmlab.vzero.VzeroTracker",
    ("act",): "stmlab.actuator.Actuator",
    ("self", "_actuator"): "stmlab.actuator.Actuator",
    ("self", "_session"): "stmlab.daq.DaqSession",
    ("cfg",): "stmlab.config.RigConfig",
    ("self", "cfg"): "stmlab.config.RigConfig",
    ("cfg", "cal"): "stmlab.config.Calibration",
    ("self", "cfg", "cal"): "stmlab.config.Calibration",
    ("rig", "cfg", "cal"): "stmlab.config.Calibration",
    ("cfg", "channels"): "stmlab.config.ChannelMap",
    ("self", "cfg", "channels"): "stmlab.config.ChannelMap",
    ("C",): "stmlab.config.Calibration",
    ("cal",): "stmlab.config.Calibration",
    ("M",): "stmlab.config.ChannelMap",
    ("R",): "stmlab.config.RampConfig",
    ("self", "ctl"): "stmgui.controller.RigController",
    ("app", "ctl"): "stmgui.controller.RigController",
    ("ctl",): "stmgui.controller.RigController",
    ("self", "app"): "stmgui.app.App",
    ("app",): "stmgui.app.App",
    ("self", "graphs"): "stmgui.graphs.GraphSet",
    ("self", "history"): "stmgui.panels.history.HistoryWindow",
    ("self", "main"): "stmgui.panels.main_panel.MainPanel",
    ("self", "offset"): "stmgui.panels.voltage_offset.VoltageOffsetPanel",
    ("self", "echem"): "stmgui.panels.echem_panel.EChemPanel",
    ("self", "inspector"): "stmgui.panels.button_map.InspectorWindow",
    ("self", "button_map"): "stmgui.panels.button_map.ButtonMapWindow",
    ("self", "tooltip"): "stmgui.widgets.Tooltip",
}

# --------------------------------------------------------------------------
# Collect the modules
# --------------------------------------------------------------------------


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def collect_files() -> list[Path]:
    files = [ROOT / "gui.py", ROOT / "run.py"]
    files += sorted((ROOT / "stmlab").glob("*.py"))
    files += sorted((ROOT / "stmgui").glob("*.py"))
    files += sorted((ROOT / "stmgui" / "panels").glob("*.py"))
    for d in sorted((ROOT / "experiments").iterdir()):
        if d.is_dir():
            files += sorted(d.glob("*.py"))
    return files


class Module:
    def __init__(self, path: Path):
        self.path = path
        self.rel = str(path.relative_to(ROOT))
        self.name = module_name(path)
        self.package = ".".join(self.name.split(".")[:-1])
        self.tree = ast.parse(path.read_text(encoding="utf-8"))
        self.lines = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
        self.functions: dict[str, int] = {}          # name -> lineno
        self.classes: dict[str, dict[str, int]] = {}  # class -> {method: lineno}
        self.imports: dict[str, str] = {}             # alias -> dotted target
        self.calls: dict[str, set[str]] = defaultdict(set)   # "def" -> {"mod.sym"}
        self.doc = ast.get_docstring(self.tree) or ""

    @property
    def is_experiment(self) -> bool:
        return self.rel.startswith("experiments/")


def known_modules(mods: dict[str, Module]) -> set[str]:
    names = set(mods)
    names |= {m.package for m in mods.values() if m.package}
    return names


def resolve_import(mod: Module, node, names: set[str]) -> None:
    if isinstance(node, ast.Import):
        for a in node.names:
            mod.imports[a.asname or a.name.split(".")[0]] = a.name
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            base_parts = mod.name.split(".")[:-1]
            if node.level > 1:
                base_parts = base_parts[:-(node.level - 1)]
            base = ".".join(base_parts)
            target = f"{base}.{node.module}" if node.module else base
        else:
            target = node.module or ""
        for a in node.names:
            full = f"{target}.{a.name}" if target else a.name
            mod.imports[a.asname or a.name] = full


def collect_defs(mod: Module) -> None:
    for node in mod.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mod.functions[node.name] = node.lineno
        elif isinstance(node, ast.ClassDef):
            mod.classes[node.name] = {
                n.name: n.lineno for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def attr_chain(node) -> tuple[str, ...] | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return tuple(reversed(parts))
    return None


def collect_calls(mod: Module, mods: dict[str, Module], names: set[str]) -> None:
    """Record, per def, the cross-module symbols it calls."""
    def target_of(callee) -> str | None:
        if isinstance(callee, ast.Name):
            t = mod.imports.get(callee.id)
            if t:
                return t                              # imported function/class
            if callee.id in mod.functions or callee.id in mod.classes:
                return f"{mod.name}.{callee.id}"      # local
            return None
        chain = attr_chain(callee)
        if not chain:
            return None
        head, *rest = chain
        # imported module alias: approach.engage, storage.SessionWriter
        t = mod.imports.get(head)
        if t and t in names and rest:
            return f"{t}.{'.'.join(rest)}"
        if t and rest:
            return f"{t}.{'.'.join(rest)}"            # imported class: Cls.method
        # hinted variable: rig.play, self.ctl.find_suppress. GUI-object
        # hints (self.history, self.app ...) apply only inside stmgui, so a
        # `self.history` list in stmlab is not mistaken for the window.
        for k in range(len(chain) - 1, 0, -1):
            hint = NAME_HINTS.get(chain[:k])
            if hint and (hint.startswith("stmlab") or mod.name.startswith("stmgui")):
                return f"{hint}.{'.'.join(chain[k:])}"
        # self.method inside a class
        if head == "self" and len(rest) == 1:
            return f"{mod.name}.<self>.{rest[0]}"
        return None

    def walk_def(owner: str, fn) -> None:
        for node in ast.walk(fn):
            if isinstance(node, ast.Call):
                t = target_of(node.func)
                if t:
                    mod.calls[owner].add(t)

    for node in mod.tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walk_def(node.name, node)
        elif isinstance(node, ast.ClassDef):
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    walk_def(f"{node.name}.{n.name}", n)
    # module level (scripts)
    top = [n for n in mod.tree.body
           if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef, ast.Import, ast.ImportFrom))]
    for n in top:
        for node in ast.walk(n):
            if isinstance(node, ast.Call):
                t = target_of(node.func)
                if t:
                    mod.calls["<module>"].add(t)


def split_target(t: str, mods: dict[str, Module], depth: int = 0):
    """'stmlab.instrument.Rig.play' -> (module 'stmlab.instrument', 'Rig.play').

    A symbol imported through a package's ``__init__`` (``from .panels
    import MainPanel``) is followed to the module that defines it."""
    parts = t.split(".")
    for k in range(len(parts), 0, -1):
        m = ".".join(parts[:k])
        if m in mods:
            return m, ".".join(parts[k:])
        init = mods.get(f"{m}.__init__")
        if init is not None and k < len(parts) and depth < 3:
            re = init.imports.get(parts[k])
            if re:
                return split_target(".".join([re] + parts[k + 1:]), mods,
                                    depth + 1)
    return None, t


def build() -> dict:
    files = collect_files()
    mods = {module_name(p): Module(p) for p in files}
    names = known_modules(mods)
    for m in mods.values():
        for node in ast.walk(m.tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                resolve_import(m, node, names)
        collect_defs(m)
    for m in mods.values():
        collect_calls(m, mods, names)

    # Cross-module edges, checked against the definitions.
    edges = []          # (from_module, from_def, to_module, to_symbol, ok)
    unresolved = []
    for m in mods.values():
        for owner, targets in m.calls.items():
            for t in sorted(targets):
                to_mod, sym = split_target(t, mods)
                if to_mod is None or to_mod == m.name:
                    continue
                tm = mods[to_mod]
                first = sym.split(".")[0]
                ok = (first in tm.functions or first in tm.classes
                      or (first == "<self>"))
                if first in tm.classes and "." in sym:
                    meth = sym.split(".")[1]
                    ok = meth in tm.classes[first] or meth in (
                        "__init__", "open", "close") or _inherited(tm, first, meth, mods)
                if not ok:
                    unresolved.append((m.rel, owner, t))
                    continue
                edges.append((m.name, owner, to_mod, sym))
    return {"mods": mods, "edges": edges, "unresolved": unresolved}


def _inherited(tm: Module, cls: str, meth: str, mods) -> bool:
    """Method defined on a base class in the same module (Simulated*)."""
    for node in tm.tree.body:
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for base in node.bases:
                bname = getattr(base, "id", None)
                if bname in tm.classes and meth in tm.classes[bname]:
                    return True
    return False


# --------------------------------------------------------------------------
# Figures
# --------------------------------------------------------------------------

def layer_of(rel: str) -> str:
    for title, items in LAYERS:
        for it in items:
            if it == rel:
                return title
            if it.endswith("*.py") and rel.startswith(it[:-4]):
                return title
            if it == "experiments/*/run_experiment.py" and rel.startswith("experiments/"):
                return title
    return "?"


def display_box(rel: str) -> str:
    if rel.startswith("experiments/"):
        return "experiments/*/run_experiment.py"
    if rel.startswith("stmgui/panels/"):
        return "stmgui/panels/*.py"
    return rel


def draw_layers(g: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    mods = g["mods"]
    # module-pair edge weights, by display box
    weight: dict[tuple[str, str], int] = defaultdict(int)
    for fm, _owner, tm, _sym in g["edges"]:
        a, b = display_box(mods[fm].rel), display_box(mods[tm].rel)
        if a != b:
            weight[(a, b)] += 1
    # external libraries
    for m in mods.values():
        for alias, t in m.imports.items():
            if t.split(".")[0] in ("nidaqmx", "pyvisa", "serial"):
                weight[(display_box(m.rel), "nidaqmx / pyvisa / pyserial")] += 1

    # Layout: a band per layer; rows of at most 6 boxes inside a band.
    per_row = 6
    band_rows = [max(1, -(-len(items) // per_row)) for _, items in LAYERS]
    band_h = [0.55 + 0.75 * r for r in band_rows]
    total_h = sum(band_h) + 0.5 * (len(LAYERS) - 1) + 0.9
    fig, ax = plt.subplots(figsize=(13, total_h))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, total_h)
    ax.axis("off")
    pos: dict[str, tuple[float, float]] = {}
    box_w, box_h = 1.85, 0.5
    colours = ["#f4e6c8", "#dbe8f7", "#e5f0dc", "#f7dbd6", "#e6e0f0"]
    y_top = total_h - 0.45
    for k, (title, items) in enumerate(LAYERS):
        h = band_h[k]
        ax.add_patch(FancyBboxPatch((0.15, y_top - h), 12.7, h,
                                    boxstyle="round,pad=0.02",
                                    fc=colours[k], ec="#999999", lw=0.8))
        ax.text(0.3, y_top - 0.12, title, fontsize=11, fontweight="bold",
                color="#444444", va="top")
        rows = [items[i:i + per_row] for i in range(0, len(items), per_row)]
        for r, row_items in enumerate(rows):
            n = len(row_items)
            gap = 12.4 / n
            yy = y_top - 0.55 - 0.75 * r - box_h - 0.05
            for i, it in enumerate(row_items):
                x = 0.3 + gap * i + (gap - box_w) / 2
                pos[it] = (x + box_w / 2, yy + box_h / 2)
                ax.add_patch(FancyBboxPatch((x, yy), box_w, box_h,
                                            boxstyle="round,pad=0.02",
                                            fc="white", ec="#333333", lw=1.0))
                label = it
                if label.startswith("stmlab/") and k >= 2:
                    label = label[len("stmlab/"):]
                label = label.replace("experiments/*/run_experiment.py",
                                      "experiments/*/\nrun_experiment.py")
                label = label.replace("nidaqmx / pyvisa / pyserial",
                                      "nidaqmx / pyvisa /\npyserial")
                ax.text(x + box_w / 2, yy + box_h / 2, label, ha="center",
                        va="center", fontsize=8.5, family="monospace")
        y_top -= h + 0.5

    # Arrows: one per calling file -> called file, thickness by the number
    # of distinct functions called. config.py is read by everything and is
    # left out (the caption says so); one-off calls are drawn faintly.
    layer_colour = {"Entry points": "#8c6a10", "The GUI (stmgui)": "#1f5fa8",
                    "Recipes (stmlab)": "#2e7d32", "The rig (stmlab)": "#b5451b",
                    "Card and instruments": "#5b4a8a"}
    for (a, b), w in sorted(weight.items(), key=lambda kv: -kv[1]):
        if a not in pos or b not in pos or b == "stmlab/config.py":
            continue
        (x1, y1), (x2, y2) = pos[a], pos[b]
        same_band = abs(y1 - y2) < 0.9
        if same_band:
            style = "arc3,rad=-0.3"
            start, end = (x1, y1 + box_h / 2), (x2, y2 + box_h / 2)
        else:
            style = "arc3,rad=0.0"
            start, end = (x1, y1 - box_h / 2), (x2, y2 + box_h / 2)
        col = layer_colour.get(layer_of(a), "#8c3a10")
        ax.add_patch(FancyArrowPatch(start, end, connectionstyle=style,
                                     arrowstyle="-|>", mutation_scale=8,
                                     lw=0.4 + min(w, 10) * 0.16,
                                     color=col, alpha=0.30 if w == 1 else 0.6))
    ax.text(0.3, 0.1, "Arrow: the file above calls functions in the file "
                      "below; thickness = number of distinct functions called, "
                      "colour = the calling layer. config.py is read by every "
                      "file and its arrows are omitted. Generated from the "
                      "source by manual_build/gen_structure.py.",
            fontsize=8, color="#555555", wrap=True)
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "layers.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def draw_flow(steps: list[tuple[str, str]], title: str, fname: str) -> None:
    """A vertical chain of boxes: (file, 'function -- what it does')."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    n = len(steps)
    fig, ax = plt.subplots(figsize=(9.5, 0.78 * n + 0.8))
    ax.set_xlim(0, 9.5)
    ax.set_ylim(0, 0.78 * n + 0.6)
    ax.axis("off")
    ax.text(0.2, 0.78 * n + 0.35, title, fontsize=11, fontweight="bold",
            color="#8c3a10", va="center")
    for i, (file, what) in enumerate(steps):
        y = 0.78 * (n - 1 - i) + 0.15
        ax.add_patch(FancyBboxPatch((0.2, y), 3.0, 0.55,
                                    boxstyle="round,pad=0.02",
                                    fc="#f4f1ea", ec="#333333", lw=0.9))
        ax.text(1.7, y + 0.275, file, ha="center", va="center", fontsize=8.5,
                family="monospace")
        ax.text(3.45, y + 0.275, what, ha="left", va="center", fontsize=8.8)
        if i < n - 1:
            ax.add_patch(FancyArrowPatch((1.7, y), (1.7, y - 0.23),
                                         arrowstyle="-|>", mutation_scale=9,
                                         lw=1.0, color="#8c3a10"))
    fig.savefig(FIG / fname, dpi=150, bbox_inches="tight")
    plt.close(fig)


CLICK_FLOW = [
    ("gui.py", "main -> stmgui.app.main(): parses --simulate, builds App"),
    ("stmgui/app.py", "App.__init__: RigController, MainPanel, panels, graphs, menus; _pump every 50 ms"),
    ("stmgui/panels/main_panel.py", "the Find Suppress button -> self.ctl.find_suppress()"),
    ("stmgui/controller.py", "find_suppress() -> _run(): queues _find_suppress_impl on the worker thread"),
    ("stmgui/controller.py", "_find_suppress_impl: rig.set_bias(0); keithley.find_suppress(rig, amp); rig.set_bias(back)"),
    ("stmlab/keithley.py", "find_suppress: 21 x [amp.set_suppress_ua; rig.hold(); mean]; polyfit; set the zero crossing"),
    ("stmlab/instrument.py", "Rig.hold -> Rig.play: safety checks, then session.play(waveform); updates the tracked position"),
    ("stmlab/daq.py  |  stmlab/sim.py", "DaqSession.play (nidaqmx) or SimulatedDaqSession.play (the junction model)"),
    ("stmgui/controller.py", "_emit('suppress', ...) and log lines -> the events queue"),
    ("stmgui/app.py", "_pump -> _fanout: MainPanel.on_event updates the Suppress I value; HistoryWindow.on_event prints"),
]

TRACE_FLOW = [
    ("stmlab/main.py", "run(): validate(cfg); SafeSession; Rig(cfg); session_calibration; recover_headroom; SessionWriter; trace_loop"),
    ("stmlab/trace.py", "trace_loop: per attempt -> approach.smash (every N), approach.engage, single_trace, analysis.select_trace, on_trace()"),
    ("stmlab/approach.py", "engage: if in contact, separate(); close_in() 0.5 nm at a time until rig.in_contact(); headroom check"),
    ("stmlab/instrument.py", "in_contact -> probe -> hold -> play; conductance_of(record) with cfg.cal"),
    ("stmlab/trace.py", "single_trace -> build_ramp(cfg, rig.piezo_v): the (2, N) volt array, spike near the end"),
    ("stmlab/safety.py", "check_bias, check_pull_headroom: refuse rather than clip"),
    ("stmlab/trace.py", "capture: rig.play(ramp.waveform); analysis.find_alignment_edge -> delay; cut the trace -> TraceRecord"),
    ("stmlab/daq.py  |  stmlab/sim.py", "play(): the card (or the model) returns the (2, N) record of volts"),
    ("stmlab/analysis.py", "to_conductance -> G/G0 from raw volts; select_trace = Igor TestTrace (tunnelling tail, gold plateau)"),
    ("stmlab/storage.py", "SessionWriter.append: raw volts and per-trace scalars into the HDF5 file"),
    ("stmlab/analysis.py", "log_histogram over the accepted traces -> the peak at 1 G0 (main.summarise, or the GUI per 100 traces)"),
]

# --------------------------------------------------------------------------
# The chapter
# --------------------------------------------------------------------------

def short(sym: str) -> str:
    return sym.replace("<self>.", "self.")


def write_chapter(g: dict) -> None:
    mods = g["mods"]
    edges = g["edges"]

    # callers / callees per module
    callees: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    callers: dict[str, set[str]] = defaultdict(set)
    for fm, owner, tm, sym in edges:
        callees[fm][owner].add(f"{mods[tm].rel}: {short(sym)}")
        callers[tm].add(mods[fm].rel)

    L = []
    L.append("# 05. The structure map: which file calls what")
    L.append("")
    L.append("*Generated from the source by `manual_build/gen_structure.py` "
             "(Python's `ast`, every `def`, every call). Figures: "
             "`manual/figures/structure/`. Regenerate after editing code.*")
    L.append("")
    L.append("Read this before chapter 00. It is the whole code on a few pages: "
             "what the files are, which file calls which function in which "
             "other file, and the two paths you will follow most — a button "
             "click, and one break-junction trace. Everything below the "
             "purpose column and the layer names is extracted from the code, "
             "not written; if a table here disagrees with a chapter, the table "
             "is right and the chapter is stale.")
    L.append("")
    L.append("## The shape, in one picture")
    L.append("")
    L.append("Five layers. Arrows point from the file that calls to the file "
             "that is called; nothing calls upward. The GUI and the "
             "command-line experiments are alternative tops on the same "
             "`stmlab` body, and only `daq.py` / `sim.py` (and, through "
             "`keithley.py`, `actuator.py`, `echem.py`, `xpiezo.py`, the driver "
             "libraries) ever touch an instrument.")
    L.append("")
    L.append("!FIGL[figures/structure/layers.png]{The whole code by layer, on its own page. Every arrow is at least one real call found in the source; thickness is the number of distinct functions called, colour is the calling layer. config.py is read by every file and its arrows are left out.}")
    L.append("")
    L.append("| Layer | Files | What lives there |")
    L.append("|----|--------|----------|")
    L.append("| Entry points | `gui.py`, `run.py`, `experiments/*/run_experiment.py`, `stmlab/main.py` | Where a run starts. `gui.py` starts the panels; `run.py` forwards to an experiment script or to `gui.py`; `stmlab/main.py` is the constant-bias command line that experiment 01 delegates to. |")
    L.append("| The GUI | `stmgui/` | The panels, graphs and menus (Tk thread) and `controller.py` (the worker thread that owns the Rig). Every button is a `RigController` method. |")
    L.append("| Recipes | `stmlab/trace.py`, `approach.py`, `ramps.py`, `analysis.py`, `vzero.py`, `calibrate.py`, `keithley.py`, `echem.py`, `xpiezo.py`, `storage.py`, `bringup.py` | The Igor procedures, one concern per file. They know *what* to do to the junction and call the Rig to do it. |")
    L.append("| The rig | `stmlab/instrument.py`, `safety.py`, `config.py`, `actuator.py` | `Rig` is the only way to the card; `safety` is what it checks; `config` is every number; `actuator` is the coarse motor. |")
    L.append("| Card and instruments | `stmlab/daq.py`, `stmlab/sim.py`, `nidaqmx`, `pyvisa`, `pyserial` | `DaqSession.play()` is the one function that talks to the NI card; `SimulatedDaqSession.play()` is its stand-in. |")
    L.append("")

    L.append("## Follow one click")
    L.append("")
    L.append("Press **Find Suppress** on the panel. This is the path, file by "
             "file, top to bottom. Every button takes the same route; only the "
             "`_impl` and the recipe module change (chapter 50 lists them all, "
             "and the Button map window shows this for any control).")
    L.append("")
    L.append("!FIG[figures/structure/click.png]{One click, from gui.py to the card and back to the screen.}")
    L.append("")
    L.append("Three things to notice. The panel never calls `stmlab` "
             "directly: it calls the controller, which queues the work. The "
             "controller never draws: it posts events, which `app.py` "
             "delivers to the panels 20 times a second. And the recipe "
             "(`keithley.find_suppress`) never touches the card: it asks the "
             "`Rig`, which checks the limits and calls `play()`.")
    L.append("")

    L.append("## Follow one trace")
    L.append("")
    L.append("`python run.py constant_bias --simulate -n 100`, or Start "
             "Measurement in constant mode. The command line path is shown; "
             "the GUI's `_measure_impl` does the same steps in the same order, "
             "with its own loop instead of `trace_loop`.")
    L.append("")
    L.append("!FIG[figures/structure/trace.png]{One constant-bias trace, from the command line to the histogram.}")
    L.append("")

    # ---- module table --------------------------------------------------
    L.append("## Every file")
    L.append("")
    L.append("| File | Lines | Purpose | Called by |")
    L.append("|--------|--|--------------|--------|")
    order = ["gui.py", "run.py", "stmlab/main.py"]
    order += [f"stmlab/{n}.py" for n in (
        "config", "safety", "instrument", "daq", "sim", "actuator", "approach",
        "trace", "ramps", "analysis", "storage", "calibrate", "keithley",
        "vzero", "echem", "xpiezo", "bringup")]
    order += ["stmgui/app.py", "stmgui/controller.py", "stmgui/state.py",
              "stmgui/widgets.py", "stmgui/graphs.py",
              "stmgui/panels/main_panel.py", "stmgui/panels/voltage_offset.py",
              "stmgui/panels/echem_panel.py", "stmgui/panels/history.py",
              "stmgui/panels/button_map.py"]
    by_rel = {m.rel: m for m in mods.values()}
    for rel in order:
        m = by_rel.get(rel)
        if m is None:
            continue
        who = sorted(callers.get(m.name, set()))
        exps = [w for w in who if w.startswith("experiments/")]
        if len(exps) >= 3:
            who = [w for w in who if not w.startswith("experiments/")]
            who.insert(0, f"experiments/* ({len(exps)} scripts)")
        who_s = ", ".join(f"`{w}`" for w in who) if who else "(entry point)"
        L.append(f"| `{rel}` | {m.lines} | {PURPOSE.get(rel, '')} | {who_s} |")
    for d in sorted(EXPERIMENT_PURPOSE):
        rel = f"experiments/{d}/run_experiment.py"
        m = by_rel.get(rel)
        if m is None:
            continue
        L.append(f"| `{rel}` | {m.lines} | {EXPERIMENT_PURPOSE[d]} | `run.py` |")
    L.append("")

    # ---- imports per module (module -> modules it calls into) -----------
    L.append("## Who calls whom, file by file")
    L.append("")
    L.append("For each file: the functions it defines, and for each one the "
             "functions in *other* files it calls (`file: function`). Calls "
             "within the same file are left out, as are calls to numpy, "
             "h5py, Tk and the standard library. A method is shown as "
             "`Class.method`; `self.x` means a method of the same class.")
    L.append("")
    for rel in order + [f"experiments/{d}/run_experiment.py" for d in sorted(EXPERIMENT_PURPOSE)]:
        m = by_rel.get(rel)
        if m is None:
            continue
        L.append(f"### {rel}")
        L.append("")
        defs = []
        for f, ln in m.functions.items():
            defs.append((f, ln))
        for c, meths in m.classes.items():
            for meth, ln in meths.items():
                defs.append((f"{c}.{meth}", ln))
        defs.sort(key=lambda x: x[1])
        rows = []
        for name, ln in defs:
            outs = sorted(callees[m.name].get(name, set()))
            if not outs:
                continue
            rows.append((f"{name} (:{ln})", "; ".join(outs)))
        if "<module>" in callees[m.name]:
            rows.insert(0, ("(module level)",
                            "; ".join(sorted(callees[m.name]["<module>"]))))
        if not rows:
            L.append("Calls nothing in another file of this package "
                     "(a leaf: it is called, it does not call).")
            L.append("")
            continue
        L.append("| Function | Calls (file: function) |")
        L.append("|-------|----------------|")
        for name, outs in rows:
            L.append(f"| `{name}` | {outs} |")
        L.append("")

    L.append("## How to use this chapter")
    L.append("")
    L.append("- To find where something happens, start at the entry point "
             "you used (`gui.py` or `run.py`), find the row in *Who calls "
             "whom*, and follow the `file: function` entries downward; "
             "each one is a row in the next table. Three hops reach the card.")
    L.append("- To find who uses a function, search this chapter for its "
             "name: every caller lists it.")
    L.append("- In the GUI, hover or right-click any control: the tooltip and "
             "the Inspector give the same file:line chain for that control "
             "(chapter 40).")
    L.append("- `less -N stmlab/trace.py` then `/def capture` opens the "
             "source at the function; the `:line` after each name in the "
             "tables is where the `def` is.")
    L.append("")
    OUT_MD.write_text("\n".join(L), encoding="utf-8")


def write_json(g: dict) -> None:
    mods = g["mods"]
    data = {
        "modules": [{
            "rel": m.rel, "name": m.name, "lines": m.lines,
            "layer": layer_of(m.rel),
            "purpose": PURPOSE.get(m.rel) or EXPERIMENT_PURPOSE.get(
                m.rel.split("/")[1] if m.rel.startswith("experiments/") else "", ""),
            "functions": [{"name": f, "line": ln} for f, ln in m.functions.items()],
            "classes": {c: [{"name": k, "line": v} for k, v in meths.items()]
                        for c, meths in m.classes.items()},
            "doc": m.doc.split("\n\n")[0][:400],
        } for m in mods.values()],
        "edges": [{"from": mods[fm].rel, "def": owner, "to": mods[tm].rel,
                   "symbol": short(sym)} for fm, owner, tm, sym in g["edges"]],
        "click_flow": CLICK_FLOW,
        "trace_flow": TRACE_FLOW,
    }
    (FIG / "graph.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def write_html(data: dict) -> Path:
    """Fill manual_build/structure_template.html with the graph and write
    manual/structure_map.html -- the interactive version of this chapter.
    Open it in a browser, or publish it as an artifact."""
    template = (Path(__file__).resolve().parent /
                "structure_template.html").read_text(encoding="utf-8")
    start = template.index("/*GRAPH_JSON*/")
    end = template.index("/*END*/") + len("/*END*/")
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = template[:start] + blob + template[end:]
    out = ROOT / "manual" / "structure_map.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    g = build()
    FIG.mkdir(parents=True, exist_ok=True)
    draw_layers(g)
    draw_flow(CLICK_FLOW, "One click: Find Suppress", "click.png")
    draw_flow(TRACE_FLOW, "One constant-bias trace: run.py constant_bias",
              "trace.png")
    write_chapter(g)
    data = write_json(g)
    html = write_html(data)
    print(f"wrote {html.relative_to(ROOT)}")
    print(f"modules: {len(g['mods'])}, cross-file call edges: {len(g['edges'])}")
    if g["unresolved"]:
        print(f"unresolved ({len(g['unresolved'])}):")
        for rel, owner, t in g["unresolved"][:40]:
            print(f"  {rel} {owner} -> {t}")
    print(f"wrote {OUT_MD.relative_to(ROOT)} and {FIG.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
