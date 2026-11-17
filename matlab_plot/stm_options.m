function opt = stm_options(defaults, args)
%STM_OPTIONS  Turn 'name', value pairs into a struct of settings.
%
%   A helper for stm_load, stm_hist1d, stm_hist2d and stm_trace. DEFAULTS
%   is a struct with every setting the function knows (lower-case names)
%   and its default value. ARGS is the function's varargin: either
%   'name', value pairs, or one struct whose fields are the settings.
%   A name that is not in DEFAULTS is an error that lists the known ones.

    opt = defaults;
    if numel(args) == 1 && isstruct(args{1})
        given = args{1};
        fields = fieldnames(given);
        args = cell(1, 2 * numel(fields));
        for i = 1:numel(fields)
            args{2 * i - 1} = fields{i};
            args{2 * i} = given.(fields{i});
        end
    end
    if mod(numel(args), 2) ~= 0
        error('stm:options', 'Options come in pairs: ''name'', value');
    end
    names = fieldnames(defaults);
    for i = 1:2:numel(args)
        key = lower(char(args{i}));
        if ~any(strcmp(key, names))
            error('stm:options', 'Unknown option ''%s''. The options are: %s', ...
                  key, strjoin(names', ', '));
        end
        opt.(key) = args{i + 1};
    end
end
