"""stmgui -- the Igor STM-BJ panels, rebuilt in Tkinter on top of ``stmlab``.

Three layers, and the dependency only ever points downwards:

    stmgui.app / stmgui.panels / stmgui.graphs     Tk widgets (main thread)
    stmgui.controller                              one worker thread, owns the Rig
    stmlab                                         the translated Igor procedures

The controller never imports Tk, so every button's behaviour is testable
headlessly against the simulator (``tests/test_gui_controller.py``); the
panels never touch the Rig directly, so a click can never race the
acquisition loop for the DAQ card.

Igor's window macros (Windows_STMBJ.ipf) map onto these modules:

    BreakJunctionMeasurement panel   panels.main_panel
    Voltage_Offset panel             panels.voltage_offset
    EChem panel                      panels.echem_panel
    the nine Graph windows           graphs
    the Macros menu (rungo, LateralEXPT)   app  (Macros menu)
"""

__all__ = ["state", "controller", "widgets", "graphs", "panels", "app"]
