# matlab_plot

MATLAB code that plots the break-junction data Igor saved: the 1D
histogram, the 2D histogram and single traces. It reads the same day
folders as `plot.py` and gives the same numbers; the point of having it in
MATLAB is that the figures are MATLAB figures, so the axis limits, the
colour limits and the colormap are yours to change.

It also reads what `pullout.py` saves, because that is the same scheme.

## The quick way

1. Open `plot_stm.m` in MATLAB.
2. At the top, set `folder` to the day folder (the one that holds
   `PullOutConductanceBlock_1.ibw`, `_2.ibw`, ...) and `traces` to the trace
   numbers you want.
3. Press Run. Three figures come up: the 1D histogram, the 2D histogram and
   one trace.

Everything you are likely to change is in the settings at the top of that
file:

| Setting | What it does |
|---|---|
| `folder` | the day folder |
| `traces` | `[1001 6000]` is traces 1001 to 6000, both included. `[]` is the whole day. `[1 1000; 6001 11000]` puts two ranges together |
| `h1.xlim`, `h1.ylim`, `h1.logy`, `h1.color` | the 1D histogram's axes and colour |
| `h1.gate` | Igor left out of the histogram every trace whose noise floor was not below 5e-4 G0. `[]` counts every trace |
| `h2.clim` | the colour limits of the 2D histogram, `[low high]` in counts per trace. `[]` is 0 to the highest count |
| `h2.colormap` | `'parula'`, `'hot'`, `'jet'`, `'turbo'`, ... |
| `h2.xlim`, `h2.ylim` | what part of the 2D histogram is shown |
| `h2.xrange`, `h2.yrange`, `h2.nx`, `h2.ny` | what the bins cover and how many there are. To see further out than -0.5 to 2 nm, widen `h2.xrange` |
| `h2.align` | 0 nm is where the conductance first drops below this (0.5 G0) |
| `trace_number` | which trace the third figure shows |

You can also change a figure after it is drawn, with the mouse or by
typing, for example:

```matlab
figure(2); caxis([0 2]); colormap(hot); xlim([-0.2 1.5]);
```

After a run the numbers are in the workspace, for plots of your own:
`x1`, `c1` (the 1D histogram), `c2`, `xe`, `ye` (the 2D histogram and its
bin edges), `xt`, `gt` (the trace) and `d` (everything that was loaded).

## Trace numbers

They are Igor's, counted through the day. Igor's Stop # is the number it
stops *before*: a run from Saved 1 with Stop # 1001 saved traces 1 to 1000,
and the next run with Stop # 6001 saved 1001 to 6000. So that experiment is
`traces = [1001 6000]`.

## From the Command Window

The script only calls four functions, which you can use directly:

```matlab
d = stm_load('C:\Data\11_16_26Merge', 'traces', [1001 6000]);

stm_hist1d(d);                                   % draws the 1D histogram
[x, counts] = stm_hist1d(d, 'plot', false);      % or just hands it back

figure; stm_hist2d(d, 'clim', [0 2], 'colormap', 'hot');
[c, xedges, yedges] = stm_hist2d(d, 'plot', false);

figure; stm_trace(d, 1500);                      % trace number 1500
[x, g] = stm_trace(d, 1500, 'plot', false);
```

`help stm_hist1d` (and the same for the others) lists every option.

To compare two experiments, draw one over the other:

```matlab
a = stm_load(folder, 'traces', [1 1000]);
b = stm_load(folder, 'traces', [1001 6000]);
stm_hist1d(a, 'color', 'k'); hold on; stm_hist1d(b, 'color', 'r'); hold off
legend('clean gold', 'molecule')
```

## The files

| File | What it is |
|---|---|
| `plot_stm.m` | the script to run: settings at the top, three figures |
| `stm_load.m` | loads a day folder, or one block file, or part of either |
| `stm_hist1d.m` | the 1D histogram, Igor's recipe |
| `stm_hist2d.m` | the 2D histogram |
| `stm_trace.m` | one trace |
| `read_ibw.m` | reads any Igor binary wave (`.ibw`) into MATLAB; useful by itself |
| `stm_boxcar.m`, `stm_bin.m`, `stm_options.m` | small helpers the others use |

No toolbox is needed.

## Two-channel data

Data taken by `pullout.py` with a two-channel amplifier has channel 2 in
the subfolder `ch2` of the day folder. `plot_stm.m` notices it and draws
channel 2 over channel 1 in the 1D histogram, in red. For the 2D histogram
or a trace of channel 2, point `folder` at the `ch2` subfolder: it is read
like a day folder.

One difference from `plot.py`: here each channel is gated by its own noise
floor, while `plot.py` gates both channels by channel 2's. If channel 1's
curve looks emptier here than there, set `h1.gate = []`.

## How it was checked

The numbers were compared with `plot.py`'s on the same folders: the loaded
traces, the 1D histogram, the 2D histogram and the 1 G0 peak position are
identical, bin for bin, for whole days, for trace ranges, for folders with
missing blocks and half-filled blocks, and for traces that the floor gate
leaves out. `read_ibw.m` was compared with the `igor2` Python library on
Igor's own sample files (written on Windows and on a Mac, file versions 2,
3 and 5).

Those checks were run with GNU Octave 8.4, which runs MATLAB code, not
with MATLAB itself. The code keeps to plain MATLAB, so it should behave
the same there; if MATLAB reports an error, the message and the line
number are what is needed to fix it.
