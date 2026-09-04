"""
The names of the variables in an ocean model's global statistics output.

Both models write one variable per (field, statistic) pair and name it after
the two, so the names are built from the fields and statistics that are
wanted rather than listed one by one.  Building them is what lets a step ask
for a field the map has never heard of, and what keeps the time reductions
Omega can write from needing a name apiece.

The two models do not compute quite the same statistics, and this module is
where that is written down: MPAS-Ocean computes a root-mean-square where
Omega computes a standard deviation.  Those are different quantities, so
neither model's list has an entry for the other's, and a step that wants a
standard deviation from MPAS-Ocean has to derive one.

This module is deliberately free of any dependence on
:py:class:`polaris.Step` and on the ocean component, so that it can be unit
tested on its own.  A caller that has Polaris-standard field names passes a
``field_map`` to say what each is called in the model that wrote the file.
"""

# the global statistics each ocean model computes, and the name each one is
# written under.  The keys are the Polaris-standard names used in config
# options; the lists differ because the models differ.
GLOBAL_STATS = {
    'mpas-ocean': {
        'min': 'Min',
        'max': 'Max',
        'mean': 'Avg',
        'rms': 'Rms',
    },
    'omega': {
        'min': 'SpatialMin',
        'max': 'SpatialMax',
        'mean': 'SpatialMean',
        'std': 'SpatialStdDev',
    },
}

# how each statistic is described, for plot legends and netCDF metadata
STAT_DESCRIPTIONS = {
    'min': 'global minimum',
    'max': 'global maximum',
    'mean': 'global mean',
    'std': 'global standard deviation',
    'rms': 'global root-mean-square',
}


def available_stats(model):
    """
    Get the global statistics a model computes

    Parameters
    ----------
    model : {'mpas-ocean', 'omega'}
        The ocean model that wrote the output

    Returns
    -------
    stats : list of str
        The Polaris-standard name of each statistic the model computes

    Raises
    ------
    ValueError
        If ``model`` is not an ocean model Polaris knows about
    """
    if model not in GLOBAL_STATS:
        known = ', '.join(GLOBAL_STATS)
        raise ValueError(
            f'Do not know what global statistics "{model}" computes.  The '
            f'ocean models are: {known}.'
        )
    return list(GLOBAL_STATS[model])


def global_stats_var_names(
    fields, stats, model, field_map=None, time_mean_period=None
):
    """
    Build the names of the global statistics variables to look for

    Parameters
    ----------
    fields : list of str
        The fields whose statistics are wanted.  These are the names the
        caller uses to label its results; ``field_map`` says what the model
        calls each of them.

    stats : list of str
        The statistics to look for, each of them one of
        :py:func:`available_stats` for this model

    model : {'mpas-ocean', 'omega'}
        The ocean model that wrote the output

    field_map : dict of str to str, optional
        What the model calls each field, as
        :py:meth:`polaris.tasks.ocean.Ocean.map_var_list_to_native_model`
        gives it.  A field that is missing from the map keeps its own name,
        which is the right answer for a field only one model has.

    time_mean_period : str, optional
        The period of the time reduction the variables were averaged over,
        e.g. ``'1Month'``.  The default is the spelling used for snapshots,
        which carry no period at all.

    Returns
    -------
    var_names : dict of (str, str) to str
        The variable name of each ``(field, stat)`` pair, in the order the
        fields and the statistics were given

    Raises
    ------
    ValueError
        If a statistic is not one this model computes, or if a time mean is
        asked of a model that writes none
    """
    model_stats = _model_stats(model, stats)
    if time_mean_period is not None and model != 'omega':
        raise ValueError(
            f'{model} writes no time means of its global statistics, so '
            f'there are no variables averaged over {time_mean_period}.'
        )
    if field_map is None:
        field_map = {}

    var_names = {}
    for field in fields:
        for stat in stats:
            var_names[(field, stat)] = _var_name(
                model_field=field_map.get(field, field),
                stat_name=model_stats[stat],
                model=model,
                time_mean_period=time_mean_period,
            )
    return var_names


