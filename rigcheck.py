"""rigcheck: a bench window for a rig -- the card, its inputs and outputs,
the Keithley and the actuator, one thing at a time, nothing automatic.

    python rigcheck.py                                 the card(s) this PC sees
    python rigcheck.py --simulate                      a pretend card (the MacBook)
    python rigcheck.py --config configs/newpc_rig.json the Keithley address and the
                                                       actuator's port from a config

Three tabs:

Card      every DAQ device the driver sees, with Details (channels, rates,
          ranges, serial number) and a self-test. Tick input channels and
          Start: each one's mean, rms noise, min and max, refreshed a few
          times a second, and the last burst drawn as a scope trace. Tick
          output channels, give each a DC value or a sine or square wave,
          Apply; "All outputs 0 V" is one button and also what closing the
          window does. A limit box refuses anything beyond +/- that many
          volts, so a slip of the finger cannot put 10 V on a cable.
Keithley  Connect over GPIB (the amplifier is left as it is), zero check
          on/off, zero correct, suppress on/off, the gain.
Actuator  Find ports, connect to the Agilis (or a NanoPZ), read its
          firmware and step counter, step apart or closer, and a click test:
          three single steps apart, the counter read before and after, and
          then it asks you whether you heard it, and says what to do next
          either way.

Wiring the loop tests on this window: output a 1 V sine on the bias output,
tick the voltage input, and the scope shows the sine; move the wire and the
piezo output shows the same. That is bring-up steps 2 and 3 by eye; the
program's own pass/fail version is python -m stmlab.main bringup.
"""
from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from stmlab.config import RigConfig                                  # noqa: E402
from stmlab.tklook import _light_window, windows_look                # noqa: E402

__version__ = "v1"
log = logging.getLogger("rigcheck")

TERMINALS = ("card default", "differential", "RSE", "NRSE")
MODES = ("DC", "sine", "square")


# --------------------------------------------------------------------------
# The card, real or pretend, behind one small interface
# --------------------------------------------------------------------------

def _terminal(name: str):
    """A TERMINALS entry -> nidaqmx TerminalConfiguration."""
    from nidaqmx.constants import TerminalConfiguration as TC
    key = {"card default": "DEFAULT", "differential": "DIFF", "RSE": "RSE",
           "NRSE": "NRSE"}[name]
    member = getattr(TC, key, None)
    if member is None and key == "DIFF":
        member = getattr(TC, "DIFFERENTIAL")
    return member


def waveform(mode: str, volts: float, amp: float, freq: float, offset: float,
             rate: float, n: int) -> np.ndarray:
    """One channel's buffer: a constant, or a sine or square of whole-Hz
    frequency so that a 1 s buffer repeats without a seam."""
    t = np.arange(n) / rate
    if mode == "DC":
        return np.full(n, float(volts))
    f = max(1.0, round(float(freq)))
    if mode == "sine":
        return offset + amp * np.sin(2 * np.pi * f * t)
    return offset + amp * np.where(np.sin(2 * np.pi * f * t) >= 0, 1.0, -1.0)


