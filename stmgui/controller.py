"""Every Igor button, as a method on one object; one worker thread; no Tk.

Igor ran everything on its single GUI thread and polled the Alt key to
abort. Here one worker thread owns the ``Rig`` and executes commands from a
queue in the order they were clicked, so two buttons can never reach the DAQ
card at once. Long commands -- Start Measurement, Start Approach, Find
Suppress, Find Offset, CV -- check :attr:`RigController.stop` between steps,
which is the Alt key.

Results come back through :attr:`events`, a queue of ``(kind, payload)``
tuples the panels drain on a timer:

    "log"       text for the History window
    "error"     text for a warning line (and the History window)
    "busy"/"idle"  a command started / finished (name)
    "readout"   {"current_ua", "junction_mv", "piezo_v", "beep"}
    "highres"   the last background read, for the HighRes graph
    "piezo"     {"volts", "nm"} after any fine-piezo move
    "writing"   True/False: the output task exists (Igor G_HighResOutputTaskStatus)
    "trace"     one generated trace, for the PullOut graphs
    "hist"      (centres, counts) for LogHistOfBlock
    "izero"     a VzeroResult, for the Izero graph
    "izero_time" (saved numbers, izero uA), for Izero_Time
    "suppress"  (new_ua, sweep, readings) after Find Suppress
    "cv"        list of CVCycle, for CyclicVoltammogram
    "counter"   actuator step counter
    "saved"/"attempts"  the two panel counters
    "vzero"     (vzero_mv, izero_ua) for the Voltage_Offset panel
    "gate"      counter electrode mV
    "xpiezo"    X piezo position nm

Igor originals for each command are named in the method docstrings.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from stmlab import analysis, approach, calibrate, echem, keithley, ramps, \
    storage, trace, vzero, xpiezo
from stmlab.approach import ApproachError
from stmlab.config import G0_SIEMENS, ConfigError, RigConfig, validate
from stmlab.instrument import Rig
from stmlab.safety import RigState, SafetyViolation, park_all_outputs, \
    verify_devices

from .state import PARAMS, GuiState

log = logging.getLogger(__name__)

PKG_ROOT = Path(__file__).resolve().parents[1]

# Igor's rungo() bias list, Setup1_STMBJ.ipf:150-156.
IGOR_RUNGO_BIAS_MV = [-100.0, -200.0, -300.0, -400.0, -500.0, -600.0,
                      -700.0, -800.0, -900.0, -100.0, -900.0, -1000.0,
                      -1100.0, -100.0]
IGOR_RUNGO_TRACES_PER_BIAS = 1000

HIST_BLOCK = 100          # LogHistFromBlocks ran on every 100-trace block


class NotReady(RuntimeError):
    """A command needs the output task (Start Writing) or an instrument."""


class QueueLogHandler(logging.Handler):
    """Routes stmlab/stmgui log records into the event queue as 'log'."""

    def __init__(self, events: "queue.Queue[tuple[str, Any]]"):
        super().__init__(level=logging.INFO)
        self.events = events
        self.setFormatter(logging.Formatter("%(levelname).1s %(name)s: "
                                            "%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.put(("log", self.format(record)))
        except Exception:
            pass


class RigController:
    BKGD_PERIOD_S = 0.25          # Igor: CtrlNamedBackground period=15 ticks

    def __init__(self, state: GuiState,
                 events: "queue.Queue[tuple[str, Any]] | None" = None,
                 start_worker: bool = True):
        self.state = state
        self.cfg: RigConfig = state.cfg
        self.opts = state.opts
        self.events: "queue.Queue[tuple[str, Any]]" = events or queue.Queue()

        self.rig: Rig | None = None
        self.amp = None                     # Keithley428 / SimulatedKeithley
        self.gate = None                    # echem.CounterElectrode
        self.xp = None                      # xpiezo.XPiezo

        self.stop = threading.Event()       # Igor's Alt key
        self.busy = threading.Event()
        self.current_command = ""

        self.vzero_tracker = vzero.VzeroTracker(self.cfg)
        self.izero_history: list[tuple[int, float]] = []   # (saved no., uA)
        self.block: list[np.ndarray] = []   # conductances of the open block
        self.last_hist: tuple[np.ndarray, np.ndarray] | None = None
        self.last_suppress: tuple[float, np.ndarray, np.ndarray] | None = None
        self.last_cv: list | None = None
        self.last_trace: dict | None = None
        self.calibrated = False
        self.session_files: list[Path] = []
        self.rejections: dict[str, int] = {}
        self._writer: storage.SessionWriter | None = None

        self._q: "queue.Queue[tuple[str, Callable, tuple, dict, threading.Event | None, list]]" = queue.Queue()
        self._alive = True
        self._handler = QueueLogHandler(self.events)
        for name in ("stmlab", "stmgui"):
            logging.getLogger(name).addHandler(self._handler)
            if logging.getLogger(name).level > logging.INFO or \
                    logging.getLogger(name).level == logging.NOTSET:
                logging.getLogger(name).setLevel(logging.INFO)

        self._thread = threading.Thread(target=self._worker, daemon=True,
                                        name="stmgui-worker")
        if start_worker:
            self._thread.start()

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _emit(self, kind: str, payload: Any = None) -> None:
        self.events.put((kind, payload))

    def _run(self, name: str, fn: Callable, *args, wait: bool = False,
             **kwargs) -> Any:
        """Queue ``fn`` for the worker. ``wait=True`` blocks until it has run
        and re-raises its exception -- the form the tests use."""
        done = threading.Event() if wait else None
        box: list = []
        self._q.put((name, fn, args, kwargs, done, box))
        if done is not None:
            done.wait()
            if box and isinstance(box[0], BaseException):
                raise box[0]
            return box[0] if box else None
        return None

    def _worker(self) -> None:
        while self._alive:
            try:
                name, fn, args, kwargs, done, box = \
                    self._q.get(timeout=self.BKGD_PERIOD_S)
            except queue.Empty:
                if self.opts.bkgd_sampling and self.rig is not None:
                    try:
                        self._background_read()
                    except Exception as exc:
                        self.opts.bkgd_sampling = False
                        self._emit("error", f"background sampling stopped: "
                                            f"{exc}")
                continue

            self.busy.set()
            self.current_command = name
            self._emit("busy", name)
            # Say which Python runs, so the History answers "what did that
            # button do" without opening the source.
            self._emit("log", f"-> {name}: {locate(fn)} "
                              f"{getattr(fn, '__qualname__', repr(fn))}")
            try:
                result = fn(*args, **kwargs)
                box.append(result)
            except (SafetyViolation, ApproachError, ConfigError, NotReady,
                    keithley.KeithleyError, echem.EChemError,
                    xpiezo.XPiezoError) as exc:
                log.error("%s: %s", name, exc)
                self._emit("error", f"{name}: {exc}")
                box.append(exc)
            except Exception as exc:              # noqa: BLE001
                log.exception("%s failed", name)
                self._emit("error", f"{name}: {type(exc).__name__}: {exc}")
                box.append(exc)
            finally:
                self.busy.clear()
                self.current_command = ""
                self._emit("idle", name)
                if done is not None:
                    done.set()

    def wait_idle(self, timeout: float = 60.0) -> None:
        """Block until the queue is drained. For tests and macros."""
        self._run("noop", lambda: None, wait=True)
        del timeout

    def shutdown(self) -> None:
        """Igor: closing the experiment. Kill tasks, release instruments."""
        self.stop.set()
        try:
            self._run("Shutdown", self._kill_tasks_impl, wait=True)
        except Exception:
            pass
        if self.amp is not None:
            try:
                self.amp.close()
            except Exception:
                pass
            self.amp = None
        self._alive = False
        for name in ("stmlab", "stmgui"):
            logging.getLogger(name).removeHandler(self._handler)

    def request_stop(self) -> None:
        """The Alt key (Functions_STMBJ.ipf:1697)."""
        self.stop.set()
        self._emit("log", "stop requested; finishing the current step")

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _require_rig(self) -> Rig:
        if self.rig is None:
            raise NotReady("the output task is not running -- press "
                           "Start Writing first (Igor: StartHighResWritingTask)")
        return self.rig

    def _require_amp(self):
        if self.amp is None:
            raise NotReady("the Keithley 428 is not connected (GPIB open "
                           "failed at startup; see the History window)")
        return self.amp

    def _sync_piezo(self) -> None:
        if self.rig is not None:
            self.opts.piezo_readout_v = self.rig.piezo_v
            self._emit("piezo", {"volts": self.rig.piezo_v,
                                 "nm": self.rig.piezo_nm})

    def igor_globals(self) -> dict[str, Any]:
        """Every panel value, by its Igor name. Written into each data file."""
        return {name: p.get(self.state) for name, p in PARAMS.items()}

    def data_dir(self) -> Path:
        """Igor's MakePath: a dated folder under the data directory."""
        base = Path(self.opts.data_dir)
        if not base.is_absolute():
            base = PKG_ROOT / base
        path = base / time.strftime("%Y%m%d")
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Instruments at startup  (Igor InitializeExperiment)
    # ------------------------------------------------------------------

    def connect_instruments(self, wait: bool = False) -> None:
        """SetUpGPIB_Keithley() at InitializeExperiment, Setup1_STMBJ.ipf:67."""
        return self._run("Connect instruments", self._connect_impl, wait=wait)

    def _connect_impl(self) -> None:
        try:
            self.amp = keithley.make_keithley(self.cfg).open()
            self.opts.zero_check = True         # C1P0B0N0X
            self.opts.suppress_on = False
            log.info("Keithley 428 ready (%s)",
                     "simulated" if self.cfg.simulate else
                     self.cfg.keithley.resource)
        except Exception as exc:                # noqa: BLE001
            self.amp = None
            log.warning("Keithley 428 not available: %s -- the Keithley "
                        "controls will refuse until it is", exc)

    # ------------------------------------------------------------------
    # DAQ tab
    # ------------------------------------------------------------------

    def start_writing(self, wait: bool = False):
        """Button 'Start Writing': StartHighResWritingTask,
        Controls_STMBJ.ipf:127. Creates the output task with the piezo at
        G_PiezoOffset_nm and the bias at G_TipBias."""
        return self._run("Start Writing", self._start_writing_impl, wait=wait)

    def _make_rig(self) -> Rig:
        if self.cfg.simulate:
            from stmlab.actuator import SimulatedActuator
            from stmlab.sim import SimulatedDaqSession
            session = SimulatedDaqSession(self.cfg)
            actuator = None
            if self.cfg.actuator.kind != "none":
                actuator = SimulatedActuator(self.cfg, rig_sim=session)
            return Rig(self.cfg, session=session, actuator=actuator).open()
        verify_devices(self.cfg)
        park_all_outputs(self.cfg)
        return Rig(self.cfg).open()

    def _start_writing_impl(self) -> None:
        if self.rig is not None:
            log.info("output task already running")
            return
        for warning in validate(self.cfg):
            log.warning("config: %s", warning)
        self.rig = self._make_rig()
        # Igor: HighResWriteWave = {PiezoOffset_nm/K_ZPiezoScale, -TipBias/1000}
        piezo_v = self.cfg.cal.nm_to_piezo_volts(self.opts.piezo_offset_nm)
        self.rig.hold(piezo_v=piezo_v, bias_v=self.cfg.ramp.bias_v)
        self._sync_piezo()
        self._emit("writing", True)
        log.info("output task ON: piezo %.3f V (%.0f nm), bias %+.1f mV",
                 self.rig.piezo_v, self.rig.piezo_nm,
                 1e3 * self.cfg.ramp.bias_v)
        if self.opts.calibrate_on_start_writing and not self.calibrated:
            results = calibrate.session_calibration(self.rig)
            self.calibrated = True
            log.info("session calibration: %s",
                     ", ".join(f"{k}={v:.4g}" for k, v in results.items()))
            self.rig.hold(bias_v=self.cfg.ramp.bias_v)

    def kill_tasks(self, wait: bool = False):
        """Button 'Kill Tasks': StopWritingTasks, Controls_STMBJ.ipf:172.
        Zero-check on, piezo to zero, task cleared, second card reset."""
        self.stop.set()
        return self._run("Kill Tasks", self._kill_tasks_impl, wait=wait)

    def _kill_tasks_impl(self) -> None:
        self.opts.bkgd_sampling = False
        if self.amp is not None:
            try:
                self.amp.zero_check(True)       # "Turn zero check on?"
                self.opts.zero_check = True
            except Exception as exc:            # noqa: BLE001
                log.warning("zero check on failed: %s", exc)
        self._close_writer()
        if self.rig is not None:
            try:
                self.rig.close()                # withdraw + park + close
            finally:
                self.rig = None
        for name in ("gate", "xp"):
            obj = getattr(self, name)
            if obj is not None:
                try:
                    obj.off() if name == "gate" else obj.stop()
                except Exception:               # noqa: BLE001
                    pass
                setattr(self, name, None)
        self.opts.piezo_readout_v = 0.0
        self._emit("piezo", {"volts": 0.0, "nm": 0.0})
        self._emit("writing", False)
        self._emit("gate", None)
        log.info("output task OFF; outputs parked")

    def reset_daq(self, wait: bool = False):
        """Button 'Reset DAQ Devices': EChemResetDAQDevices,
        Controls_STMBJ.ipf:221. MXResetDevice on both cards."""
        return self._run("Reset DAQ Devices", self._reset_daq_impl, wait=wait)

    def _reset_daq_impl(self) -> None:
        if self.rig is not None:
            raise NotReady("Kill Tasks before resetting the DAQ devices")
        if not self.cfg.simulate:
            import nidaqmx
            for dev in (self.cfg.channels.device,
                        self.cfg.channels.low_res_device):
                if dev:
                    nidaqmx.system.Device(dev).reset_device()
                    log.info("reset %s", dev)
            park_all_outputs(self.cfg)
        else:
            log.info("simulate: reset DAQ devices")
        if self.gate is not None:
            try:
                self.gate.off()                 # Igor: CounterElectrodeBias = 0
            except Exception:                   # noqa: BLE001
                pass
        self.cfg.echem.gate_mv = 0.0
        self.gate = None
        self._emit("gate", None)

    def set_background_sampling(self, on: bool) -> None:
        """Checkbox 'Background Sampling': BkgdSamplingCheckProc."""
        if on and self.rig is None:
            self.opts.bkgd_sampling = False
            self._emit("error", "Background sampling needs the output task; "
                                "press Start Writing first")
            self._emit("bkgd", False)
            return
        self.opts.bkgd_sampling = bool(on)
        self._emit("bkgd", bool(on))

    def _background_read(self) -> None:
        """BackgroundRead, Functions_STMBJ.ipf:657: read a short record, show
        junction voltage (mV), current (uA), piezo, and beep above 0.15 uA."""
        rig = self.rig
        if rig is None:
            return
        n = max(25, int(self.opts.fast_read_wave_size))
        record = rig.hold(n_samples=n)
        M, C = self.cfg.channels, self.cfg.cal
        v = record[M.ROW_VOLTAGE]
        i = record[M.ROW_CURRENT]
        junction_mv = float(C.voltage_input_sign * np.mean(v) * 1e3)
        current_ua = float(C.volts_to_amps(np.mean(i)) * 1e6)
        self.opts.junction_voltage_mv = junction_mv
        self.opts.current_readout_ua = current_ua
        self.opts.piezo_readout_v = rig.piezo_v
        self._emit("readout", {
            "current_ua": current_ua, "junction_mv": junction_mv,
            "piezo_v": rig.piezo_v,
            "beep": abs(current_ua) > self.opts.beep_current_ua})
        self._emit("highres", {
            "voltage_mv": C.voltage_input_sign * v * 1e3,
            "current_ua": C.volts_to_amps(i) * 1e6,
            "piezo_nm": np.full(n, rig.piezo_nm)})

    # ------------------------------------------------------------------
    # Piezo controls
    # ------------------------------------------------------------------

    def piezo_step(self, delta_nm: float, wait: bool = False):
        """Buttons 'Step closer'/'Step apart' (piezo): PiezoStepCloser /
        PiezoStepApart, Controls_STMBJ.ipf:394-413. Closer is +nm."""
        return self._run("Piezo step", self._piezo_step_impl, delta_nm,
                         wait=wait)

    def _piezo_step_impl(self, delta_nm: float) -> None:
        rig = self._require_rig()
        rig.piezo_step_nm(delta_nm)
        self._sync_piezo()

    def piezo_goto(self, volts: float, wait: bool = False):
        """Slider: SetPiezoBiasFromSlider, Controls_STMBJ.ipf:380. The slider
        value is the DAQ voltage on the piezo, not a distance."""
        return self._run("Piezo slider", self._piezo_goto_impl, volts,
                         wait=wait)

    def _piezo_goto_impl(self, volts: float) -> None:
        rig = self._require_rig()
        rig.piezo_goto(volts)
        self._sync_piezo()

    # ------------------------------------------------------------------
    # Tip bias and Keithley controls
    # ------------------------------------------------------------------

    def set_tip_bias(self, mv: float, wait: bool = False):
        """SetVariable 'Tip Bias (mV)': SetTipBiasVoltage,
        Controls_STMBJ.ipf:416. With the Keithley bias source on, Igor
        quantised to 5 mV and sent it over GPIB too."""
        return self._run("Tip bias", self._set_tip_bias_impl, mv, wait=wait)

    def _set_tip_bias_impl(self, mv: float) -> None:
        if self.cfg.keithley.enabled and self.amp is not None:
            mv = 5.0 * np.floor(mv / 5.0)
            self.amp.set_bias_mv(mv)
        volts = mv / 1000.0
        if abs(volts) > self.cfg.limits.bias_max_v:
            raise SafetyViolation(
                f"tip bias {mv:+.1f} mV exceeds the limit of "
                f"+/-{1e3 * self.cfg.limits.bias_max_v:.0f} mV "
                f"(limits.bias_max_v); raise it deliberately in the config "
                f"if the experiment needs it")
        self.cfg.ramp.bias_v = volts
        if self.rig is not None:
            self.rig.set_bias(volts)
        self._emit("bias", mv)
        log.info("tip bias %+.1f mV", mv)

    def set_gain(self, exponent: int, wait: bool = False):
        """SetVariable 'Gain ( log(V/A) )': SetGain, Controls_STMBJ.ipf:290.
        Programs the 428 AND the conversion every conductance divides by."""
        return self._run("Set gain", self._set_gain_impl, int(exponent),
                         wait=wait)

    def _set_gain_impl(self, exponent: int) -> None:
        self.cfg.keithley.gain_exponent = exponent
        self.cfg.cal.preamp_gain_v_per_a = 10.0 ** exponent
        if self.amp is not None:
            self.amp.set_gain(exponent)
        log.info("Gain Set To %d (%.0e V/A)", exponent, 10.0 ** exponent)
        self._emit("gain", exponent)

    def set_suppress_const(self, value: float, wait: bool = False):
        """SetVariable 'Suppress I value': SetCurrentSuppress,
        Controls_STMBJ.ipf:460. Suppress (uA) = const * 10^(3 - gain)."""
        return self._run("Suppress value", self._set_suppress_impl, value,
                         wait=wait)

    def _set_suppress_impl(self, value: float) -> None:
        self.cfg.keithley.suppress_const = float(value)
        ua = value * 10.0 ** (3 - self.cfg.keithley.gain_exponent)
        self._require_amp().set_suppress_ua(ua)
        log.info("current suppress %.4g uA (const %.3f)", ua, value)

    def zero_check(self, on: bool, wait: bool = False):
        """Checkbox 'Zero Check': ZeroCheckProc, C1X / C0X."""
        self.opts.zero_check = bool(on)
        return self._run("Zero check", lambda: self._require_amp().zero_check(on),
                         wait=wait)

    def zero_correct(self, wait: bool = False):
        """Button 'Zero Correct': ZeroCorrectProc, C2X."""
        return self._run("Zero correct",
                         lambda: self._require_amp().zero_correct(), wait=wait)

    def suppress_enable(self, on: bool, wait: bool = False):
        """Checkbox 'Suppress I': CurrentSuppressCheckProc, N1X / N0X."""
        self.opts.suppress_on = bool(on)
        return self._run("Suppress on/off",
                         lambda: self._require_amp().suppress_enable(on),
                         wait=wait)

    def keithley_bias(self, on: bool, wait: bool = False):
        """Checkbox 'Bias': KeithleyBias, SetUpGPIB_Keithley.ipf:67. B1X/B0X."""
        self.cfg.keithley.enabled = bool(on)
        return self._run("Keithley bias",
                         lambda: self._require_amp().bias_enable(on), wait=wait)

    def find_suppress(self, wait: bool = False):
        """Button 'Find Suppress': FindSuppress, Controls_STMBJ.ipf:479.
        Zero the tip bias, TestVirtualGround, restore the bias."""
        return self._run("Find Suppress", self._find_suppress_impl, wait=wait)

    def _find_suppress_impl(self) -> None:
        rig = self._require_rig()
        amp = self._require_amp()
        bias = self.cfg.ramp.bias_v
        rig.set_bias(0.0)                       # WriteToHighRes(0, 0)
        try:
            new_ua, sweep, readings = keithley.find_suppress(rig, amp)
        finally:
            rig.set_bias(bias)                  # WriteToHighRes(0, TipBias)
        self.cfg.keithley.suppress_const = \
            new_ua / 10.0 ** (3 - self.cfg.keithley.gain_exponent)
        self.last_suppress = (new_ua, sweep, readings)
        self._emit("suppress", self.last_suppress)
        log.info("New current suppress is %.4g uA", new_ua)

    # ------------------------------------------------------------------
    # Voltage_Offset panel
    # ------------------------------------------------------------------

    def find_offset(self, wait: bool = False):
        """Button 'Find Offset' (Find Zero): FindOffset, Controls_STMBJ.ipf:498
        -> OffsetVoltage. Fills G_Vzero / G_Izero and opens the Izero graph."""
        return self._run("Find Offset", self._find_offset_impl, wait=wait)

    def _find_offset_impl(self) -> vzero.VzeroResult:
        rig = self._require_rig()
        result = vzero.measure_offset(rig)
        self._record_vzero(result)
        self._sync_piezo()
        return result

    def _record_vzero(self, result: vzero.VzeroResult) -> None:
        self.opts.vzero_mv = result.vzero_mv
        self.opts.izero_ua = result.izero_a * 1e6
        if not self.vzero_tracker.history or \
                self.vzero_tracker.history[-1] is not result:
            self.vzero_tracker.history.append(result)
        self.izero_history.append((self.opts.pull_out_number,
                                   result.izero_a * 1e6))
        self._emit("vzero", (result.vzero_mv, result.izero_a * 1e6))
        self._emit("izero", result)
        self._emit("izero_time", (np.array([n for n, _ in self.izero_history]),
                                  np.array([i for _, i in self.izero_history])))

    # ------------------------------------------------------------------
    # Actuator controls
    # ------------------------------------------------------------------

    def step_actuator(self, closer: bool, wait: bool = False):
        """Buttons 'Step closer'/'Step apart' (actuator): StepActuatorCloser /
        StepActuatorApart, NanoPZ_Actuator_Functions_STM.ipf:6-23."""
        return self._run("Actuator step", self._step_actuator_impl, closer,
                         wait=wait)

    def _step_actuator_impl(self, closer: bool) -> None:
        if self.rig is not None:
            self.rig.coarse_step(closer=closer)     # behind the interlock
        else:
            from stmlab.actuator import make_actuator
            act = make_actuator(self.cfg)
            try:
                act.step(closer=closer)
            finally:
                act.close()
        log.info("actuator step %s (%d)", "closer" if closer else "apart",
                 self.cfg.actuator.step_size)

    def approach(self, wait: bool = False):
        """Button 'Start Approach': ApproachButton -> HighResCardApproach,
        Functions_STMBJ.ipf:1723. Step the actuator in (step size forced to 5)
        until |I| exceeds actuator.stop_current_ua; Alt (Stop) aborts."""
        return self._run("Start Approach", self._approach_impl, wait=wait)

    def _approach_impl(self) -> int:
        rig = self._require_rig()
        if self.cfg.actuator.kind == "none":
            raise ApproachError("no coarse actuator configured "
                                "(actuator.kind == 'none'); approach by hand")
        self.stop.clear()
        self.cfg.actuator.step_size = 5              # Igor: ActuatorStepSize=5
        self.opts.actuator_counter = 0
        self._emit("counter", 0)
        rig.state = RigState.APPROACHING
        n = max(25, int(self.opts.fast_read_wave_size))
        stop_ua = self.cfg.actuator.stop_current_ua
        while not self.stop.is_set():
            record = rig.hold(n_samples=n)
            M, C = self.cfg.channels, self.cfg.cal
            current_ua = float(C.volts_to_amps(
                np.mean(record[M.ROW_CURRENT])) * 1e6)
            voltage_v = float(np.mean(record[M.ROW_VOLTAGE]))
            self.opts.current_readout_ua = current_ua
            self._emit("readout", {"current_ua": current_ua,
                                   "junction_mv": C.voltage_input_sign
                                   * voltage_v * 1e3,
                                   "piezo_v": rig.piezo_v, "beep": False})
            log.info("Approach: actual current= %.4f uA, Voltage= %.4f V",
                     current_ua, voltage_v)
            if abs(current_ua) < stop_ua:
                rig.coarse_step(closer=True)
                self.opts.actuator_counter += 1
                self._emit("counter", self.opts.actuator_counter)
                time.sleep(self.cfg.actuator.settle_s
                           if not self.cfg.simulate else 0.0)
            else:
                break
        rig.state = RigState.RETRACTED
        self._sync_piezo()
        return self.opts.actuator_counter

    # ------------------------------------------------------------------
    # Start Measurement / +1
    # ------------------------------------------------------------------

    def start_measurement(self, single: bool = False, wait: bool = False):
        """Buttons 'Start Measurement' / '+1': StartMeasurement / MakeAttempt
        -> MeasureBreakJunctions, Functions_STMBJ.ipf:1664."""
        return self._run("+1" if single else "Start Measurement",
                         self._measure_impl, single, wait=wait)

    def _configure_mode(self, mode: str) -> None:
        """What each experiments/<NN> runner does before its loop: set the
        headroom check to the mode's net descent, and raise the bias limit
        (loudly) for the modes whose sweep or hold exceeds it."""
        cfg = self.cfg
        if mode == "push_pull":
            pp = cfg.push_pull
            cfg.ramp.pull_length_nm = pp.initial_pull_nm + pp.final_pull_nm
        elif mode == "iv":
            iv = cfg.iv
            cfg.ramp.pull_length_nm = iv.init_pull_nm + iv.final_pull_nm
            self._raise_bias_limit(1.1 * iv.max_bias_v, "iv.max_bias_v")
        elif mode == "ac_hold":
            ac = cfg.ac_hold
            cfg.ramp.pull_length_nm = ac.init_pull_nm + ac.final_pull_nm
            self._raise_bias_limit(1.1 * ac.amp_v, "ac_hold.amp_v")
        elif mode == "hb_hold":
            hb = cfg.hb_hold
            cfg.ramp.pull_length_nm = hb.init_pull_nm + hb.final_pull_nm
            self._raise_bias_limit(1.1 * abs(hb.hold_bias_v),
                                   "hb_hold.hold_bias_v")

    def _raise_bias_limit(self, needed: float, why: str) -> None:
        if self.cfg.limits.bias_max_v < needed:
            log.warning("RAISING limits.bias_max_v from %.3f V to %.3f V "
                        "(1.1 x %s) for this session",
                        self.cfg.limits.bias_max_v, needed, why)
            self.cfg.limits.bias_max_v = needed

    def _build_ramp(self, mode: str, rig: Rig, bias_offset_v: float):
        cfg = self.cfg
        fs = rig.sample_rate_hz
        if mode == "constant":
            return trace.build_ramp(cfg, rig.piezo_v, fs,
                                    bias_offset_v=bias_offset_v)
        if mode == "push_pull":
            return ramps.build_push_pull(cfg, rig.piezo_v, sample_rate_hz=fs)
        if mode == "iv":
            return ramps.build_iv(cfg, rig.piezo_v, sample_rate_hz=fs)
        if mode == "ac_hold":
            return ramps.build_ac_hold(cfg, rig.piezo_v, sample_rate_hz=fs)
        if mode == "hb_hold":
            vz = self.opts.vzero_mv if self.opts.vzero_check else None
            return ramps.build_hb_hold(cfg, rig.piezo_v, sample_rate_hz=fs,
                                       vzero_mv=vz)
        raise ValueError(mode)

    def _open_writer(self, mode: str) -> storage.SessionWriter:
        path = self.data_dir() / \
            f"{mode}_{time.strftime('%H%M%S')}_from{self.opts.pull_out_number}.h5"
        writer = storage.SessionWriter(path, self.cfg).open()
        self.session_files.append(path)
        log.info("writing traces to %s", path)
        return writer

    def _close_writer(self) -> None:
        writer = getattr(self, "_writer", None)
        if writer is not None:
            try:
                writer.write_summary({
                    "saved_upto": self.opts.pull_out_number,
                    "attempts_total": self.opts.pull_out_attempt,
                    "rejections": self.rejections,
                    "vzero_history": {k: v.tolist() for k, v in
                                      self.vzero_tracker.as_arrays().items()}})
                writer.close()
            except Exception:                   # noqa: BLE001
                log.exception("closing the session file failed")
            self._writer = None

    def _measure_impl(self, single: bool) -> dict:
        rig = self._require_rig()
        opts, cfg = self.opts, self.cfg
        if not single and opts.pull_out_number >= opts.stop_number:
            log.info("Saved (%d) >= Stop # (%d): nothing to do",
                     opts.pull_out_number, opts.stop_number)
            return {"accepted": 0, "attempts": 0}

        self.stop.clear()
        mode = opts.mode()
        self._configure_mode(mode)
        for warning in validate(cfg):
            log.warning("config: %s", warning)

        # CreateInputs: the applied bias carries Vzero when the box is ticked
        use_vzero = opts.vzero_check and mode == "constant"

        writer = self._open_writer(mode)
        self._writer = writer
        header_written = False
        accepted = attempts = 0
        segments: dict | None = None
        try:
            rig.set_bias(cfg.ramp.bias_v)
            while True:
                if self.stop.is_set():
                    log.info("stopping: Stop pressed")
                    break
                if not single and opts.pull_out_number >= opts.stop_number:
                    break
                if opts.pull_out_attempt >= cfg.ramp.max_attempts:
                    log.error("Catastrophic failure: %d attempts",
                              opts.pull_out_attempt)
                    break

                # SingleBreakJunctionAttempt
                opts.pull_out_attempt += 1
                attempts += 1
                rig.attempts = opts.pull_out_attempt
                self._emit("attempts", opts.pull_out_attempt)

                if cfg.ramp.smash_every and \
                        opts.pull_out_attempt % cfg.ramp.smash_every == 0:
                    approach.smash(rig)                 # SmashFun

                try:
                    if approach.recover_headroom(rig) is not RigState.ENGAGED:
                        self._reject("engage")
                        continue
                except ApproachError as exc:
                    # Igor: HighResMakeContact returned -2/-3, run terminated
                    log.error("cannot make contact: %s", exc)
                    self._emit("error", f"Start Measurement: {exc}")
                    break

                bias_offset = self.vzero_tracker.offset_v if use_vzero else 0.0
                ramp = self._build_ramp(mode, rig, bias_offset)
                record = trace.capture(rig, ramp, index=opts.pull_out_number,
                                       bias_v=cfg.ramp.bias_v + bias_offset)
                self._sync_piezo()
                if record is None:
                    self._reject("alignment")
                    continue

                g0 = record.conductance_g0(cfg)
                M = cfg.channels
                piezo_cmd = ramp.waveform[M.ROW_PIEZO,
                                          ramp.pre_pad:ramp.pre_pad + ramp.n_pull]
                piezo_nm = cfg.cal.piezo_volts_to_nm(piezo_cmd)
                disp_nm = cfg.cal.piezo_volts_to_nm(ramp.start_piezo_v
                                                    - piezo_cmd)
                bias_mv = cfg.cal.voltage_input_sign * record.voltage_v * 1e3

                if mode == "constant":
                    verdict = analysis.select_trace(g0, cfg.ramp)
                    ok = verdict.accepted
                else:
                    verdict = None
                    ok = True                   # Igor tested constant pulls only
                    segments = ramp.segments

                self.last_trace = {"g0": g0, "disp_nm": disp_nm,
                                   "bias_mv": bias_mv, "piezo_nm": piezo_nm,
                                   "accepted": ok, "mode": mode,
                                   "number": opts.pull_out_number}
                self._emit("trace", self.last_trace)

                if not ok:
                    self._reject(verdict.reason.split(":")[0].split("(")[0]
                                 .strip())
                    if single:
                        break
                    continue

                # SaveOffset: re-measure Vzero every N saved traces
                if use_vzero:
                    res = self.vzero_tracker.maybe_measure(
                        rig, opts.pull_out_number)
                    if res is not None:
                        self._record_vzero(res)

                # SavePullOut
                writer.append(opts.pull_out_number, record, verdict)
                if not header_written:
                    h5 = writer._h5
                    h5.attrs["mode"] = mode
                    h5.attrs["igor_globals_json"] = json.dumps(
                        self.igor_globals(), default=str)
                    if segments:
                        h5.attrs["segments_json"] = json.dumps(segments)
                    header_written = True
                opts.pull_out_number += 1
                accepted += 1
                self._emit("saved", opts.pull_out_number)

                self.block.append(self._histogram_input(g0, segments))
                if len(self.block) >= HIST_BLOCK:
                    self._histogram_block()

                if single:
                    break
        finally:
            if self.block and (single or accepted):
                # Igor only histogrammed complete 100-trace blocks; showing
                # the partial block at the end of a run is a GUI addition.
                self._histogram_block(partial=True)
            self._close_writer()
            self._sync_piezo()

        stats = {"accepted": accepted, "attempts": attempts,
                 "saved": opts.pull_out_number, "mode": mode}
        log.info("%s: %d saved / %d attempts this run (Saved now %d)",
                 mode, accepted, attempts, opts.pull_out_number)
        return stats

    def _reject(self, reason: str) -> None:
        self.rejections[reason] = self.rejections.get(reason, 0) + 1

    @staticmethod
    def _histogram_input(g0: np.ndarray, segments: dict | None) -> np.ndarray:
        """LogHistFromBlocks deleted the hold / push-pull section of a mode
        trace before histogramming (Functions_STMBJ.ipf:817-830)."""
        if not segments:
            return g0
        first = segments.get("initial_pull") or segments.get("init_pull")
        final = segments.get("final_pull")
        if first is None or final is None:
            return g0
        return np.concatenate([g0[:first[1]], g0[final[0]:]])

    def _histogram_block(self, partial: bool = False) -> None:
        centres, counts = analysis.log_histogram(
            self.block, zero_cutoff=self.cfg.ramp.break_g0)
        self.last_hist = (centres, counts)
        self._emit("hist", {"centres": centres, "counts": counts,
                            "n": len(self.block), "partial": partial})
        if self.opts.save_hist:
            path = self.data_dir() / \
                f"loghist_{time.strftime('%H%M%S')}_upto{self.opts.pull_out_number}.csv"
            np.savetxt(path, np.column_stack([centres, counts]),
                       delimiter=",", header="log10(G/G0),counts_per_trace")
            log.info("wrote %s (%d traces%s)", path.name, len(self.block),
                     ", partial block" if partial else "")
        if not partial:
            self.block = []

    # ------------------------------------------------------------------
    # EChem panel
    # ------------------------------------------------------------------

    def counter_electrode_on(self, wait: bool = False):
        """Button 'Counter Electrode ON': CounterElectrodeOn ->
        StartEChemWriting, EChem_Module.ipf:41."""
        return self._run("Counter Electrode ON", self._gate_on_impl, wait=wait)

    def _gate_on_impl(self) -> None:
        if self.gate is None:
            self.gate = echem.make_counter_electrode(self.cfg).on()
        self.gate.set_mv(self.cfg.echem.gate_mv)
        self._emit("gate", self.gate.gate_mv)
        log.info("counter electrode ON at %+.1f mV", self.gate.gate_mv)

    def set_counter_electrode(self, mv: float, wait: bool = False):
        """SetVariable 'Counter Electrode Bias (mV)': CounterElectrodeSetVar
        -> WriteToCounterElectrode."""
        return self._run("Counter electrode bias", self._gate_set_impl, mv,
                         wait=wait)

    def _gate_set_impl(self, mv: float) -> None:
        if self.gate is None:
            raise NotReady("press Counter Electrode ON first")
        self.gate.set_mv(mv)
        self._emit("gate", self.gate.gate_mv)

    def start_cv(self, kind: str, wait: bool = False):
        """Buttons 'CV HighRes' / 'CV LowRes': StartCVHighResButton /
        StartCVLowResButton, EChem_Module.ipf:364/389. Zero check is lifted
        for the sweep and restored after."""
        return self._run(f"CV {kind}", self._cv_impl, kind, wait=wait)

    def _cv_impl(self, kind: str) -> list:
        if self.rig is not None and not self.cfg.simulate and kind == "highres":
            raise NotReady("CV HighRes drives the junction-bias channel; "
                           "Kill Tasks first (Igor reset the card afterwards)")
        restore = self.opts.zero_check and self.amp is not None
        if restore:
            self.amp.zero_check(False)
        try:
            cycles = echem.run_cv(self.cfg, kind=kind)
        finally:
            if restore:
                self.amp.zero_check(True)
        path = self.data_dir() / f"cv_{kind}_{time.strftime('%H%M%S')}.h5"
        storage.save_cv_cycles(path, self.cfg, cycles, kind=kind)
        self.last_cv = cycles
        self._emit("cv", cycles)
        return cycles

    # ------------------------------------------------------------------
    # X piezo (Igor: SetupXPiezo / MoveXPiezo / MoveXPiezoToZero / StopXPiezo)
    # ------------------------------------------------------------------

    def _xp(self) -> xpiezo.XPiezo:
        if self.xp is None:
            self.xp = xpiezo.make_xpiezo(self.cfg).setup()
        return self.xp

    def move_xpiezo(self, delta_nm: float, wait: bool = False):
        return self._run("Move X piezo", self._move_xp_impl, delta_nm,
                         wait=wait)

    def _move_xp_impl(self, delta_nm: float) -> float:
        pos = self._xp().move_nm(delta_nm)
        self._emit("xpiezo", pos)
        return pos

    def zero_xpiezo(self, wait: bool = False):
        return self._run("X piezo to zero", self._zero_xp_impl, wait=wait)

    def _zero_xp_impl(self) -> None:
        self._xp().zero()
        self._emit("xpiezo", 0.0)

    # ------------------------------------------------------------------
    # Macros (command-line functions in Igor)
    # ------------------------------------------------------------------

    def rungo(self, biases_mv: list[float] | None = None,
              counts_each: int = IGOR_RUNGO_TRACES_PER_BIAS,
              wait: bool = False):
        """Macro rungo(), Setup1_STMBJ.ipf:138: a bias series, resumable
        from the current Saved number."""
        return self._run("rungo", self._rungo_impl,
                         list(biases_mv or IGOR_RUNGO_BIAS_MV), counts_each,
                         wait=wait)

    def _rungo_impl(self, biases_mv: list[float], counts_each: int) -> None:
        opts = self.opts
        start_num = 1
        stop_nums = [(i + 1) * counts_each + start_num
                     for i in range(len(biases_mv))]
        start_nums = [s - counts_each for s in stop_nums]
        # FindLevel/EDGE=1 StartNumWave, SavedNumber -> resume index
        starti = 0
        for i, s in enumerate(start_nums):
            if s <= opts.pull_out_number:
                starti = i
        self.stop.clear()
        for i in range(starti, len(biases_mv)):
            mv = biases_mv[i]
            opts.stop_number = stop_nums[i]
            self._emit("stop_number", opts.stop_number)
            log.info("rungo step %d: tip bias %+.0f mV, stop # %d",
                     i, mv, opts.stop_number)
            self._set_tip_bias_impl(mv)
            self._measure_impl(single=False)
            if self.stop.is_set():
                log.info("rungo aborted at step %d", i)
                return
        log.info("rungo complete")

    def lateral_expt(self, z_distance: int, x_distance_nm: float,
                     x_freq: int, final_stop_number: int = 12201,
                     wait: bool = False):
        """Macro LateralEXPT(ZDistance, XDistance, XFreq),
        Setup1_STMBJ.ipf:91: a trace batch per site, walking the X piezo."""
        return self._run("LateralEXPT", self._lateral_impl, int(z_distance),
                         float(x_distance_nm), int(x_freq),
                         int(final_stop_number), wait=wait)

    def _lateral_impl(self, z_distance: int, x_distance_nm: float,
                      x_freq: int, final_stop_number: int) -> None:
        rig = self._require_rig()
        opts = self.opts
        self.cfg.actuator.step_size = z_distance
        self.stop.clear()
        while opts.pull_out_number < final_stop_number:
            if self.stop.is_set():
                break
            opts.stop_number = opts.pull_out_number + x_freq
            self._emit("stop_number", opts.stop_number)
            log.info("LateralEXPT: X piezo at %.3f V", self._xp().voltage)
            self._measure_impl(single=False)
            if self.stop.is_set():
                break
            # Withdraw tip in Z: three actuator steps apart
            rig.withdraw()
            self._sync_piezo()
            for _ in range(3):
                rig.coarse_step(closer=False)
                time.sleep(0.1 if not self.cfg.simulate else 0.0)
            # Move tip in X
            self._move_xp_impl(x_distance_nm)
            # Approach tip into contact: step size 5, slider to 0, approach
            self.cfg.actuator.step_size = 5
            rig.piezo_goto(0.0)
            self._sync_piezo()
            rig.set_bias(self.cfg.ramp.bias_v)
            self._approach_impl()
            self.cfg.actuator.step_size = z_distance
        log.info("LateralEXPT done at Saved = %d", opts.pull_out_number)

    # ------------------------------------------------------------------
    # Config files
    # ------------------------------------------------------------------

    def save_config(self, path: str | Path) -> None:
        self.cfg.to_json(path)
        log.info("config written to %s", path)

    def load_config(self, path: str | Path) -> None:
        new = RigConfig.from_json(path)
        for name in ("channels", "limits", "ramp", "cal", "actuator",
                     "push_pull", "iv", "ac_hold", "hb_hold", "vzero",
                     "keithley", "echem", "xpiezo", "simulate", "notes"):
            setattr(self.cfg, name, getattr(new, name))
        log.info("config loaded from %s", path)
        self._emit("config", None)


