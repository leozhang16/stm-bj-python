function [counts, xedges, yedges, info] = stm_hist2d(d, varargin)
%STM_HIST2D  The 2D histogram: conductance against displacement.
%
%   stm_hist2d(d)                                   compute it and draw it
%   [counts, xedges, yedges] = stm_hist2d(d)        also hand back the numbers
%   [counts, xedges, yedges] = stm_hist2d(d, 'plot', false)     compute only
%   stm_hist2d(d, 'clim', [0 3], 'colormap', 'hot')  options, as name-value pairs
%
%   D comes from stm_load. COUNTS(i, j) is the counts per trace in
%   displacement bin i and log10(G/G0) bin j; XEDGES and YEDGES are the
%   bin edges (nm and decades). To draw it yourself:
%       imagesc(xcentres, ycentres, counts');  set(gca, 'YDir', 'normal')
%
%   The recipe is plot.py's. For every trace: keep the first 95 % of the
%   points, smooth with a box 11 points wide, and put 0 nm where the
%   conductance first drops below 0.5 G0 (the gold contact breaking), so
%   that all traces are lined up there. A trace that never drops below
%   0.5 G0 is left out. The total is divided by the number of traces
%   that were counted.
%
%   Options for the calculation:
%     'xrange'   [-0.5 2]   displacement covered by the bins, nm
%     'yrange'   [-7 1]     log10(G/G0) covered by the bins
%     'nx'       200        bins along the displacement
%     'ny'       300        bins along the conductance
%     'align'    0.5        0 nm is where G first drops below this, in G0.
%                           [] leaves 0 nm at the start of the pull
%     'smooth'   11         width of the smoothing box, points (1 = none)
%   Options for the picture:
%     'plot'     true
%     'clim'     []         colour limits [low high], counts per trace;
%                           [] = from 0 to the highest count
%     'colormap' ''         a colormap name ('parula', 'hot', 'jet', ...)
%                           or an N x 3 matrix; '' = MATLAB's default
%     'xlim'     []         axis limits; [] = the whole of xrange / yrange
%     'ylim'     []
%
%   The bins only cover xrange and yrange: to see further out, widen
%   those; 'xlim' and 'ylim' only choose what part is shown.
%
%   INFO has more: info.used (traces counted), info.n (traces given),
%   info.max (the highest count per trace).

    opt = stm_options(struct('xrange', [-0.5 2], 'yrange', [-7 1], ...
        'nx', 200, 'ny', 300, 'align', 0.5, 'smooth', 11, 'plot', true, ...
        'clim', [], 'colormap', '', 'xlim', [], 'ylim', []), varargin);
    nx = max(10, round(opt.nx));
    ny = max(10, round(opt.ny));
    xedges = even_edges(opt.xrange(1), opt.xrange(2), nx);
    yedges = even_edges(opt.yrange(1), opt.yrange(2), ny);

    counts = zeros(nx, ny);
    used = 0;
    for b = 1:numel(d.block)
        G = double(d.block(b).G);                 % points x traces
        [N, m] = size(G);
        keep = max(1, floor(N * 0.95));
        S = stm_boxcar(G(1:keep, :), opt.smooth);

        % The displacement of every point: from 0 to the pull length.
        step = d.block(b).size_nm / max(1, N - 1);          % nm per point
        step(~(d.block(b).size_nm > 0)) = 1;
        X = (0:keep - 1)' * step;                           % points x traces

        if isempty(opt.align)
            pick = true(1, m);
        else
            below = S < opt.align;
            pick = any(below, 1);                 % traces that do break
            [~, first] = max(below, [], 1);       % the point where they do
            X = bsxfun(@minus, X, (first - 1) .* step);
        end
        if ~any(pick)
            continue
        end
        S = S(:, pick);
        X = X(:, pick);

        positive = S > 0 & isfinite(S);
        used = used + nnz(any(positive, 1));
        ix = stm_bin(X(positive), xedges);
        iy = stm_bin(log10(S(positive)), yedges);
        inside = ix > 0 & iy > 0;
        if any(inside)
            counts = counts + accumarray([ix(inside) iy(inside)], 1, [nx ny]);
        end
    end
    if used > 0
        counts = counts / used;
    end

    info.used = used;
    info.n = d.n;
    info.max = max(counts(:));

    if opt.plot
        xc = 0.5 * (xedges(1:end - 1) + xedges(2:end));
        yc = 0.5 * (yedges(1:end - 1) + yedges(2:end));
        imagesc(xc, yc, counts');
        set(gca, 'YDir', 'normal');
        if ischar(opt.colormap)
            if ~isempty(opt.colormap)
                colormap(feval(opt.colormap, 256));
            end
        else
            colormap(opt.colormap);
        end
        if ~isempty(opt.clim)
            caxis(opt.clim);
        elseif info.max > 0
            caxis([0 info.max]);
        end
        cb = colorbar;
        ylabel(cb, 'counts per trace');
        if isempty(opt.align)
            xlabel('displacement (nm)');
        else
            xlabel(sprintf('displacement (nm), 0 where G first < %g G_0', opt.align));
        end
        ylabel('log_{10}(G / G_0)');
        title(sprintf('%s: %d traces', d.name, d.n), 'Interpreter', 'none');
        if ~isempty(opt.xlim)
            xlim(opt.xlim);
        end
        if ~isempty(opt.ylim)
            ylim(opt.ylim);
        end
    end
end


function edges = even_edges(lo, hi, n)
% N even bins from LO to HI: N + 1 edges, as a column.
    edges = (0:n)' * ((hi - lo) / n) + lo;
    edges(end) = hi;
end
