"""SNIPPET 16 -- The real hardware. RUN THIS ON THE LAB PC.  [bring-up]

Snippets 01-15 run on any laptop. This one needs nidaqmx and the PXI-4461,
and it exercises the ONLY part of the package that has never executed
against hardware.

    PIEZO DISCONNECTED. TIP CLEAR OF THE SAMPLE.

Both outputs go nowhere but a BNC cable. Nothing here can damage anything,
which is the point of running it before anything is plugged in.
"""

# _common first, before numpy: it checks the interpreter has the
# dependencies and prints which one to use instead. Imported after
# numpy, a bare ModuleNotFoundError wins and says nothing useful.
from _common import rule

import logging
import sys

import numpy as np

from stmlab.config import RigConfig

logging.basicConfig(level=logging.INFO, format="    %(levelname)-7s %(message)s")

try:
    import nidaqmx                                       # noqa: F401
except ImportError:
    print(__doc__)
    print("\nnidaqmx is not installed here -- this snippet only runs on the "
          "lab PC.\nOn a laptop, run snippets 01-15 instead.")
    sys.exit(0)

cfg = RigConfig()

rule("A. Is the card there, and is it the card we think?")
import nidaqmx.system                                    # noqa: E402
system = nidaqmx.system.System.local()
v = system.driver_version
print(f"  NI-DAQmx {v.major_version}.{v.minor_version}.{v.update_version}")
for d in system.devices:
    print(f"    {d.name:<10} {d.product_type}")
names = [d.name for d in system.devices]
if cfg.channels.device not in names:
    print(f"\n  {cfg.channels.device!r} is not present. Fix the device name in")
    print("  the config, or the alias in NI MAX, before going further.")
    sys.exit(1)

rule("A2. Is there a second card? (experiments 06 and 07 need one)")
low = cfg.channels.low_res_device
if low is None:
    print("  channels.low_res_device is None.")
    print("  -> experiment 06 (gate, lowres CV) and 07 (lateral map) cannot")
    print("     run on hardware. 'cv --kind highres' still can: it drives")
    print("     dev1/ao1, with the tip as the working electrode.")
elif low in names:
    print(f"  {low} present -- experiments 06 and 07 can run.")
else:
    print(f"  config names {low!r} but it is NOT present: {names}")

rule("B. What sample rate does a delta-sigma card actually grant?")
from nidaqmx.constants import AcquisitionType           # noqa: E402
with nidaqmx.Task() as t:
    t.ai_channels.add_ai_voltage_chan(
        cfg.channels.path(cfg.channels.ai_voltage),
        min_val=-cfg.channels.ai_range_v, max_val=cfg.channels.ai_range_v)
    t.timing.cfg_samp_clk_timing(cfg.ramp.sample_rate_hz,
                                 sample_mode=AcquisitionType.FINITE,
                                 samps_per_chan=1000)
    granted = float(t.timing.samp_clk_rate)
print(f"  requested {cfg.ramp.sample_rate_hz:,.1f} Hz")
print(f"  granted   {granted:,.1f} Hz")
print("  Every time and displacement axis uses the GRANTED value. A 0.1%")
print("  error here is a 0.1% error in every displacement you report.")
if granted != cfg.ramp.sample_rate_hz:
    print(f"\n  NOTE: at {granted:,.0f} Hz the AC hold gives "
          f"{granted / (cfg.ac_hold.freq_khz * 1000):.1f} samples/cycle")

rule("C. Open a DaqSession and play one waveform")
print("  CONNECT: BNC from ao1 to ai0.  Piezo still disconnected.")
input("  press Enter when the cable is in, or Ctrl-C to stop... ")

from stmlab.daq import DaqSession                       # noqa: E402
from stmlab import analysis                             # noqa: E402

with DaqSession(cfg) as session:
    print(f"  idle output behaviour: {session.idle_behavior}")
    if session.idle_behavior != "maintain":
        print("  ^ the card refused MAINTAIN_EXISTING_VALUE. Outputs fall to")
        print("    0 V between plays. Safe (0 V is retracted) but the")
        print("    step-wise approach will not hold position. See bringup 3.")

    n = 4000
    wave = np.zeros((2, n))
    wave[cfg.channels.ROW_BIAS] = -0.1
    wave[cfg.channels.ROW_BIAS, n // 2:n // 2 + 400] = +0.1
    record = session.play(wave)
    print(f"  played {wave.shape}, read back {record.shape}")
    print(f"  retriggerable AI: {session._retriggerable}")

    edge = analysis.find_alignment_edge(record[cfg.channels.ROW_VOLTAGE],
                                        search_from=n // 4)
    if edge is None:
        print("\n  NO EDGE FOUND. Either the BNC is not connected, or ai0 is")
        print("  AC-coupled (the 4461 defaults to AC and a DC step vanishes).")
    else:
        print(f"  spike written at {n // 2}, seen at {edge:.2f}")
        print(f"  -> AI/AO group delay {edge - (n // 2 - 0.5):.2f} samples")

rule("D. Then the packaged bring-up, in order")
print("""      python -m stmlab.main bringup 1    devices, channels, rate   no cables
      python -m stmlab.main bringup 2    group delay + SCATTER     ao1 -> ai0
      python -m stmlab.main bringup 3    does ao0 HOLD?            ao0 -> ai0
      python -m stmlab.main bringup 4    preamp gain and zero      resistor
      python -m stmlab.main bringup 5    coarse actuator           NanoPZ USB

  Step 2 matters most: the delay SCATTER must be under one sample, or AI is
  not really triggered off ao/StartTrigger and displacement is not reliably
  aligned to current.

  Only after all five pass should the piezo be connected -- and then watch
  ao0 on a scope through one engage() and confirm it ramps 0 -> 10 V and
  never goes negative. That last step is deliberately not automated.""")

rule("The one thing still unverified that can damage hardware")
print("  Whether 0-10 V is the limit AT ao0 or at the piezo AFTER the driver")
print("  box. If the box has gain, the DAQ-side limit is lower than 10 V and")
print("  the config as shipped would over-drive the piezo.")
print("  Settle that before connecting the piezo.")
