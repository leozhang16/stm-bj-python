function S = stm_boxcar(G, width)
%STM_BOXCAR  Box smoothing down each column, as Igor's Smooth/B.
%
%   S = stm_boxcar(G, width)
%
%   Every point becomes the mean of the WIDTH points around it. At the two
%   ends, where there are not enough points on one side, the trace is
%   continued as its own mirror image (Igor's default, "bounce"), so the
%   ends are not pulled toward zero. An even WIDTH is rounded up to the
%   next odd number, as Igor does. G can be one trace (a column) or many
%   (one column each).

    width = round(width);
    if width <= 1 || isempty(G)
        S = G;
        return
    end
    if mod(width, 2) == 0
        width = width + 1;
    end
    pad = (width - 1) / 2;
    n = size(G, 1);
    if n <= pad
        S = G;            % too short to mirror: leave it as it is
        return
    end
    mirrored = [G(pad + 1:-1:2, :); G; G(n - 1:-1:n - pad, :)];
    S = conv2(mirrored, ones(width, 1) / width, 'valid');
end
