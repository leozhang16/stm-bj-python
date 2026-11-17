%% plot_stm.m
% Plot break-junction data saved by Igor (or by pullout.py): the 1D
% histogram, the 2D histogram and one trace.
%
%   1. Fill in the settings below.
%   2. Press Run. Three figures come up.
%   3. Change a limit or a colour below and run again. Or change it on
%      the figure itself, or type for example  caxis([0 2])  or
%      xlim([-0.2 1.5])  in the Command Window.
%
% After a run the numbers are in the workspace: x1 and c1 (the 1D
% histogram), c2 with xe and ye (the 2D histogram and its bin edges),
% xt and gt (the trace), and d (everything that was loaded).

%% Settings

% The day folder: the one that holds PullOutConductanceBlock_1.ibw, _2.ibw ...
folder = '/Users/ly666/Library/CloudStorage/SynologyDrive-SynNAS/STM_Data/11_11_26';

% Which traces. [] is every trace of the day.
% One experiment:        [1001 6000]      (first and last, both included)
% Several put together:  [1 1000; 6001 11000]
traces = [1001 6001];

% The 1D histogram
h1.xlim   = [-7 1];     % log10(G/G0)
h1.ylim   = [];         % counts per trace; [] = automatic
h1.logy   = false;      % true: logarithmic counts axis
h1.color  = 'k';
h1.bins   = 1000;
h1.smooth = 11;         % smoothing box, points
h1.gate   = 5e-4;       % leave out traces whose noise floor is not below
                        % this (G0), as Igor did. [] counts every trace

% The 2D histogram
h2.xrange   = [-0.5 2];   % displacement covered by the bins, nm
h2.yrange   = [-7 1];     % log10(G/G0) covered by the bins
h2.nx       = 200;        % bins along the displacement
h2.ny       = 300;        % bins along the conductance
h2.align    = 0.5;        % 0 nm is where G first drops below this (G0)
h2.smooth   = 11;
h2.clim     = [];         % colour limits [low high]; [] = 0 to the maximum
h2.colormap = '';         % 'parula', 'hot', 'jet', 'turbo' ...; '' = default
h2.xlim     = [];         % what part to show; [] = all of xrange
h2.ylim     = [];         %                    [] = all of yrange

% One trace. [] is the first trace that was loaded.
trace_number = [];

%% Load

here = fileparts(mfilename('fullpath'));      % the functions sit beside this file
if ~isempty(here)
    addpath(here);
end
d = stm_load(folder, 'traces', traces);
fprintf('%s: %d traces loaded (numbers %d to %d)\n', ...
        d.name, d.n, min(d.numbers), max(d.numbers));

%% The 1D histogram

figure(1); clf;
[x1, c1, info1] = stm_hist1d(d, h1);
fprintf('1D: %d of %d traces counted, 1 G0 peak at %+.3f decades\n', ...
        info1.used, info1.n, info1.peak);

% Data of a two-channel amplifier (pullout.py) has channel 2 in the
% subfolder ch2: draw it over channel 1, in red.
ch2 = fullfile(folder, 'ch2');
d_ch2 = [];
if exist(ch2, 'dir') == 7
    try
        d_ch2 = stm_load(ch2, 'traces', traces);
    catch
        d_ch2 = [];          % no channel 2 for these traces
    end
end
if ~isempty(d_ch2)
    h1_ch2 = h1;
    h1_ch2.color = 'r';
    hold on;
    [x1_ch2, c1_ch2] = stm_hist1d(d_ch2, h1_ch2);
    hold off;
    legend('channel 1', 'channel 2', 'Location', 'northwest');
    title(sprintf('%s: %d traces, two channels', d.name, d.n), 'Interpreter', 'none');
end

%% The 2D histogram

figure(2); clf;
[c2, xe, ye, info2] = stm_hist2d(d, h2);
fprintf('2D: %d of %d traces counted, highest count %.3g per trace\n', ...
        info2.used, info2.n, info2.max);

%% One trace

if isempty(trace_number)
    trace_number = d.numbers(1);
end
figure(3); clf;
[xt, gt] = stm_trace(d, trace_number);
