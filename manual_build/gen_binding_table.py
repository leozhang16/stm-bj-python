#!/usr/bin/env python3
"""Generate manual/51_gui_binding_table.md from stmgui.state.PARAMS.

The table is the contract between the panels and the config: one row per
Igor global, saying which RigConfig / GuiOptions attribute it lives in now,
its display units, limits and default. Generated, not written, so it cannot
drift from the code.

    ./.venv/bin/python manual_build/gen_binding_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GROUPS = [
    ("DAQ tab", ["G_AcquisitionRate", "G_WriteBufferSize",
                 "G_FastReadWaveSize", "G_HighResOutputRange",
                 "K_ZPiezoScale", "K_SenseScale", "G_PiezoOffset_nm"]),
    ("Inputs tab", ["G_PullOutRate", "G_PseudoTotalLength_nm",
                    "G_ConductanceThreshold", "G_MakeContactApproachStepSize",
                    "G_SeriesResistance", "G_EndOfTraceNoiseThreshold",
                    "G_SmashFrequency", "G_SmashInSteps", "G_SmashOutSteps",
                    "G_BiasSaveCheck", "G_CurrentSaveCheck",
                    "G_PiezoWaveSaveCheck", "G_SenseSaveCheck",
                    "G_HistSaveCheck", "G_VoltageRead"]),
    ("Options tab: Push-Pull", ["G_PushPullCheck", "G_NumPushPullCycles",
                                "G_InitialPullLength", "G_FinalPullLength",
                                "G_PushPullLength", "G_HoldLength"]),
    ("Options tab: IV", ["G_IVCheck", "G_IVMaxBias", "G_IVSignFlag",
                         "G_IVInitPull", "G_IVFinPull", "G_IVCapLength",
                         "G_IVRampLength"]),
    ("Options tab: AC", ["G_ACHoldCheck", "G_ACAmp", "G_ACFreq",
                         "G_ACInitPullLength", "G_ACHoldLength",
                         "G_ACFinPullLength"]),
    ("Options tab: High bias hold", ["G_HBHoldCheck", "G_HBBias",
                                     "G_HBInitPullLength", "G_HBFinPullLength",
                                     "G_HBHoldLength", "G_HBCapLengthIN",
                                     "G_HBCapLengthFIN"]),
    ("Keithley Controls", ["G_CurrentVoltGain", "G_CurrentSuppressConst",
                           "G_KeithleyBiasEnabled", "ZeroCheckBox",
                           "SuppressCheckBox"]),
    ("Actuator and Piezo Controls", ["G_ActuatorStepSize", "G_ActuatorCounter",
                                     "G_PiezoDeltaZ_nm"]),
    ("Bottom of the panel", ["G_TipBias", "G_PullOutNumber", "G_StopNumber",
                             "G_PullOutAttempt", "OnCheck"]),
    ("Voltage_Offset panel", ["G_VoltageInterval", "G_NumPoints",
                              "G_Vzerofrequency", "VzeroCheckBox", "G_Vzero",
                              "G_Izero"]),
    ("EChem panel", ["G_CounterElectrodeBias", "G_CVAcquisitionRate",
                     "G_NumCVCycles", "G_ScanRate", "G_VoltagePeakOne",
                     "G_VoltagePeakTwo"]),
    ("Readouts", ["G_CurrentSamplingReadoutVal", "G_JunctionVoltage",
                  "G_PiezoBiasSamplingReadoutVal"]),
]


def fmt_limit(v: float) -> str:
    if v == float("inf"):
        return "inf"
    if v == float("-inf"):
        return "-inf"
    return f"{v:g}"


def main() -> int:
    from stmgui.state import PARAMS, GuiState

    state = GuiState()
    seen: set[str] = set()
    lines = [
        "# 51. Appendix: the binding table",
        "",
        "*Generated from `stmgui/state.py` by `manual_build/gen_binding_table.py`. "
        "Igor: `Declare_STMBJ_Variables`, Functions_STMBJ.ipf:5-198, and the "
        "`value=` bindings in Windows_STMBJ.ipf.*",
        "",
        "Every panel control is bound to one row of this table. **Igor global** "
        "is the name the control was bound to in Igor; **lives in** is the "
        "attribute it writes now, dotted from a `GuiState` (`cfg.` is the "
        "`RigConfig` that every data file carries, `opts.` is `GuiOptions`, the "
        "panel-only state); **shown as** is the display unit where it differs "
        "from the stored one (Tip Bias is stored in volts, shown in mV); "
        "**limits** are Igor's `limits={lo, hi, increment}` (an increment gives "
        "the control arrow buttons); **default** is what a fresh panel shows.",
        "",
        "Bool rows are checkboxes. Rows with no limits are display-only or "
        "unbounded, as in Igor.",
        "",
    ]
    for title, names in GROUPS:
        lines += [f"## {title}", "",
                  "| Igor global | Panel title | Lives in | Kind | Limits (lo, hi, inc) | Default |",
                  "|---|---|---|---|---|---|"]
        for name in names:
            p = PARAMS[name]
            seen.add(name)
            lo, hi, inc = p.limits
            limits = "" if (lo == float("-inf") and hi == float("inf")
                            and not inc) else \
                f"{fmt_limit(lo)}, {fmt_limit(hi)}, {inc:g}"
            default = p.get(state)
            if p.kind is bool:
                default_s = "on" if default else "off"
            elif p.kind is int:
                default_s = f"{default:d}"
            else:
                default_s = f"{default:g}"
            kind = p.kind.__name__
            if p.scale != 1.0:
                kind += f" (x{p.scale:g} for display)"
            lines.append(f"| `{name}` | {p.title or '(counter)'} | `{p.path}` | "
                         f"{kind} | {limits} | {default_s} |")
        lines.append("")
    missing = sorted(set(PARAMS) - seen)
    if missing:
        raise SystemExit(f"binding table is missing PARAMS rows: {missing}")
    out = ROOT / "manual" / "51_gui_binding_table.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(seen)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
