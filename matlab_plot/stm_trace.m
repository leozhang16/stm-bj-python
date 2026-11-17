function [x, g] = stm_trace(d, number, varargin)
%STM_TRACE  One trace: conductance against displacement.
%
%   stm_trace(d, 1234)                  draw trace number 1234
%   [x, g] = stm_trace(d, 1234)         also hand back the trace
%   [x, g] = stm_trace(d, 1234, 'plot', false)       the trace only
%
%   D comes from stm_load and NUMBER is the trace number, Igor's
%   numbering through the day. X is the displacement in nm (0 where the
%   pull began) and G the conductance in G0, as saved: nothing is
%   smoothed. The plot shows log10(G), with a dashed line at 1 G0.
%
%   Options:
%     'plot'      true
%     'color'     [0 0.447 0.741]
%     'xlim'      []       nm; [] = the whole pull
%     'ylim'      [-7 1]   log10(G/G0)

    opt = stm_options(struct('plot', true, 'color', [0 0.447 0.741], ...
        'xlim', [], 'ylim', [-7 1]), varargin);

    g = [];
    for b = 1:numel(d.block)
        col = find(d.block(b).numbers == number, 1);
        if ~isempty(col)
            g = double(d.block(b).G(:, col));
            len = d.block(b).size_nm(col);
            break
        end
    end
    if isempty(g)
        error('stm_trace:missing', ...
              'Trace %d is not loaded. Loaded: %d traces, numbers %d to %d.', ...
              number, d.n, min(d.numbers), max(d.numbers));
    end

    % The displacement axis: from 0 to the pull length, as Igor scaled it.
    n = numel(g);
    if len > 0 && n > 1
        x = (0:n - 1)' * (len / (n - 1));
        x(end) = len;
    else
        x = (0:n - 1)';
    end

    if opt.plot
        plot(x, log10(max(g, 1e-12)), 'Color', opt.color, 'LineWidth', 0.8);
        hold on;
        plot([x(1) x(end)], [0 0], '--', 'Color', [0.5 0.5 0.5]);
        hold off;
        xlabel('displacement (nm)');
        ylabel('log_{10}(G / G_0)');
        title(sprintf('%s: trace %d', d.name, number), 'Interpreter', 'none');
        if isempty(opt.xlim)
            xlim([x(1) x(end)]);
        else
            xlim(opt.xlim);
        end
        if ~isempty(opt.ylim)
            ylim(opt.ylim);
        end
        grid on;
        box on;
    end
end