class RealDaq:
    """NI-DAQmx: discovery, a finite input burst, a continuous output."""

    def __init__(self):
        self._ao = None
        self._ao_device = None
        self._ao_channels: list[str] = []

    def devices(self) -> list[dict]:
        import nidaqmx.system
        sysm = nidaqmx.system.System.local()
        v = sysm.driver_version
        out = []
        for d in sysm.devices:
            out.append({"name": d.name, "product": d.product_type,
                        "ai": [c.name for c in d.ai_physical_chans],
                        "ao": [c.name for c in d.ao_physical_chans],
                        "driver": f"{v.major_version}.{v.minor_version}.{v.update_version}"})
        return out

    def details(self, name: str) -> str:
        import nidaqmx.system
        d = nidaqmx.system.System.local().devices[name]
        lines = [f"{name}: {d.product_type}"]

        def row(label, getter, fmt=str):
            try:
                lines.append(f"  {label:<28} {fmt(getter())}")
            except Exception as exc:                          # noqa: BLE001
                lines.append(f"  {label:<28} (not reported: "
                             f"{str(exc).splitlines()[0][:60]})")
        row("serial number", lambda: d.serial_num, lambda x: f"{x:08X}")
        row("bus", lambda: d.bus_type)
        row("simulated in NI MAX", lambda: d.dev_is_simulated)
        row("AI channels", lambda: len(d.ai_physical_chans))
        row("AI simultaneous sampling", lambda: d.ai_simultaneous_sampling_supported)
        row("AI max rate, one channel", lambda: d.ai_max_single_chan_rate,
            lambda x: f"{x:,.0f} S/s")
        row("AI max rate, many channels", lambda: d.ai_max_multi_chan_rate,
            lambda x: f"{x:,.0f} S/s (aggregate)")
        row("AI voltage ranges", lambda: d.ai_voltage_rngs,
            lambda r: ", ".join(f"{r[i]:g}..{r[i + 1]:g} V" for i in range(0, len(r), 2)))
        row("AO channels", lambda: len(d.ao_physical_chans))
        row("AO max rate", lambda: d.ao_max_rate, lambda x: f"{x:,.0f} S/s")
        row("AO voltage ranges", lambda: d.ao_voltage_rngs,
            lambda r: ", ".join(f"{r[i]:g}..{r[i + 1]:g} V" for i in range(0, len(r), 2)))
        row("counters", lambda: len(d.ci_physical_chans))
        row("PFI / terminals", lambda: [t for t in d.terminals if "PFI" in t],
            lambda t: f"{len(t)}: {', '.join(x.split('/')[-1] for x in t[:16])}"
                      + (" ..." if len(t) > 16 else ""))
        row("AI channel names", lambda: [c.name.split("/")[-1] for c in d.ai_physical_chans],
            lambda t: " ".join(t))
        row("AO channel names", lambda: [c.name.split("/")[-1] for c in d.ao_physical_chans],
            lambda t: " ".join(t))
        return "\n".join(lines)

    def self_test(self, name: str) -> str:
        import nidaqmx.system
        d = nidaqmx.system.System.local().devices[name]
        d.self_test_device()                       # raises when it fails
        return f"{name}: self-test passed"

    # -- inputs ---------------------------------------------------------------

    def read(self, channels: list[str], terminal: str, range_v: float,
             rate: float, n: int) -> np.ndarray:
        """One finite burst, (k, n) volts."""
        import nidaqmx
        from nidaqmx.constants import AcquisitionType
        with nidaqmx.Task("rigcheck_ai") as t:
            for ch in channels:
                t.ai_channels.add_ai_voltage_chan(
                    ch, terminal_config=_terminal(terminal),
                    min_val=-range_v, max_val=range_v)
            t.timing.cfg_samp_clk_timing(rate, sample_mode=AcquisitionType.FINITE,
                                         samps_per_chan=n)
            data = t.read(number_of_samples_per_channel=n, timeout=10.0)
        return np.atleast_2d(np.asarray(data, dtype=float))

    # -- outputs --------------------------------------------------------------

    def drive(self, device: str, buffers: dict[str, np.ndarray], rate: float) -> str:
        """Start (or restart) a continuous output of ``buffers``
        ({channel: 1 s of samples}); an empty dict stops the output."""
        import nidaqmx
        from nidaqmx.constants import AcquisitionType
        self.stop_output()
        if not buffers:
            return "outputs stopped"
        chans = list(buffers)
        task = nidaqmx.Task("rigcheck_ao")
        try:
            for ch in chans:
                task.ao_channels.add_ao_voltage_chan(ch, min_val=-10.0, max_val=10.0)
            n = len(next(iter(buffers.values())))
            task.timing.cfg_samp_clk_timing(rate, sample_mode=AcquisitionType.CONTINUOUS,
                                            samps_per_chan=n)
            data = np.vstack([buffers[ch] for ch in chans])
            task.write(data[0] if len(chans) == 1 else data, auto_start=False)
            task.start()
        except Exception:
            task.close()
            raise
        self._ao, self._ao_device, self._ao_channels = task, device, chans
        granted = float(task.timing.samp_clk_rate)
        return (f"driving {', '.join(c.split('/')[-1] for c in chans)} at "
                f"{granted:,.0f} S/s")

    def stop_output(self) -> None:
        if self._ao is not None:
            try:
                self._ao.stop()
            except Exception:
                pass
            try:
                self._ao.close()
            except Exception:
                pass
            self._ao = None

    def zero(self, device: str, channels: list[str]) -> str:
        """Every listed output to 0 V: a short run of zeros, then stop, so a
        card that drops idle outputs and one that holds them both end at 0."""
        chans = sorted(set(channels) | set(self._ao_channels))
        if not chans:
            self.stop_output()
            return "no outputs were driven"
        self.drive(device, {ch: np.zeros(2000) for ch in chans}, 20_000.0)
        time.sleep(0.15)
        self.stop_output()
        self._ao_channels = []
        return "all outputs at 0 V"


class SimDaq:
    """A pretend one-card rig: ai0..ai3 read back ao0..ao3 (a loop cable in
    the imagination), the other inputs read noise."""

    def __init__(self):
        self.buffers: dict[str, np.ndarray] = {}
        self.rate = 50_000.0
        self.t0 = time.monotonic()
        self.rng = np.random.default_rng(1)

    def devices(self) -> list[dict]:
        return [{"name": "Dev1", "product": "USB-6453 (simulated)",
                 "ai": [f"Dev1/ai{i}" for i in range(32)],
                 "ao": [f"Dev1/ao{i}" for i in range(4)], "driver": "simulated"}]

    def details(self, name: str) -> str:
        return (f"{name}: USB-6453 (simulated)\n  32 AI (16 differential pairs), 20 bit\n"
                "  4 AO, 16 bit, +/-10 V\n  ai0..ai3 read back ao0..ao3 here, as if "
                "looped with a cable; the rest read noise")

    def self_test(self, name: str) -> str:
        return f"{name}: self-test passed (simulated)"

    def read(self, channels, terminal, range_v, rate, n) -> np.ndarray:
        t = (time.monotonic() - self.t0) + np.arange(n) / rate
        out = np.zeros((len(channels), n))
        for k, ch in enumerate(channels):
            src = ch.replace("/ai", "/ao")
            buf = self.buffers.get(src)
            if buf is not None:
                idx = (np.round(t * self.rate).astype(int)) % buf.size
                out[k] = buf[idx]
            out[k] += self.rng.normal(0.0, 0.0008, n)
        time.sleep(n / rate)
        return np.clip(out, -range_v, range_v)

    def drive(self, device, buffers, rate) -> str:
        self.buffers = dict(buffers)
        self.rate = rate
        return ("outputs stopped" if not buffers else
                f"driving {', '.join(c.split('/')[-1] for c in buffers)} (simulated)")

    def stop_output(self) -> None:
        pass

    def zero(self, device, channels) -> str:
        self.buffers = {}
        return "all outputs at 0 V (simulated)"


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------

