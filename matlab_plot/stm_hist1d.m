function [x, counts, info] = stm_hist1d(d, varargin)
%STM_HIST1D  The 1D conductance histogram of loaded traces.
%
%   stm_hist1d(d)                       compute it and draw it
%   [x, counts] = stm_hist1d(d)         also hand back the curve
%   [x, counts] = stm_hist1d(d, 'plot', false)     compute only
%   stm_hist1d(d, 'xlim', [-6 1], 'color', 'r')    options, as name-value pairs
%
%   D comes from stm_load. X is log10(G/G0) at the middle of each bin and
%   COUNTS the counts per trace, so histograms of different numbers of
%   traces can be compared.
%
%   The recipe is Igor's (LogHistFromBlocks), the same as plot.py's.
%   For every trace:
%     1. keep the first 95 % of the points (the end holds a spike);
%     2. smooth with a box, 11 points wide;
%     3. take the mean of the last 1 % of what is left as the noise floor;
%     4. if that floor is not below the gate (5e-4 G0), leave the trace
%        out: it never reached a clean floor;
%     5. subtract the floor, smooth again, take log10 and count.
%   The total is divided by the number of traces that were counted.
%
%   Options for the calculation:
%     'bins'      1000    number of bins
%     'smooth'    11      width of the smoothing box, points (1 = none)
%     'gate'      5e-4    the floor gate, in G0. [] counts every trace
%     'igorbins'  true    Igor's bins: bin i starts at -8 + i*10/999.
%                         false: even bins from -8 to 2
%     'tail'      22      rows a block column has after the trace; the
%                         95 % cut counts them, as Igor's did
%   Options for the picture:
%     'plot'      true
%     'xlim'      [-7 1]  log10(G/G0)
%     'ylim'      []      counts per trace; [] = automatic
%     'logy'      false   logarithmic counts axis
%     'color'     'k'
%     'linewidth' 1.2
%
%   INFO has more: info.used (traces counted), info.n (traces given),
%   info.peak (where the 1 G0 peak is, in decades), info.edges (bin edges).

    opt = stm_options(struct('bins', 1000, 'smooth', 11, 'gate', 5e-4, ...
        'igorbins', true, 'tail', 22, 'plot', true, 'xlim', [-7 1], ...
        'ylim', [], 'logy', false, 'color', 'k', 'linewidth', 1.2), varargin);
    bins = max(10, round(opt.bins));
    lo = -8;
    hi = 2;

    % The bin edges.
    if opt.igorbins
        edges = lo + ((0:bins) * (hi - lo)) / (bins - 1);
    else
        edges = (0:bins) * ((hi - lo) / bins) + lo;
        edges(end) = hi;
    end
    edges = edges(:);
    x = 0.5 * (edges(1:end - 1) + edges(2:end));

    counts = zeros(bins, 1);
    used = 0;
    for b = 1:numel(d.block)
        G = double(d.block(b).G);                 % points x traces
        N = size(G, 1);

        % 1. the first 95 %, counted over the whole block column
        keep = floor((N + opt.tail) * 0.95);
        keep = max(1, min(N, keep));
        % 2. smooth
        S = stm_boxcar(G(1:keep, :), opt.smooth);
        % 3. the noise floor of each trace
        first = floor(keep * 0.95) + 1;
        last  = min(keep, floor(keep * 0.96) + 1);
        if first <= last
            noiseFloor = mean(S(first:last, :), 1);
        else
            noiseFloor = zeros(1, size(S, 2));
        end
        % 4. the gate
        if isempty(opt.gate)
            pass = true(1, size(S, 2));
        else
            pass = noiseFloor < opt.gate;
        end
        if ~any(pass)
            continue
        end
        % 5. subtract, smooth again, log10, count
        S = stm_boxcar(bsxfun(@minus, S(:, pass), noiseFloor(pass)), opt.smooth);
        positive = S > 0 & isfinite(S);
        used = used + nnz(any(positive, 1));
        bin = stm_bin(log10(S(positive)), edges);
        bin = bin(bin > 0);
        if ~isempty(bin)
            counts = counts + accumarray(bin, 1, [bins 1]);
        end
    end
    if used > 0
        counts = counts / used;
    end

    info.used = used;
    info.n = d.n;
    info.edges = edges;
    info.peak = peak_near(x, counts, 0, 0.4, 0.15);

    if opt.plot
        plot(x, counts, 'Color', opt.color, 'LineWidth', opt.linewidth);
        xlabel('log_{10}(G / G_0)');
        ylabel('counts per trace');
        if used < d.n
            label = sprintf('%s: %d traces (%d left out by the floor gate)', ...
                            d.name, d.n, d.n - used);
        else
            label = sprintf('%s: %d traces', d.name, d.n);
        end
        title(label, 'Interpreter', 'none');
        if ~isempty(opt.xlim)
            xlim(opt.xlim);
        end
        if ~isempty(opt.ylim)
            ylim(opt.ylim);
        end
        if opt.logy
            set(gca, 'YScale', 'log');
        end
        grid on;
        box on;
    end
end


function p = peak_near(x, counts, around, window, refine)
% Where the histogram peak near AROUND is, in decades: the highest bin
% within WINDOW of it, then the centre of mass of the bins within REFINE
% of that bin.
    p = NaN;
    sel = abs(x - around) <= window;
    if ~any(sel) || sum(counts(sel)) == 0
        return
    end
    local = counts;
    local(~sel) = -Inf;
    [~, i] = max(local);
    apex = x(i);
    near = abs(x - apex) <= refine;
    if sum(counts(near)) == 0
        p = apex;
    else
        p = sum(x(near) .* counts(near)) / sum(counts(near));
    end
end
