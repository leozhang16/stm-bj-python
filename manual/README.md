# The stmlab manual

**Start with [05. The structure map](05_structure_map.md)** — the whole
code on a few pages: what every file is, which file calls which function
in which other file (extracted from the source, not written), and the two
paths to follow first: one button click, and one break-junction trace. It
is the first chapter of `../STMLAB_GUI_Manual.pdf`. Regenerate it with
`../manual_build/gen_structure.py` after editing code.

The complete Igor STM-BJ setup in Python, documented chapter by chapter.
Read 00–04 once; then read the chapter for the experiment you are about to
run; keep 30 open while working. **Chapter 04 is the fastest way in** — it
maps sixteen runnable snippets onto the eight experiments.

**A typeset PDF of the fifteen core chapters is at `../../STMLAB_Manual.pdf`**
(55 pages). These Markdown files are the source of truth; rebuild the PDF
with `../../manual_entire/build.sh` after editing them. Chapter 40 (the GUI)
exists only in this folder and is not in that PDF.

## Platform

| Chapter | Covers |
|---|---|
| [00. Overview](00_overview.md) | What this folder is, the experiment menu, quick start |
| [01. Architecture](01_architecture.md) | The module stack, `play()`, `ModeRamp` + `capture()`, safety design |
| [02. Config reference](02_config_reference.md) | Every field of every config dataclass, with Igor origins |
| [03. Hardware](03_hardware.md) | The cards, the Keithley, the NanoPZ, what needs what, bring-up |
| [04. The snippets](04_snippets.md) | Sixteen runnable scripts, and which one is for which experiment |
| [06. Code walkthrough](06_walkthrough.md) | Function by function through approach, pull and trace, plus the GUI — all 445 definitions, with the known defects |

## Experiments

| Chapter | Experiment |
|---|---|
| [10. Constant bias](10_constant_bias.md) | The reference break-junction measurement |
| [11. Push-pull](11_push_pull.md) | Re-forming the junction, cycle by cycle |
| [12. IV sweep](12_iv_sweep.md) | Bias spectroscopy at a held junction |
| [13. AC hold](13_ac_hold.md) | Sine bias, lock-in-style readout |
| [14. High-bias hold](14_high_bias_hold.md) | Stability under field; the Vzero link |
| [15. EChem gate & CV](15_echem_gate_cv.md) | Electrochemical gating, cyclic voltammetry |
| [16. Lateral monolayer](16_lateral_monolayer.md) | Site-by-site maps across a monolayer |
| [17. Bias series](17_bias_series.md) | Igor's `rungo` campaign |

## Support systems

| Chapter | Covers |
|---|---|
| [20. Keithley 428](20_keithley.md) | Gain, suppress, zero check, Keithley-sourced bias |
| [21. Vzero](21_vzero.md) | The zero-current offset workflow |
| [30. Quick reference](30_quick_reference.md) | Every command, every number, where to look |

## The GUI (this folder only)

Part I of `../STMLAB_GUI_Manual.pdf`. Read 40 and 41 before the first run;
42-45 are the panels and graphs control by control; keep 50 open while
working.

| Chapter | Covers |
|---|---|
| [40. The GUI: what it is and how to start it](40_gui_overview.md) | The tour, installing (Tk), launch options, what opens, simulate vs hardware, the first five minutes |
| [41. The lab flow, button by button](41_gui_lab_flow.md) | Start Writing → Background Sampling → Approach → Find Offset → Find Suppress → Start Measurement → Stop → Kill Tasks, in depth |
| [42. The main panel, control by control](42_gui_main_panel.md) | Every control of BreakJunctionMeasurement: Igor name, binding, effect, enable rules |
| [43. The Voltage Offset panel and V0 tracking](43_gui_offset_panel.md) | Find Offset (Find Zero) line by line; V0 check ON in each mode; Izero and Izero_Time |
| [44. The Electrochemistry panel](44_gui_echem_panel.md) | Counter-electrode gating; CV HighRes / LowRes; the keep mask; the simulated cell |
| [45. The graph windows and the History window](45_gui_graphs.md) | The nine graphs with figures, what feeds each, the History format |
| [46. Menus and macros](46_gui_macros.md) | File, Macros (rungo, LateralEXPT, X piezo), Windows, Help, keyboard |
| [47. What the GUI writes, and how to read it back](47_gui_data_files.md) | Session HDF5 layout and headers, histogram CSVs, CV files, reading examples |
| [48. How stmgui is built](48_gui_architecture.md) | state / controller / widgets / graphs / panels / app; threading rules; adding a control, a button, a graph; tests |
| [49. Deviations, limitations, troubleshooting](49_gui_troubleshooting.md) | Every deliberate difference from Igor; config warnings; symptom → cause → fix |
| [50. GUI quick reference](50_gui_quick_reference.md) | Buttons → methods → Igor procedures; events; keys; files; commands; the numbers you change most |
| [51. Appendix: the binding table](51_gui_binding_table.md) | Generated from `stmgui/state.py`: every Igor global, where it lives, limits, defaults |

Rebuild the PDF with `../manual_build/build.sh` (add `--figures` to
regenerate the graph figures from a simulated session).