def run(cfg: RigConfig, simulate: bool, autoclose: float | None = None,
        zoom: float | None = None) -> int:
    import tkinter as tk
    from tkinter import messagebox, ttk

    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure

    daq = SimDaq() if simulate else RealDaq()
    events: queue.Queue = queue.Queue()

    root = tk.Tk()
    root.title(f"rigcheck {__version__}" + ("  [simulate]" if simulate else ""))
    style = ttk.Style(root)
    if zoom is None:
        zoom = 1.2 if sys.platform == "darwin" else 1.0
    want_clam = sys.platform == "darwin" or os.environ.get("PULLOUT_THEME") == "clam"
    if want_clam and "clam" in style.theme_names():
        windows_look(root, style, zoom)
    elif zoom != 1.0:
        root.tk.call("tk", "scaling", float(root.tk.call("tk", "scaling")) * zoom)
    _light_window(root)

    status = tk.Label(root, text="ready", anchor="w", font=("Arial", 10, "bold"),
                      fg="#1b5e20")
    status.pack(side="bottom", fill="x", padx=8, pady=(0, 6))

    def say(text: str, level: str = "info") -> None:
        colour = {"ok": "#1b5e20", "bad": "#b00000", "warn": "#b06000",
                  "info": "#202020"}[level]
        status.config(text=text, fg=colour)
        log.info("%s", text)

    def post(kind: str, **payload):
        events.put((kind, payload))

    style.configure("Big.TNotebook.Tab", font=("Arial", 11, "bold"), padding=(14, 4))
    nb = ttk.Notebook(root, style="Big.TNotebook")
    nb.pack(fill="both", expand=True, padx=6, pady=6)

    # ======================================================================
    # Card
    # ======================================================================
    card = ttk.Frame(nb)
    nb.add(card, text="Card")
    left = ttk.Frame(card)
    left.pack(side="left", fill="y", padx=(0, 8))
    right = ttk.Frame(card)
    right.pack(side="left", fill="both", expand=True)

    # -- devices ---------------------------------------------------------------
    db = ttk.LabelFrame(left, text="Devices the driver sees")
    db.pack(fill="x", pady=(0, 6))
    dev_var = tk.StringVar()
    dev_box = ttk.Combobox(db, textvariable=dev_var, width=34, state="readonly")
    dev_box.grid(row=0, column=0, columnspan=2, padx=4, pady=3, sticky="w")
    found: dict[str, dict] = {}

    def refresh_devices():
        try:
            devs = daq.devices()
        except Exception as exc:                                  # noqa: BLE001
            say(f"NI-DAQmx: {exc}", "bad")
            return
        found.clear()
        for d in devs:
            found[d["name"]] = d
        names = [f"{d['name']}   {d['product']}" for d in devs]
        dev_box.config(values=names)
        if names:
            dev_box.current(0)
            on_device()
            say(f"NI-DAQmx {devs[0]['driver']}: {len(devs)} device(s)", "ok")
        else:
            say("no DAQ device found: is it plugged in and does NI MAX see it?", "bad")

    def current_device() -> str:
        return dev_var.get().split()[0] if dev_var.get() else ""

    def show_details():
        name = current_device()
        if not name:
            return
        try:
            text = daq.details(name)
        except Exception as exc:                                  # noqa: BLE001
            say(f"details: {exc}", "bad")
            return
        win = tk.Toplevel(root)
        _light_window(win)
        win.title(f"{name}: details")
        box = tk.Text(win, width=90, height=22, font=("Courier", 9), wrap="none")
        box.pack(fill="both", expand=True, padx=6, pady=6)
        box.insert("1.0", text)
        box.config(state="disabled")

    def self_test():
        name = current_device()
        if not name:
            return
        try:
            say(daq.self_test(name), "ok")
        except Exception as exc:                                  # noqa: BLE001
            say(f"{name}: self-test FAILED: {exc}", "bad")

    ttk.Button(db, text="Refresh", command=refresh_devices).grid(row=1, column=0, padx=4, pady=2, sticky="ew")
    ttk.Button(db, text="Details...", command=show_details).grid(row=1, column=1, padx=4, pady=2, sticky="ew")
    ttk.Button(db, text="Self-test", command=self_test).grid(row=2, column=0, padx=4, pady=(0, 3), sticky="ew")

    # -- inputs ----------------------------------------------------------------
    ib = ttk.LabelFrame(left, text="Inputs: tick channels, Start")
    ib.pack(fill="x", pady=(0, 6))
    ai_frame = ttk.Frame(ib)
    ai_frame.grid(row=0, column=0, columnspan=6, sticky="w", padx=2)
    ai_vars: dict[str, tk.BooleanVar] = {}
    term_var = tk.StringVar(value=TERMINALS[0])
    range_var = tk.StringVar(value="10")
    rate_var = tk.StringVar(value="10000")
    n_var = tk.StringVar(value="2000")
    ttk.Label(ib, text="terminal").grid(row=1, column=0, sticky="w", padx=(4, 1))
    ttk.Combobox(ib, textvariable=term_var, values=TERMINALS, width=12,
                 state="readonly").grid(row=1, column=1, sticky="w")
    ttk.Label(ib, text="range +/-").grid(row=1, column=2, sticky="e", padx=(8, 1))
    ttk.Combobox(ib, textvariable=range_var, values=("10", "5", "2.5", "1", "0.2"),
                 width=5).grid(row=1, column=3, sticky="w")
    ttk.Label(ib, text="V").grid(row=1, column=4, sticky="w")
    ttk.Label(ib, text="rate (S/s)").grid(row=2, column=0, sticky="w", padx=(4, 1))
    ttk.Entry(ib, textvariable=rate_var, width=8).grid(row=2, column=1, sticky="w")
    ttk.Label(ib, text="samples").grid(row=2, column=2, sticky="e", padx=(8, 1))
    ttk.Entry(ib, textvariable=n_var, width=7).grid(row=2, column=3, sticky="w")
    mon = {"on": False, "thread": None}
    start_btn = ttk.Button(ib, text="Start", command=lambda: start_monitor())
    start_btn.grid(row=3, column=0, columnspan=2, padx=4, pady=3, sticky="ew")
    ttk.Button(ib, text="Stop", command=lambda: stop_monitor()).grid(
        row=3, column=2, columnspan=2, padx=4, pady=3, sticky="ew")

    # -- outputs ---------------------------------------------------------------
    ob = ttk.LabelFrame(left, text="Outputs: tick, set, Apply")
    ob.pack(fill="x", pady=(0, 6))
    ao_rows: dict[str, dict] = {}
    ao_frame = ttk.Frame(ob)
    ao_frame.grid(row=0, column=0, columnspan=6, sticky="w", padx=2)
    for c, head in enumerate(("", "mode", "V / amplitude", "Hz", "offset V")):
        ttk.Label(ao_frame, text=head, font=("Arial", 9, "bold")).grid(row=0, column=c, padx=3)
    limit_var = tk.StringVar(value="5")
    ao_rate_var = tk.StringVar(value="50000")
    ttk.Label(ob, text="limit: no output beyond +/-").grid(row=1, column=0, sticky="w", padx=(4, 1))
    ttk.Entry(ob, textvariable=limit_var, width=5).grid(row=1, column=1, sticky="w")
    ttk.Label(ob, text="V").grid(row=1, column=2, sticky="w")
    ttk.Label(ob, text="rate (S/s)").grid(row=1, column=3, sticky="e", padx=(8, 1))
    ttk.Entry(ob, textvariable=ao_rate_var, width=8).grid(row=1, column=4, sticky="w")
    ttk.Button(ob, text="Apply", command=lambda: apply_outputs()).grid(
        row=2, column=0, columnspan=2, padx=4, pady=3, sticky="ew")
    zero_btn = tk.Button(ob, text="All outputs 0 V", command=lambda: zero_outputs(),
                         bg="#c62828", fg="white", activebackground="#8e0000",
                         activeforeground="white", font=("Arial", 10, "bold"))
    zero_btn.grid(row=2, column=2, columnspan=3, padx=4, pady=3, sticky="ew")

    def on_device(_e=None):
        """Rebuild the channel tick boxes for the device chosen."""
        for w in ai_frame.winfo_children():
            w.destroy()
        for w in list(ao_frame.winfo_children())[5:]:
            w.destroy()
        ai_vars.clear()
        ao_rows.clear()
        d = found.get(current_device())
        if not d:
            return
        for i, ch in enumerate(d["ai"]):
            var = tk.BooleanVar(value=False)
            ai_vars[ch] = var
            ttk.Checkbutton(ai_frame, text=ch.split("/")[-1], variable=var).grid(
                row=i // 8, column=i % 8, sticky="w", padx=1)
        for i, ch in enumerate(d["ao"]):
            r = i + 1
            on = tk.BooleanVar(value=False)
            mode = tk.StringVar(value="DC")
            volts = tk.StringVar(value="0")
            freq = tk.StringVar(value="10")
            offset = tk.StringVar(value="0")
            ttk.Checkbutton(ao_frame, text=ch.split("/")[-1], variable=on).grid(
                row=r, column=0, sticky="w", padx=2)
            ttk.Combobox(ao_frame, textvariable=mode, values=MODES, width=7,
                         state="readonly").grid(row=r, column=1, padx=2)
            ttk.Entry(ao_frame, textvariable=volts, width=8).grid(row=r, column=2, padx=2)
            ttk.Entry(ao_frame, textvariable=freq, width=6).grid(row=r, column=3, padx=2)
            ttk.Entry(ao_frame, textvariable=offset, width=7).grid(row=r, column=4, padx=2)
            ao_rows[ch] = {"on": on, "mode": mode, "volts": volts, "freq": freq,
                           "offset": offset}
    dev_box.bind("<<ComboboxSelected>>", on_device)

    # -- the readings and the scope -------------------------------------------
    rb = ttk.LabelFrame(right, text="Readings (the last burst)")
    rb.pack(fill="x")
    table = tk.Text(rb, width=70, height=9, font=("Courier", 10), relief="flat",
                    state="disabled", background=root.cget("background"))
    table.pack(fill="x", padx=4, pady=3)
    fig = Figure(figsize=(7.2, 4.2), dpi=100)
    ax = fig.add_subplot(111)
    canvas = FigureCanvasTkAgg(fig, master=right)
    canvas.get_tk_widget().pack(fill="both", expand=True, pady=(6, 0))

    def set_table(text: str):
        table.config(state="normal")
        table.delete("1.0", "end")
        table.insert("1.0", text)
        table.config(state="disabled")

    def numbers(rate_s: str, n_s: str, range_s: str):
        try:
            rate, n, rng = float(rate_s), int(float(n_s)), float(range_s)
        except ValueError:
            raise ValueError("rate, samples and range must be numbers") from None
        if rate <= 0 or n < 10 or rng <= 0:
            raise ValueError("rate and range must be positive, samples at least 10")
        return rate, n, rng

    def monitor_loop(channels, terminal, rng, rate, n):
        while mon["on"]:
            try:
                data = daq.read(channels, terminal, rng, rate, n)
            except Exception as exc:                              # noqa: BLE001
                post("error", text=f"input read failed: {exc}")
                mon["on"] = False
                return
            post("burst", channels=channels, data=data, rate=rate)
            time.sleep(0.1)

    def start_monitor():
        channels = [ch for ch, v in ai_vars.items() if v.get()]
        if not channels:
            say("tick at least one input channel", "warn")
            return
        try:
            rate, n, rng = numbers(rate_var.get(), n_var.get(), range_var.get())
        except ValueError as exc:
            say(str(exc), "bad")
            return
        stop_monitor()
        mon["on"] = True
        mon["thread"] = threading.Thread(
            target=monitor_loop, args=(channels, term_var.get(), rng, rate, n),
            daemon=True)
        mon["thread"].start()
        say(f"reading {', '.join(c.split('/')[-1] for c in channels)} "
            f"({term_var.get()}, +/-{rng:g} V, {n} samples at {rate:,.0f} S/s)", "ok")

    def stop_monitor():
        if mon["on"]:
            mon["on"] = False
            t = mon["thread"]
            if t is not None:
                t.join(timeout=5.0)
            say("input reading stopped")

    def show_burst(channels, data, rate):
        lines = [f"{'channel':<10}{'mean V':>12}{'rms noise':>12}{'min V':>10}{'max V':>10}"]
        for ch, row in zip(channels, data):
            lines.append(f"{ch.split('/')[-1]:<10}{row.mean():>12.5f}{row.std():>12.5f}"
                         f"{row.min():>10.4f}{row.max():>10.4f}")
        set_table("\n".join(lines))
        ax.clear()
        t_ms = np.arange(data.shape[1]) / rate * 1e3
        for ch, row in zip(channels, data):
            ax.plot(t_ms, row, lw=0.8, label=ch.split("/")[-1])
        ax.set_xlabel("ms")
        ax.set_ylabel("V")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
        ax.set_title("the last burst", fontsize=9)
        canvas.draw_idle()

    def apply_outputs():
        try:
            limit = abs(float(limit_var.get()))
            rate = float(ao_rate_var.get())
        except ValueError:
            say("the limit and the rate must be numbers", "bad")
            return
        if rate <= 0:
            say("the output rate must be positive", "bad")
            return
        buffers = {}
        n = int(round(rate))                                  # one second
        for ch, r in ao_rows.items():
            if not r["on"].get():
                continue
            try:
                volts = float(r["volts"].get())
                freq = float(r["freq"].get())
                offset = float(r["offset"].get())
            except ValueError:
                say(f"{ch}: V, Hz and offset must be numbers", "bad")
                return
            mode = r["mode"].get()
            peak = abs(volts) if mode == "DC" else abs(offset) + abs(volts)
            if peak > limit:
                say(f"{ch.split('/')[-1]}: {peak:g} V would exceed the limit of "
                    f"+/-{limit:g} V; raise the limit if you mean it", "bad")
                return
            buffers[ch] = waveform(mode, volts, volts, freq, offset, rate, n)
        try:
            say(daq.drive(current_device(), buffers, rate), "ok")
        except Exception as exc:                                  # noqa: BLE001
            say(f"output failed: {exc}", "bad")

    def zero_outputs():
        try:
            say(daq.zero(current_device(), list(ao_rows)), "ok")
        except Exception as exc:                                  # noqa: BLE001
            say(f"could not zero the outputs: {exc}", "bad")

    # ======================================================================
    # Keithley
    # ======================================================================
    kt = ttk.Frame(nb)
    nb.add(kt, text="Keithley")
    kb = ttk.LabelFrame(kt, text="Keithley 428 over GPIB")
    kb.pack(fill="x", padx=4, pady=4)
    k = {"inst": None}
    res_var = tk.StringVar(value=cfg.keithley.resource)
    ttk.Label(kb, text="VISA resource").grid(row=0, column=0, sticky="w", padx=4)
    ttk.Entry(kb, textvariable=res_var, width=24).grid(row=0, column=1, columnspan=2, sticky="w")
    k_lbl = tk.Label(kb, text="not connected", anchor="w", font=("Arial", 9))
    k_lbl.grid(row=0, column=3, columnspan=3, sticky="w", padx=8)

    def k_connect():
        from stmlab.keithley import Keithley428, SimulatedKeithley
        k_disconnect()
        cfg.keithley.resource = res_var.get().strip()
        try:
            inst = SimulatedKeithley(cfg.keithley) if simulate else Keithley428(cfg.keithley)
            inst.open(init=False)                  # left exactly as it is
        except Exception as exc:                                  # noqa: BLE001
            say(f"Keithley: {exc}", "bad")
            k_lbl.config(text="not connected")
            return
        k["inst"] = inst
        k_lbl.config(text=f"connected at {cfg.keithley.resource}"
                          + (" (simulated)" if simulate else "")
                          + "; its state is as the front panel left it")
        say("Keithley connected; nothing was sent to it yet", "ok")

    def k_disconnect():
        if k["inst"] is not None:
            try:
                k["inst"].close(inert=False)
            except Exception:
                pass
            k["inst"] = None
            k_lbl.config(text="not connected")

    def k_do(label, fn):
        if k["inst"] is None:
            say("connect the Keithley first", "warn")
            return
        try:
            fn(k["inst"])
            say(f"Keithley: {label}", "ok")
        except Exception as exc:                                  # noqa: BLE001
            say(f"Keithley {label} failed: {exc}", "bad")

    zc_var = tk.BooleanVar(value=False)
    sup_var = tk.BooleanVar(value=False)
    gain_var = tk.StringVar(value=str(cfg.keithley.gain_exponent))
    ttk.Button(kb, text="Connect", command=k_connect).grid(row=1, column=0, padx=4, pady=3, sticky="ew")
    ttk.Button(kb, text="Disconnect", command=k_disconnect).grid(row=1, column=1, padx=4, pady=3, sticky="ew")
    ttk.Checkbutton(kb, text="Zero check", variable=zc_var,
                    command=lambda: k_do(f"zero check {'ON' if zc_var.get() else 'off'}",
                                         lambda i: i.zero_check(zc_var.get()))).grid(
        row=2, column=0, sticky="w", padx=6)
    ttk.Button(kb, text="Zero correct",
               command=lambda: k_do("zero correct sent (do it with zero check ON)",
                                    lambda i: i.zero_correct())).grid(
        row=2, column=1, padx=4, pady=2, sticky="ew")
    ttk.Checkbutton(kb, text="Suppress I", variable=sup_var,
                    command=lambda: k_do(f"suppress {'ON' if sup_var.get() else 'off'}",
                                         lambda i: i.suppress_enable(sup_var.get()))).grid(
        row=2, column=2, sticky="w", padx=6)
    ttk.Label(kb, text="gain 10^").grid(row=3, column=0, sticky="e", padx=4)
    ttk.Entry(kb, textvariable=gain_var, width=4).grid(row=3, column=1, sticky="w")

    def k_gain():
        try:
            n = int(gain_var.get())
        except ValueError:
            say("the gain exponent must be a whole number 3..11", "bad")
            return
        if not 3 <= n <= 11:
            say("the gain exponent must be 3..11", "bad")
            return
        k_do(f"gain 1e{n} V/A", lambda i: i.set_gain(n))
    ttk.Button(kb, text="Set gain", command=k_gain).grid(row=3, column=2, padx=4, pady=2, sticky="ew")
    ttk.Label(kt, text="Connect leaves the amplifier exactly as it is. The usual order on "
                       "the rig: zero check ON, Zero correct, zero check off, then the "
                       "amplifier reads. Suppress only acts while ON.",
              font=("Arial", 9), wraplength=560, justify="left").pack(anchor="w", padx=8, pady=4)

    # ======================================================================
    # Actuator
    # ======================================================================
    at = ttk.Frame(nb)
    nb.add(at, text="Actuator")
    ab = ttk.LabelFrame(at, text="Coarse actuator (Newport Agilis or NanoPZ)")
    ab.pack(fill="x", padx=4, pady=4)
    a = {"act": None, "busy": False}
    KIND_NAMES = {"agilis": "Agilis AG-UC2/UC8", "nanopz": "NanoPZ PZC200"}
    kind_var = tk.StringVar(value=KIND_NAMES.get(cfg.actuator.kind.lower(), KIND_NAMES["agilis"]))
    port_var = tk.StringVar(value=cfg.actuator.port)
    steps_var = tk.StringVar(value=str(cfg.actuator.step_size))
    amp_var = tk.StringVar(value=str(cfg.actuator.step_amplitude))
    ttk.Label(ab, text="controller").grid(row=0, column=0, sticky="w", padx=4)
    ttk.Combobox(ab, textvariable=kind_var, values=tuple(KIND_NAMES.values()), width=18,
                 state="readonly").grid(row=0, column=1, sticky="w")
    ttk.Label(ab, text="port").grid(row=0, column=2, sticky="e", padx=(8, 2))
    port_box = ttk.Combobox(ab, textvariable=port_var, width=8, values=(cfg.actuator.port,))
    port_box.grid(row=0, column=3, sticky="w")
    ports_txt = tk.Text(ab, width=70, height=4, font=("Courier", 9), relief="flat",
                        state="disabled", background=root.cget("background"))
    ports_txt.grid(row=1, column=0, columnspan=6, sticky="w", padx=4)
    a_lbl = tk.Label(ab, text="not connected", anchor="w", font=("Arial", 9),
                     wraplength=560, justify="left")
    a_lbl.grid(row=4, column=0, columnspan=6, sticky="w", padx=4, pady=(2, 4))

    def kind_now() -> str:
        return next(kk for kk, v in KIND_NAMES.items() if v == kind_var.get())

    def find_ports():
        from stmlab.actuator import list_serial_ports
        try:
            ports = list_serial_ports()
        except Exception as exc:                                  # noqa: BLE001
            say(f"ports: {exc}", "bad")
            return
        ports_txt.config(state="normal")
        ports_txt.delete("1.0", "end")
        ports_txt.insert("1.0", "\n".join(f"{d:<8} {desc}" for d, desc in ports)
                         or "no serial ports: is the controller's USB plugged in?")
        ports_txt.config(state="disabled")
        port_box.config(values=tuple(d for d, _ in ports) or (port_var.get(),))
        newport = [d for d, desc in ports if "AG-UC" in desc.upper() or "NEWPORT" in desc.upper()]
        if newport:
            port_var.set(newport[0])
            say(f"the Newport port is {newport[0]}", "ok")
        else:
            say(f"{len(ports)} serial port(s); none says Newport, pick one", "warn")

    def a_connect():
        from stmlab.actuator import KINDS, SimulatedActuator
        a_disconnect()
        cfg.actuator.kind = kind_now()
        cfg.actuator.port = port_var.get().strip()
        try:
            cfg.actuator.step_size = max(1, int(steps_var.get()))
            cfg.actuator.step_amplitude = max(1, min(50, int(amp_var.get())))
        except ValueError:
            say("steps and amplitude must be whole numbers", "bad")
            return
        try:
            if simulate:
                act = SimulatedActuator(cfg)
                ident = {"version": "simulated", "status": "0", "position": 0}
            else:
                act = KINDS[cfg.actuator.kind](cfg)
                ident = act.identify()
        except Exception as exc:                                  # noqa: BLE001
            say(f"actuator: {exc}", "bad")
            a_lbl.config(text="not connected. Nothing answering at all usually means the "
                              "controller is asleep: unplug its USB cable, plug it back "
                              "in, Connect again.")
            return
        a["act"] = act
        a_lbl.config(text=f"connected on {cfg.actuator.port}: {ident.get('version', '?')}, "
                          f"status {ident.get('status')!r} (0 = ready), step counter "
                          f"{ident.get('position')}")
        say("actuator connected", "ok")

    def a_disconnect():
        if a["act"] is not None:
            try:
                a["act"].close()
            except Exception:
                pass
            a["act"] = None
            a_lbl.config(text="not connected")

    def a_move(closer: bool, count: int | None = None, then=None):
        """A move in a thread (a run of steps takes a while)."""
        act = a["act"]
        if act is None:
            say("connect the actuator first", "warn")
            return
        if a["busy"]:
            say("the actuator is still moving", "warn")
            return
        if closer and not messagebox.askyesno(
                "Step closer", "This moves the tip TOWARD the sample, further than the "
                               "fine piezo's whole range. Is the tip clear of the sample?"):
            return
        try:
            cfg.actuator.step_size = max(1, int(steps_var.get())) if count is None else count
            cfg.actuator.step_amplitude = max(1, min(50, int(amp_var.get())))
        except ValueError:
            say("steps and amplitude must be whole numbers", "bad")
            return
        a["busy"] = True

        def work():
            try:
                before = act.position()
                t0 = time.monotonic()
                act.step(closer=closer)
                after = act.position()
                post("moved", closer=closer, before=before, after=after,
                     seconds=time.monotonic() - t0, then=then)
            except Exception as exc:                              # noqa: BLE001
                post("error", text=f"move failed: {exc}")
            finally:
                a["busy"] = False
        threading.Thread(target=work, daemon=True).start()
        say("moving ...", "info")

    def click_test():
        """Three single steps apart, then the question."""
        act = a["act"]
        if act is None:
            say("connect the actuator first", "warn")
            return
        messagebox.showinfo("Click test",
                            "The actuator will make three single steps APART, half a "
                            "second between them. Put your ear near it, press OK, "
                            "and listen for three clicks.")

        def ask(p):
            heard = messagebox.askyesno("Click test", "Did you hear the actuator click?")
            counter = (f"The step counter went {p['before']} -> {p['after']}."
                       if p["before"] is not None and p["after"] is not None
                       else "This controller reports no step counter.")
            if heard:
                a_lbl.config(text=f"CLICK TEST PASSED: you heard it, and {counter} "
                                  "The actuator moves. Next: Step closer once (tip clear "
                                  "of the sample) and check the counter goes the other way.")
                say("click test passed", "ok")
            elif p["before"] is not None and p["after"] is not None and p["after"] != p["before"]:
                a_lbl.config(text=f"No click heard, but {counter} The controller believes "
                                  "it moved: the motor may be too quiet to hear, or the "
                                  "amplitude too low to move the stage. Try amplitude 35, "
                                  "then 50, and listen again.")
                say("click test: counter moved, no sound", "warn")
            else:
                a_lbl.config(text="CLICK TEST FAILED: no click and no counter change. "
                                  "Check, in this order: (1) the controller is on and awake "
                                  "(unplug and replug its USB, Connect again); (2) this is "
                                  "the right port (Find ports: the Newport one); (3) the "
                                  "amplitude (try 35 or 50); (4) the motor cable to the stage.")
                say("click test failed", "bad")
        a_move(closer=False, count=3, then=ask)

    ttk.Button(ab, text="Find ports", command=find_ports).grid(row=2, column=0, padx=4, pady=3, sticky="ew")
    ttk.Button(ab, text="Connect", command=a_connect).grid(row=2, column=1, padx=4, pady=3, sticky="ew")
    ttk.Button(ab, text="Disconnect", command=a_disconnect).grid(row=2, column=2, columnspan=2, padx=4, pady=3, sticky="ew")
    ttk.Label(ab, text="steps").grid(row=3, column=0, sticky="e", padx=4)
    ttk.Entry(ab, textvariable=steps_var, width=5).grid(row=3, column=1, sticky="w")
    ttk.Label(ab, text="amplitude 1..50").grid(row=3, column=2, sticky="e", padx=(8, 2))
    ttk.Entry(ab, textvariable=amp_var, width=5).grid(row=3, column=3, sticky="w")
    bf = ttk.Frame(at)
    bf.pack(fill="x", padx=4)
    ttk.Button(bf, text="Step apart (safe)", command=lambda: a_move(False)).pack(side="left", padx=4)
    ttk.Button(bf, text="Step closer ...", command=lambda: a_move(True)).pack(side="left", padx=4)
    tk.Button(bf, text="Click test (3 steps apart, then it asks you)", command=click_test,
              bg="#2e7d32", fg="white", activebackground="#1b5e20", activeforeground="white",
              font=("Arial", 10, "bold")).pack(side="left", padx=12)
    ttk.Label(at, text="Apart = away from the sample, the safe direction; on this rig the "
                       "Agilis counts it negative. Close Igor first: a serial port belongs to "
                       "one program at a time.",
              font=("Arial", 9), wraplength=560, justify="left").pack(anchor="w", padx=8, pady=4)

    # ======================================================================
    # the heartbeat, start-up and shutdown
    # ======================================================================
    def poll():
        try:
            while True:
                kind, p = events.get_nowait()
                if kind == "burst":
                    show_burst(p["channels"], p["data"], p["rate"])
                elif kind == "moved":
                    counter = (f"counter {p['before']} -> {p['after']}"
                               if p["before"] is not None else "no counter")
                    say(f"moved {'closer' if p['closer'] else 'apart'}: {counter}, "
                        f"{p['seconds']:.2f} s", "ok")
                    if p.get("then"):
                        p["then"](p)
                elif kind == "error":
                    say(p["text"], "bad")
        except queue.Empty:
            pass
        root.after(100, poll)

    def on_close():
        mon["on"] = False
        try:
            daq.zero(current_device(), list(ao_rows))
        except Exception:
            pass
        k_disconnect()
        a_disconnect()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_devices()
    root.after(100, poll)
    if autoclose is not None:
        # A smoke run: inputs on, two outputs driven, the details window,
        # the Keithley and the actuator, then close.
        def smoke():
            for ch in list(ai_vars)[:2]:
                ai_vars[ch].set(True)
            start_monitor()
            rows = list(ao_rows.values())
            if rows:
                rows[0]["on"].set(True)
                rows[0]["mode"].set("sine")
                rows[0]["volts"].set("1")
                rows[0]["freq"].set("50")
            if len(rows) > 1:
                rows[1]["on"].set(True)
                rows[1]["volts"].set("2.5")
            apply_outputs()
        root.after(400, smoke)
        root.after(1200, lambda: (nb.select(kt), k_connect(), zc_var.set(True),
                                  k_do("zero check ON", lambda i: i.zero_check(True))))
        root.after(1600, lambda: (nb.select(at), find_ports(), a_connect(), a_move(False)))
        root.after(2600, lambda: nb.select(card))
        root.after(3600, show_details)
        root.after(int(autoclose * 1000), on_close)
    root.mainloop()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, help="rig config (Keithley address, actuator port)")
    p.add_argument("--simulate", action="store_true", help="a pretend card, no hardware")
    p.add_argument("--zoom", type=float, default=None, help="window scale (Mac: 1.2)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--autoclose", type=float, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    cfg = RigConfig.from_json(args.config) if args.config else RigConfig()
    if args.simulate:
        cfg.simulate = True
    return run(cfg, simulate=args.simulate, autoclose=args.autoclose, zoom=args.zoom)


if __name__ == "__main__":
    raise SystemExit(main())