# --------------------------------------------------------------------------
# The button map: which Python runs when you click what
# --------------------------------------------------------------------------

# public method -> (panel control, Igor procedure, _impl name or None,
#                   the stmlab functions it calls, in order)
COMMAND_MAP: dict[str, tuple[str, str, str | None, list[str]]] = {
    "connect_instruments": (
        "(at launch)", "SetUpGPIB_Keithley", "_connect_impl",
        ["stmlab.keithley.make_keithley", "stmlab.keithley.Keithley428.open"]),
    "start_writing": (
        "Start Writing", "StartHighResWritingTask", "_start_writing_impl",
        ["stmlab.config.validate", "stmlab.safety.verify_devices",
         "stmlab.safety.park_all_outputs", "stmlab.instrument.Rig.open",
         "stmlab.instrument.Rig.hold",
         "stmlab.calibrate.session_calibration"]),
    "kill_tasks": (
        "Kill Tasks", "StopWritingTasks", "_kill_tasks_impl",
        ["stmlab.keithley.Keithley428.zero_check",
         "stmlab.storage.SessionWriter.close", "stmlab.instrument.Rig.close",
         "stmlab.echem.CounterElectrode.off", "stmlab.xpiezo.XPiezo.stop"]),
    "reset_daq": (
        "Reset DAQ Devices", "EChemResetDAQDevices", "_reset_daq_impl",
        ["stmlab.safety.park_all_outputs",
         "stmlab.echem.CounterElectrode.off"]),
    "set_background_sampling": (
        "Background Sampling (Beep is ON)", "BkgdSamplingCheckProc",
        "_background_read", ["stmlab.instrument.Rig.hold"]),
    "piezo_step": (
        "Step closer / Step apart (Piezo Controls)",
        "PiezoStepCloser / PiezoStepApart", "_piezo_step_impl",
        ["stmlab.instrument.Rig.piezo_step_nm"]),
    "piezo_goto": (
        "SliderPos_Z", "SetPiezoBiasFromSlider", "_piezo_goto_impl",
        ["stmlab.instrument.Rig.piezo_goto"]),
    "set_tip_bias": (
        "Tip Bias (mV)", "SetTipBiasVoltage", "_set_tip_bias_impl",
        ["stmlab.keithley.Keithley428.set_bias_mv",
         "stmlab.instrument.Rig.set_bias"]),
    "set_gain": (
        "Gain ( log(V/A) )", "SetGain", "_set_gain_impl",
        ["stmlab.keithley.Keithley428.set_gain"]),
    "set_suppress_const": (
        "Suppress I value", "SetCurrentSuppress", "_set_suppress_impl",
        ["stmlab.keithley.Keithley428.set_suppress_ua"]),
    "zero_check": (
        "Zero Check", "ZeroCheckProc", None,
        ["stmlab.keithley.Keithley428.zero_check"]),
    "zero_correct": (
        "Zero Correct", "ZeroCorrectProc", None,
        ["stmlab.keithley.Keithley428.zero_correct"]),
    "suppress_enable": (
        "Suppress I", "CurrentSuppressCheckProc", None,
        ["stmlab.keithley.Keithley428.suppress_enable"]),
    "keithley_bias": (
        "Bias", "KeithleyBias", None,
        ["stmlab.keithley.Keithley428.bias_enable"]),
    "find_suppress": (
        "Find Suppress", "FindSuppress -> TestVirtualGround",
        "_find_suppress_impl",
        ["stmlab.instrument.Rig.set_bias", "stmlab.keithley.find_suppress"]),
    "find_offset": (
        "Find Offset (Find Zero)", "FindOffset -> OffsetVoltage",
        "_find_offset_impl", ["stmlab.vzero.measure_offset"]),
    "step_actuator": (
        "Step closer / Step apart (Actuator Controls)",
        "StepActuatorCloser / StepActuatorApart", "_step_actuator_impl",
        ["stmlab.instrument.Rig.coarse_step", "stmlab.actuator.make_actuator"]),
    "approach": (
        "Start Approach", "ApproachButton -> HighResCardApproach",
        "_approach_impl",
        ["stmlab.instrument.Rig.hold", "stmlab.instrument.Rig.coarse_step"]),
    "start_measurement": (
        "Start Measurement / +1",
        "StartMeasurement / MakeAttempt -> MeasureBreakJunctions",
        "_measure_impl",
        ["stmlab.config.validate", "stmlab.storage.SessionWriter.open",
         "stmlab.approach.smash", "stmlab.approach.recover_headroom",
         "stmlab.trace.build_ramp", "stmlab.ramps.build_push_pull",
         "stmlab.ramps.build_iv", "stmlab.ramps.build_ac_hold",
         "stmlab.ramps.build_hb_hold", "stmlab.trace.capture",
         "stmlab.analysis.select_trace",
         "stmlab.vzero.VzeroTracker.maybe_measure",
         "stmlab.storage.SessionWriter.append",
         "stmlab.analysis.log_histogram"]),
    "request_stop": (
        "Stop (Alt) / Alt / Escape", "GetKeyState (Alt)", None, []),
    "counter_electrode_on": (
        "Counter Electrode ON", "CounterElectrodeOn -> StartEChemWriting",
        "_gate_on_impl",
        ["stmlab.echem.make_counter_electrode",
         "stmlab.echem.CounterElectrode.on",
         "stmlab.echem.CounterElectrode.set_mv"]),
    "set_counter_electrode": (
        "Counter Electrode Bias (mV)",
        "CounterElectrodeSetVar -> WriteToCounterElectrode", "_gate_set_impl",
        ["stmlab.echem.CounterElectrode.set_mv"]),
    "start_cv": (
        "CV HighRes / CV LowRes",
        "StartCVHighResButton / StartCVLowResButton -> CVcurveHighRes / "
        "CVcurveLowRes", "_cv_impl",
        ["stmlab.keithley.Keithley428.zero_check", "stmlab.echem.run_cv",
         "stmlab.storage.save_cv_cycles"]),
    "move_xpiezo": (
        "Macros > MoveXPiezo(nm)", "MoveXPiezo", "_move_xp_impl",
        ["stmlab.xpiezo.make_xpiezo", "stmlab.xpiezo.XPiezo.move_nm"]),
    "zero_xpiezo": (
        "Macros > MoveXPiezoToZero()", "MoveXPiezoToZero", "_zero_xp_impl",
        ["stmlab.xpiezo.XPiezo.zero"]),
    "rungo": (
        "Macros > rungo()", "rungo", "_rungo_impl",
        ["stmgui.controller.RigController._set_tip_bias_impl",
         "stmgui.controller.RigController._measure_impl"]),
    "lateral_expt": (
        "Macros > LateralEXPT(Z, X, XFreq)", "LateralEXPT", "_lateral_impl",
        ["stmgui.controller.RigController._measure_impl",
         "stmlab.instrument.Rig.withdraw", "stmlab.instrument.Rig.coarse_step",
         "stmlab.xpiezo.XPiezo.move_nm",
         "stmgui.controller.RigController._approach_impl"]),
    "save_config": (
        "File > Save config JSON", "(none)", None,
        ["stmlab.config.RigConfig.to_json"]),
    "load_config": (
        "File > Load config JSON", "(none)", None,
        ["stmlab.config.RigConfig.from_json"]),
    "shutdown": (
        "File > Quit", "(none)", "_kill_tasks_impl",
        ["stmlab.keithley.Keithley428.close"]),
}


