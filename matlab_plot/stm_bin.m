function bin = stm_bin(values, edges)
%STM_BIN  Which bin each value falls in.
%
%   bin = stm_bin(values, edges)
%
%   EDGES are the bin edges, evenly spaced and increasing; there is one
%   bin fewer than there are edges. Bin i holds the values from edges(i)
%   up to, but not including, edges(i+1); the last bin also holds a value
%   equal to the last edge. BIN is 0 for a value outside the edges, so
%   that  bin(bin > 0)  are the ones to count.
%
%   (The same rule as numpy.histogram, which plot.py uses, so the two
%   give the same counts.)

    values = values(:);
    edges = edges(:);
    n = numel(edges) - 1;
    bin = zeros(size(values));
    inside = values >= edges(1) & values <= edges(end);
    if ~any(inside)
        return
    end
    v = values(inside);
    step = (edges(end) - edges(1)) / n;
    i = floor((v - edges(1)) / step) + 1;
    i = min(max(i, 1), n);
    % Settle the values that sit right at an edge against the edges
    % themselves, not against the division above.
    low = v < edges(i);
    i(low) = i(low) - 1;
    high = v >= edges(i + 1) & i < n;
    i(high) = i(high) + 1;
    bin(inside) = i;
end
