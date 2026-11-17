function w = read_ibw(filename, keepClass)
%READ_IBW  Read an Igor Pro binary wave file (.ibw).
%
%   w = read_ibw(filename)
%   w = read_ibw(filename, true)    keep the numbers in the file's own type
%                                   (single stays single: half the memory)
%
%   What comes back:
%     w.data      the wave's values, in the wave's own shape:
%                 a column for a 1-D wave, rows x columns for a 2-D wave
%     w.name      the wave's name in Igor
%     w.dx, w.x0  the x scaling of the rows:  x = x0 + (0:n-1)*dx
%     w.sfA, w.sfB  the same two numbers for each of the 4 dimensions
%     w.dims      the size of each dimension
%     w.note      the wave note (text)
%     w.version   the file format version (1, 2, 3 or 5)
%     w.type      Igor's number-type code (2 = single, 4 = double, ...)
%
%   Numeric waves only. The file layout is the one in Igor's Technical
%   Note 003, "Igor Binary Format". Files written on either kind of
%   computer (little-endian or big-endian) are read.

    if nargin < 2 || isempty(keepClass)
        keepClass = false;
    end
    filename = char(filename);

    % The first two bytes are the version number. If the first byte is 0
    % the file was written with the bytes the other way round.
    fid = fopen(filename, 'r');
    if fid < 0
        error('read_ibw:open', 'Cannot open %s', filename);
    end
    first = fread(fid, 2, 'uint8');
    fclose(fid);
    if numel(first) < 2
        error('read_ibw:short', '%s is too short to be an Igor wave', filename);
    end
    if first(1) == 0
        machine = 'ieee-be';
    else
        machine = 'ieee-le';
    end

    fid = fopen(filename, 'r', machine);
    closeIt = onCleanup(@() fclose(fid));
    fseek(fid, 0, 'eof');
    fileSize = ftell(fid);
    fseek(fid, 0, 'bof');

    fmtVersion = fread(fid, 1, 'int16');
    formulaSize = 0;
    noteSize = 0;
    switch fmtVersion
        case 1
            wfmSize = fread(fid, 1, 'int32');
            binSize = 8;
        case 2
            wfmSize  = fread(fid, 1, 'int32');
            noteSize = fread(fid, 1, 'int32');
            binSize = 16;
        case 3
            wfmSize     = fread(fid, 1, 'int32');
            noteSize    = fread(fid, 1, 'int32');
            formulaSize = fread(fid, 1, 'int32');
            binSize = 20;
        case 5
            fseek(fid, 4, 'bof');
            wfmSize     = fread(fid, 1, 'int32');
            formulaSize = fread(fid, 1, 'int32');
            noteSize    = fread(fid, 1, 'int32');
            binSize = 64;
        otherwise
            error('read_ibw:version', ...
                  '%s: version %d is not an Igor binary wave (1, 2, 3 or 5)', ...
                  filename, fmtVersion);
    end

    sfA = [1; 1; 1; 1];
    sfB = [0; 0; 0; 0];
    if fmtVersion == 5
        % WaveHeader5: 320 bytes, then the data.
        h = binSize;
        fseek(fid, h + 12, 'bof');
        npnts = fread(fid, 1, 'int32');
        numType  = fread(fid, 1, 'int16');
        fseek(fid, h + 28, 'bof');
        name = fread(fid, 32, 'uint8')';
        fseek(fid, h + 68, 'bof');
        dims = fread(fid, 4, 'int32');
        sfA  = fread(fid, 4, 'double');
        sfB  = fread(fid, 4, 'double');
        dataStart = h + 320;
        noteStart = h + wfmSize + formulaSize;
    else
        % WaveHeader2: 110 bytes, then the data, then 16 bytes of padding.
        h = binSize;
        fseek(fid, h, 'bof');
        numType = fread(fid, 1, 'int16');
        fseek(fid, h + 6, 'bof');
        name = fread(fid, 20, 'uint8')';
        fseek(fid, h + 42, 'bof');
        npnts = fread(fid, 1, 'int32');
        fseek(fid, h + 48, 'bof');
        sfA(1) = fread(fid, 1, 'double');
        sfB(1) = fread(fid, 1, 'double');
        dims = [npnts; 0; 0; 0];
        dataStart = h + 110;
        noteStart = h + wfmSize;
    end

    % The number type is a set of flags.
    isComplex  = mod(numType, 2) == 1;
    isUnsigned = mod(floor(numType / 64), 2) == 1;
    kind = numType - isComplex - 64 * isUnsigned;
    switch kind
        case 2
            precision = 'single';
            bytesPer = 4;
        case 4
            precision = 'double';
            bytesPer = 8;
        case 8
            precision = 'int8';
            bytesPer = 1;
        case 16
            precision = 'int16';
            bytesPer = 2;
        case 32
            precision = 'int32';
            bytesPer = 4;
        case 128
            precision = 'int64';
            bytesPer = 8;
        case 0
            error('read_ibw:text', '%s is a text wave; only numeric waves are read', filename);
        otherwise
            error('read_ibw:type', '%s: unknown Igor number type %d', filename, numType);
    end
    if isUnsigned && kind >= 8
        precision = ['u' precision];
    end
    if keepClass
        spec = [precision '=>' precision];
    else
        spec = [precision '=>double'];
    end

    nValues = npnts * (1 + isComplex);
    % How many values the file really holds, from the size in its header.
    % (A wave that Igor computes from a formula is saved without values.)
    if fmtVersion == 5
        stored = floor((wfmSize - 320) / bytesPer);
    else
        stored = floor((wfmSize - 126) / bytesPer);
    end
    if stored >= 0 && stored < nValues
        nValues = stored;
        npnts = floor(nValues / (1 + isComplex));
        nValues = npnts * (1 + isComplex);
    end
    fseek(fid, dataStart, 'bof');
    data = fread(fid, nValues, spec);
    if numel(data) ~= nValues
        error('read_ibw:data', '%s: the file ends before its %d points do', filename, npnts);
    end
    if isComplex
        data = complex(data(1:2:end), data(2:2:end));
    end

    % Igor stores a 2-D wave one column after the other, as MATLAB does.
    shape = dims(dims > 0)';
    if isempty(shape) || prod(shape) ~= npnts
        shape = [npnts 1];
    elseif numel(shape) == 1
        shape = [shape 1];
    end
    data = reshape(data, shape);

    note = '';
    if noteSize > 0 && noteStart + noteSize <= fileSize
        fseek(fid, noteStart, 'bof');
        note = fread(fid, noteSize, 'uint8=>char')';
    end

    stop = find(name == 0, 1);
    if ~isempty(stop)
        name = name(1:stop - 1);
    end

    w.data    = data;
    w.name    = char(name);
    w.dx      = sfA(1);
    w.x0      = sfB(1);
    w.sfA     = sfA;
    w.sfB     = sfB;
    w.dims    = dims;
    w.note    = note;
    w.version = fmtVersion;
    w.type    = numType;
end