def discover_fields(ds, model, time_mean_period=None):
    """
    Get the fields a dataset holds global statistics for

    This is the inverse of the name construction: a variable whose name ends
    in one of the statistics the model computes is a statistic of whatever
    comes before it.  It is what lets a step plot what a simulation wrote
    rather than what someone thought it would write.

    Parameters
    ----------
    ds : xarray.Dataset
        The global statistics, with the names the model gave them

    model : {'mpas-ocean', 'omega'}
        The ocean model that wrote the output

    time_mean_period : str, optional
        The period of the time reduction to look for.  The default finds the
        snapshots, and a dataset holding both is not searched for the wrong
        one.

    Returns
    -------
    fields : list of str
        The model's own name for each field, in the order its variables
        appear in the dataset, without repeats
    """
    # raises for a model Polaris does not know about
    available_stats(model)
    stat_names = GLOBAL_STATS[model]

    fields = []
    for var_name in ds.data_vars:
        field = _field_name(
            var_name=str(var_name),
            stat_names=stat_names.values(),
            model=model,
            time_mean_period=time_mean_period,
        )
        if field is not None and field not in fields:
            fields.append(field)
    return fields


def select_global_stats(
    ds,
    fields,
    stats,
    model,
    field_map=None,
    time_mean_period=None,
    log=None,
    source='the global statistics output',
    hint=None,
):
    """
    Intersect the requested (field, statistic) pairs with what a dataset holds

    A simulation writes some subset of the fields and statistics that were
    asked for, and which subset is not something the person asking controls,
    so a pair that is absent is reported and dropped rather than raised on.
    A field with no surviving statistics is dropped entirely.  Only a dataset
    with *none* of the requested variables raises, since that is not a
    simulation writing a subset but a step reading the wrong thing.

    Parameters
    ----------
    ds : xarray.Dataset
        The global statistics, with the names the model gave them

    fields, model, field_map, time_mean_period
        As for :py:func:`global_stats_var_names`

    stats : list of str or None
        The statistics to look for, or ``None`` for every statistic this
        model computes

    log : callable, optional
        Where to report each pair that was dropped, typically
        ``step.logger.info``.  The default reports nothing.

    source : str, optional
        A short description of what was read, for the message when nothing
        was found

    hint : str, optional
        What to check when nothing was found, appended to that message

    Returns
    -------
    found : dict of str to dict of str to str
        The variable name of each statistic that is present, by field, in the
        order the fields and the statistics were given

    Raises
    ------
    ValueError
        If none of the requested variables is in ``ds``
    """
    if not stats:
        stats = available_stats(model)
    var_names = global_stats_var_names(
        fields=fields,
        stats=stats,
        model=model,
        field_map=field_map,
        time_mean_period=time_mean_period,
    )

    found: dict = {}
    for (field, stat), var_name in var_names.items():
        if var_name in ds:
            found.setdefault(field, {})[stat] = var_name
        elif log is not None:
            log(f'  no {var_name}: skipping the {stat} of {field}')

    if log is not None:
        for field in fields:
            if field not in found:
                log(f'  no statistics of {field} were written: skipping it')

    if not found:
        message = (
            f'None of the {len(var_names)} global statistics variables that '
            f'were asked for is in {source}.'
        )
        if hint is not None:
            message = f'{message}  {hint}'
        raise ValueError(message)

    return found


def _model_stats(model, stats):
    """Get a model's statistics, complaining about any it does not compute"""
    # raises for a model Polaris does not know about
    known = available_stats(model)

    unknown = [stat for stat in stats if stat not in known]
    if unknown:
        raise ValueError(
            f'{model} does not compute the global '
            f'{", ".join(unknown)} of a field.  The statistics it computes '
            f'are: {", ".join(known)}.'
        )
    return GLOBAL_STATS[model]


def _var_name(model_field, stat_name, model, time_mean_period):
    """Build one global statistics variable name"""
    if model == 'omega':
        name = f'{model_field}_{stat_name}'
        if time_mean_period is not None:
            name = f'{name}_TimeMean{time_mean_period}'
        return name
    return f'{model_field}{stat_name}'


def _field_name(var_name, stat_names, model, time_mean_period):
    """Get the field one global statistics variable is a statistic of"""
    if model == 'omega':
        suffix = (
            '' if time_mean_period is None else f'_TimeMean{time_mean_period}'
        )
        for stat_name in stat_names:
            ending = f'_{stat_name}{suffix}'
            if var_name.endswith(ending):
                return var_name[: -len(ending)]
        return None

    for stat_name in stat_names:
        if var_name.endswith(stat_name):
            return var_name[: -len(stat_name)]
    return None