def _resolve(dotted: str):
    """'stmlab.keithley.Keithley428.zero_check' -> the object, or None."""
    import importlib
    parts = dotted.split(".")
    for k in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:k]))
        except ImportError:
            continue
        try:
            for attr in parts[k:]:
                obj = getattr(obj, attr)
            return obj
        except AttributeError:
            return None
    return None


def locate(obj) -> str:
    """'stmlab/keithley.py:199' for a function, method or class."""
    import inspect
    fn = getattr(obj, "__func__", obj)
    try:
        path = Path(inspect.getsourcefile(fn)).resolve()
        line = inspect.getsourcelines(fn)[1]
    except (TypeError, OSError):
        return "?"
    try:
        path = path.relative_to(PKG_ROOT)
    except ValueError:
        pass
    #return f"{path}:{line}"
    return f"{path.as_posix()}:{line}"

def where(dotted: str) -> str:
    """'stmlab/keithley.py:199 find_suppress' for a dotted name."""
    obj = _resolve(dotted)
    short = ".".join(dotted.split(".")[2:]) or dotted
    return f"{locate(obj)} {short}" if obj is not None else f"? {short}"


def describe_command(method) -> str:
    """The tooltip text for a controller method: what it does, which Igor
    procedure it mirrors, the Python file:line of the method and its
    worker-thread _impl, and the stmlab functions it calls."""
    fn = getattr(method, "__func__", method)
    name = fn.__name__
    doc = fn.__doc__ or ""
    paragraphs = [" ".join(p.split()) for p in doc.strip().split("\n\n")]
    lines = [p for p in paragraphs if p]
    control, igor, impl, calls = COMMAND_MAP.get(
        name, (name, "?", None, []))
    lines.append("")
    lines.append(f"Python: {locate(fn)}  RigController.{name}")
    impl_fn = getattr(RigController, impl, None) if impl else None
    if impl_fn is not None:
        lines.append(f"        {locate(impl_fn)}  RigController.{impl}  "
                     f"(runs on the worker thread)")
    lines.append(f"Igor:   {igor}")
    if calls:
        lines.append("Calls:  " + "; ".join(where(c) for c in calls))
    return "\n".join(lines)


def command_table() -> list[dict[str, str]]:
    """One row per command, for the Button map window and the manual."""
    rows = []
    for name, (control, igor, impl, calls) in COMMAND_MAP.items():
        fn = getattr(RigController, name)
        impl_fn = getattr(RigController, impl, None) if impl else None
        rows.append({
            "control": control,
            "method": f"RigController.{name}",
            "where": locate(fn),
            "impl": f"{locate(impl_fn)} RigController.{impl}" if impl_fn
            else "",
            "igor": igor,
            "calls": [where(c) for c in calls],
        })
    return rows


__all__ = ["RigController", "NotReady", "IGOR_RUNGO_BIAS_MV",
           "IGOR_RUNGO_TRACES_PER_BIAS", "HIST_BLOCK", "G0_SIEMENS",
           "COMMAND_MAP", "describe_command", "command_table", "locate",
           "where"]
