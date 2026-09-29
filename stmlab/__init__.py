"""stmlab -- the complete Igor STM-BJ setup, translated.

Everything the Igor procedures in ``../../igor_code/`` could run:

    constant-bias break junction   trace.build_ramp + trace.trace_loop
    push-pull                      ramps.build_push_pull
    IV sweep at a held junction    ramps.build_iv
    AC hold                        ramps.build_ac_hold
    high-bias hold                 ramps.build_hb_hold
    Vzero offset workflow          vzero.measure_offset / VzeroTracker
    Keithley 428 over GPIB         keithley.Keithley428
    counter-electrode gate + CV    echem.CounterElectrode / run_cv
    lateral X piezo                xpiezo.XPiezo
    NanoPZ coarse actuator         actuator.NanoPZActuator

Layering, dependencies pointing downward only::

    experiments/ (one folder per experiment)
    trace  approach  ramps  vzero  echem  xpiezo  keithley
    instrument
    daq  sim  calibrate
    config  safety  storage  actuator
    analysis                 no hardware; runs anywhere

The constant-bias core is byte-for-byte the validated ``stmbj`` package;
everything else was translated for this folder. One Rig, one ``play()``
verb, raw volts in every file.
"""

from .config import (G0_SIEMENS, ACHoldConfig, Calibration, ChannelMap,
                     ConfigError, EChemConfig, HBHoldConfig, IVConfig,
                     KeithleyConfig, PushPullConfig, RampConfig, RigConfig,
                     SafetyLimits, VzeroConfig, XPiezoConfig, validate)
from .safety import RigState, SafetyViolation

__all__ = [
    "G0_SIEMENS",
    "ACHoldConfig",
    "Calibration",
    "ChannelMap",
    "ConfigError",
    "EChemConfig",
    "HBHoldConfig",
    "IVConfig",
    "KeithleyConfig",
    "PushPullConfig",
    "RampConfig",
    "RigConfig",
    "RigState",
    "SafetyLimits",
    "SafetyViolation",
    "VzeroConfig",
    "XPiezoConfig",
    "validate",
]

__version__ = "0.1.0"
