function d = stm_load(source, varargin)
%STM_LOAD  Load break-junction traces saved in Igor's day-folder scheme.
%
%   d = stm_load(folder)                                 every trace of the day
%   d = stm_load(folder, 'traces', [1001 6000])          only these trace numbers
%   d = stm_load(folder, 'traces', [1 1000; 6001 11000]) several ranges
%   d = stm_load(folder, 'blocks', 11:60)                only these block files
%   d = stm_load(file)                    one PullOutConductanceBlock_k.ibw
%
%   FOLDER is the day folder Igor saved (and pullout.py saves the same
%   way): the one holding PullOutConductanceBlock_1.ibw, _2.ibw, ...
%   Each of those files is a block of 100 traces. Trace numbers are
%   Igor's: block k holds traces (k-1)*100 + 1 to k*100. A range gives
%   the first and the last trace, both included.
%
%   What comes back:
%     d.name       text for plot titles
%     d.folder     the folder that was read
%     d.n          how many traces were loaded
%     d.numbers    their trace numbers
%     d.block(i)   one entry per block file that was read:
%        .k        the block number
%        .G        conductance in G0, one column per trace (single)
%        .numbers  the trace number of each column
%        .size_nm  the pull length of each column, nm: the x axis of a
%                  trace runs from 0 to size_nm
%        .params   Igor's 20 parameters of each column (20 x traces)
%
%   Then: stm_hist1d(d), stm_hist2d(d), stm_trace(d, number).

    opt = stm_options(struct('traces', [], 'blocks', []), varargin);
    source = char(source);
    BLOCK = 100;      % traces in a block file
    TAIL = 22;        % rows after the trace: 2 empty rows and 20 parameters
    pattern = '^PullOutConductanceBlock_(\d+)\.ibw$';

    % Which block files are there?
    if exist(source, 'dir') == 7
        folder = source;
        while numel(folder) > 1 && any(folder(end) == '/\')
            folder(end) = [];
        end
        listing = dir(fullfile(folder, 'PullOutConductanceBlock_*.ibw'));
        ks = [];
        for i = 1:numel(listing)
            tok = regexp(listing(i).name, pattern, 'tokens', 'once');
            if ~isempty(tok)
                ks(end + 1) = str2double(tok{1}); %#ok<AGROW>
            end
        end
        ks = sort(ks);
        if isempty(ks)
            error('stm_load:empty', ...
                  '%s holds no PullOutConductanceBlock_k.ibw file', folder);
        end
        [~, name, ext] = fileparts(folder);
        name = [name ext];
    elseif exist(source, 'file') == 2
        [folder, base, ext] = fileparts(source);
        tok = regexp([base ext], pattern, 'tokens', 'once');
        if isempty(tok)
            error('stm_load:name', ...
                  '%s is not a PullOutConductanceBlock_k.ibw file', [base ext]);
        end
        ks = str2double(tok{1});
        name = base;
    else
        error('stm_load:missing', '%s is neither a folder nor a file', source);
    end

    % The trace ranges, as rows of [first last].
    ranges = opt.traces;
    if ~isempty(ranges)
        if numel(ranges) == 2
            ranges = reshape(ranges, 1, 2);
        end
        if size(ranges, 2) ~= 2 || any(ranges(:, 1) > ranges(:, 2)) || any(ranges(:) < 1)
            error('stm_load:traces', ...
                  '''traces'' is [first last], or one such row per range, counted from 1');
        end
    end

    % Only the blocks that are asked for.
    if ~isempty(opt.blocks)
        ks = ks(ismember(ks, opt.blocks));
    end
    if ~isempty(ranges)
        wanted = false(size(ks));
        for i = 1:numel(ks)
            firstOfBlock = (ks(i) - 1) * BLOCK + 1;
            lastOfBlock  = ks(i) * BLOCK;
            wanted(i) = any(ranges(:, 1) <= lastOfBlock & ranges(:, 2) >= firstOfBlock);
        end
        ks = ks(wanted);
    end
    if numel(ks) > 20
        fprintf('reading %d blocks from %s ...\n', numel(ks), name);
    end

    d.name = name;
    d.folder = folder;
    d.block = struct('k', {}, 'G', {}, 'numbers', {}, 'size_nm', {}, 'params', {});
    for k = ks
        file = fullfile(folder, sprintf('PullOutConductanceBlock_%d.ibw', k));
        w = read_ibw(file, true);
        rows = size(w.data, 1);
        if rows <= TAIL
            warning('stm_load:block', '%s has %d rows: not a block of traces, skipped', ...
                    file, rows);
            continue
        end
        N = rows - TAIL;
        params = double(w.data(N + 3:end, :));        % 20 x columns
        G = w.data(1:N, :);
        % A column is a trace when it holds numbers and its parameters
        % give a pull length and a pull rate. (A block that is not full
        % yet has its other columns empty.)
        filled = any(isfinite(G), 1) & params(1, :) > 0 & params(2, :) > 0;
        numbers = (k - 1) * BLOCK + find(filled);
        if ~isempty(ranges)
            inRange = false(size(numbers));
            for r = 1:size(ranges, 1)
                inRange = inRange | (numbers >= ranges(r, 1) & numbers <= ranges(r, 2));
            end
            numbers = numbers(inRange);
        end
        if isempty(numbers)
            continue
        end
        cols = numbers - (k - 1) * BLOCK;
        b.k = k;
        b.G = single(G(:, cols));
        b.numbers = numbers;
        b.size_nm = params(1, cols);
        b.params = params(:, cols);
        d.block(end + 1) = b;
    end

    d.numbers = [d.block.numbers];
    d.n = numel(d.numbers);
    if d.n == 0
        error('stm_load:none', '%s: no trace matches what was asked for', name);
    end
    if ~isempty(opt.blocks)
        got = [d.block.k];
        if all(diff(got) == 1)
            d.name = sprintf('%s blocks %d-%d', d.name, got(1), got(end));
        else
            d.name = sprintf('%s, %d blocks', d.name, numel(got));
        end
    end
    if ~isempty(ranges)
        parts = cell(1, size(ranges, 1));
        for r = 1:size(ranges, 1)
            parts{r} = sprintf('%d-%d', ranges(r, 1), ranges(r, 2));
        end
        d.name = [d.name ' traces ' strjoin(parts, ',')];
    end
end
