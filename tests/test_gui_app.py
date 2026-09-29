"""The Tk layer: build every panel and graph, drive a simulated run through
the real widgets, and check the events reach the screen.

Skipped where Tk cannot open a display (a headless CI box).
"""

from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:                          # no display
        pytest.skip(f"no Tk display: {exc}")
    root.withdraw()
    return root


@pytest.fixture
def app(tmp_path):
    from stmgui.app import App
    from stmgui.state import simulated_state
    state = simulated_state()
    state.opts.data_dir = str(tmp_path)
    state.cfg.vzero.n_points = 3
    state.cfg.vzero.settle_s = 0.0
    root = _root()
    a = App(state=state, simulate=True, root=root)
    a.ctl.wait_idle()
    a.pump_once()
    yield a
    a.quit()


def test_panels_and_graphs_build(app):
    assert app.main.winfo_exists()
    assert app.offset.winfo_exists() and app.echem.winfo_exists()
    for name in app.graphs.names():
        win = app.graphs.get(name)
        assert win.winfo_exists()


def test_setvariable_writes_through_to_config(app):
    w = app.main.tip_bias
    w.var.set("150")
    w._commit(None)                     # Return key
    app.ctl.wait_idle()
    assert app.state.cfg.ramp.bias_v == pytest.approx(0.150)
    w.var.set("not a number")
    w._commit(None)
    assert w.var.get() == "150.0"       # rejected, display restored


def test_mode_checkboxes_exclusive_in_widgets(app):
    boxes = app.main.mode_boxes
    boxes["iv"].var.set(True)
    boxes["iv"]._toggle()
    boxes["ac_hold"].var.set(True)
    boxes["ac_hold"]._toggle()
    assert app.state.opts.mode() == "ac_hold"
    assert boxes["iv"].var.get() is False


def test_simulated_run_reaches_the_graphs(app):
    app.ctl.start_writing(wait=True)
    app.pump_once()
    assert str(app.main.b_start_daq["state"]) == "disabled"
    assert str(app.main.slider["state"]) == "normal"

    app.ctl.find_offset(wait=True)
    app.pump_once()
    assert app.offset.vzero.var.get() != ""
    assert app.graphs.get("Izero").winfo_viewable() in (0, 1)  # created

    app.state.opts.stop_number = app.state.opts.pull_out_number + 2
    app.ctl.start_measurement(wait=True)
    app.pump_once()
    assert app.main.saved.var.get() == str(app.state.opts.pull_out_number)
    hist = app.graphs.get("LogHistOfBlock")
    assert hist.bars is not None
    low = app.graphs.get("PullOutLowG")
    assert len(low.l_g.get_xdata()) > 100

    app.ctl.kill_tasks(wait=True)
    app.pump_once()
    assert str(app.main.b_start_daq["state"]) == "normal"


def test_cv_reaches_the_voltammogram(app):
    app.ctl.set_gain(6, wait=True)
    app.pump_once()
    assert str(app.echem.b_high["state"]) == "normal"
    app.ctl.start_cv("highres", wait=True)
    app.pump_once()
    assert app.graphs.get("CyclicVoltammogram").lines


def test_every_button_has_a_tooltip_naming_its_igor_procedure(app):
    import tkinter as tk
    from stmgui.widgets import Tooltip
    buttons = [w for w in _walk(app.main) + _walk(app.offset) + _walk(app.echem)
               if isinstance(w, tk.Button)]
    assert buttons
    for b in buttons:
        assert hasattr(b, "tooltip"), b["text"]
        if b is app.main.b_code:          # the Button-map button itself
            continue
        assert "stmgui/controller.py" in b.tooltip.text, b["text"]   # names its Python
    tip = app.main.b_find_sup.tooltip
    tip._show()
    assert tip._win is not None and tip._win.winfo_exists()
    tip._hide()
    assert tip._win is None


def _walk(widget):
    out = [widget]
    for child in widget.winfo_children():
        out += _walk(child)
    return out


def test_button_map_window_lists_every_command(app):
    from stmgui.controller import COMMAND_MAP
    app.show_button_map()
    text = app.button_map.text.get("1.0", "end")
    for name, (control, igor, _impl, _calls) in COMMAND_MAP.items():
        assert f"RigController.{name}" in text, name
        assert control in text, control
    assert "stmlab/keithley.py:" in text and "TestVirtualGround" in text


def test_right_click_opens_the_inspector_with_the_python(app):
    from stmgui import widgets
    assert widgets.INSPECT_HOOK is not None
    # The button carries the right-click bindings (the root is withdrawn in
    # tests, so no event can be delivered; call what the binding calls).
    bound = app.main.b_find_sup.bind()
    assert "<Button-3>" in bound and "<Button-2>" in bound
    widgets.INSPECT_HOOK(widgets.tip_text(app.ctl.find_suppress))
    app.root.update()
    assert app.inspector is not None
    text = app.inspector.text.get("1.0", "end")
    assert "stmgui/controller.py:" in text and "stmlab/keithley.py:" in text
    # The panel button opens the full Button map.
    app.main.b_code.invoke()
    assert app.button_map is not None and app.button_map.winfo_exists()
    assert "Which code runs this?" == app.main.b_code["text"]
