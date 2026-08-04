"""
Parse a dynamic-adjustment schedule YAML into a chain of
:py:class:`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage`
objects.

A stage is a forward run, so it starts from the ``[realistic_global_forward]``
config options -- including any per-mesh overrides -- and the schedule supplies
only what varies from stage to stage: the run duration, the time steps and
the Rayleigh damping.  The schedule is therefore a delta on the forward config
rather than a second configuration system, and options added to
``ForwardStage`` upstream reach the adjustment stages without any change here.

A schedule has a small ``shared`` block of per-stage defaults plus an ordered
``stages`` mapping.  Every key in either block must name a ``ForwardStage``
field, so a stale or misspelled key fails at setup rather than silently
reverting to a default; the fields the restart chain owns (``start_time``,
``do_restart``, ``restart_in``, ``restart_out``) are set here instead, from the
cumulative durations.
"""

import dataclasses
import datetime
import importlib.resources as imp_res
import typing
from typing import Any, Dict, List, Optional

from ruamel.yaml import YAML

from polaris.config import PolarisConfigParser
from polaris.mpas.time import duration_to_seconds
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage

PACKAGE = 'polaris.tasks.ocean.realistic_global.dynamic_adjustment'
DEFAULT_SCHEDULE = 'default.yaml'
SECTION = 'realistic_global_dynamic_adjustment'
FORWARD_SECTION = 'realistic_global_forward'

# MPAS-Ocean fires an output alarm at ``reference_time + n * interval``, and
# the restart stream's reference time is fixed at this value by the Registry
# (``Registry.xml``, the immutable ``restart`` stream).  It does not follow a
# stage's start time, so a stage's stop has to land on the alarm measured from
# here, not from where the stage began.
RESTART_REFERENCE_TIME = '0001-01-01_00:00:00'

# ForwardStage fields the restart chain owns, which a schedule may not set.
# ``start_time`` is the exception: it is accepted in the ``shared`` block as
# the origin of the chain, and each stage's own start time follows from it.
_CHAIN_FIELDS = frozenset(
    {'name', 'do_restart', 'restart_in', 'restart_out', 'start_time'}
)

# The fields a schedule may set, in ForwardStage declaration order.
SCHEDULE_FIELDS = tuple(
    field.name
    for field in dataclasses.fields(ForwardStage)
    if field.name not in _CHAIN_FIELDS
)

_TRUE_VALUES = frozenset({'true', 'yes', 'on', '1'})
_FALSE_VALUES = frozenset({'false', 'no', 'off', '0'})


def load_schedule_stages(
    mesh_name: str,
    config: PolarisConfigParser,
) -> List[ForwardStage]:
    """
    Build the ordered list of restart-chained stages for a mesh.

    Parameters
    ----------
    mesh_name : str
        The MPAS mesh name.  A ``<mesh_name>.yaml`` schedule in the package is
        used when present; otherwise the shared ``default.yaml`` is used.

    config : polaris.config.PolarisConfigParser
        The task config.  Each stage starts from its
        ``[realistic_global_forward]`` options, and a
        ``[realistic_global_dynamic_adjustment] schedule`` path overrides the
        built-in schedule.

    Returns
    -------
    list of ForwardStage
        One stage per entry in the schedule's ``stages`` block, with
        ``do_restart``, ``start_time``, ``restart_in`` and ``restart_out`` set
        so the stages form a restart chain.
    """
    options = _load_schedule(mesh_name, config)
    shared = dict(options.get('shared', {}))
    stages_dict = options['stages']

    # every stage is a forward run on this mesh; the schedule only says how
    # each one differs
    base = ForwardStage.from_config(config, section=FORWARD_SECTION)

    stages: List[ForwardStage] = []
    start_time = str(shared.pop('start_time', '0001-01-01_00:00:00'))
    _check_keys(shared, 'the shared block')
    restart_in: Optional[str] = None
    do_restart = False
    for name, stage_options in stages_dict.items():
        merged = _merge(shared, stage_options, name)
        run_duration = str(merged['run_duration'])
        stop = _advance(start_time, run_duration)
        stop_colons = _format_time(stop, ':')
        restart_out = f'restarts/rst.{_format_time(stop, ".")}.nc'
        stage = _build_stage(
            base=base,
            name=name,
            merged=merged,
            run_duration=run_duration,
            start_time=start_time,
            do_restart=do_restart,
            restart_in=restart_in,
            restart_out=restart_out,
        )
        _check_stage_writes_its_records(stage, stop)
        stages.append(stage)
        start_time = stop_colons
        restart_in = restart_out
        do_restart = True

    return stages


def excluded_days_in_stage(
    stage: ForwardStage,
    sequence_start: str,
    exclusion_duration: str,
) -> float:
    """
    How much of a stage falls inside the startup window of the sequence.

    The window over which the tracer extremes are not judged is measured from
    the start of the *sequence* rather than of each stage, because what it
    exists to skip belongs to the initial condition: the WOA23 source data
    carries a warm artifact off Sumatra and a salty one in the Red Sea, and on
    the finer meshes they need a couple of hours of mixing before they fall
    back to the values they then hold for the rest of the run.  A window
    measured from each stage would instead stop looking just after every
    damping change, which is where a schedule that steps the damping down too
    fast would show itself.

    Parameters
    ----------
    stage : polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage
        The stage in question.

    sequence_start : str
        The start time of the first stage, in MPAS ``YYYY-MM-DD_HH:MM:SS``
        form.

    exclusion_duration : str
        The length of the window, as an MPAS duration string.

    Returns
    -------
    float
        The number of days *into this stage* that lie within the window, and so
        0.0 for a stage beginning at or after the end of it.  Expressed
        relative to the stage because that is how a stage's own statistics
        measure time, whether or not the model restarted its clock.
    """
    window_days = duration_to_seconds(exclusion_duration) / 86400.0
    if window_days <= 0.0:
        return 0.0
    offset = _parse_time(stage.start_time) - _parse_time(sequence_start)
    return max(0.0, window_days - offset.total_seconds() / 86400.0)


def _check_stage_writes_its_records(
    stage: ForwardStage, stop: datetime.datetime
) -> None:
    """
    Raise unless the stage will actually write the records the chain needs.

    Two ways a schedule can look reasonable and produce nothing usable:

    * a ``restart_interval`` that does not put the stage's stop time on the
      restart alarm.  The stage declares ``restarts/rst.<stop>.nc`` as its
      output and the next stage reads it, so a miss is not a missing diagnostic
      but a broken chain -- discovered only after the model has already run.
      The alarm is measured from the stream's fixed reference time, so it is
      the elapsed time from there, not the stage's duration, that has to
      divide.
    * a ``stats_interval`` longer than the stage, which leaves the statistics
      with only the record written at startup, so the diagnostics summary
      reports the state the stage began from as its end-of-stage value.

    ``output_interval`` is deliberately not checked.  An interval longer than
    the stage is a legitimate way to say "do not write 3-D fields during the
    damped stages", which is what the ported Compass schedules do, and now that
    the diagnostics come from the statistics nothing depends on ``output.nc``
    having a final record.
    """
    restart_seconds = _interval_seconds(stage, 'restart_interval')
    elapsed = (stop - _parse_time(RESTART_REFERENCE_TIME)).total_seconds()
    if elapsed % restart_seconds != 0:
        raise ValueError(
            f'Stage {stage.name!r} ends at {_format_time(stop, ":")}, '
            f'which is '
            f'{elapsed:g} s after the restart reference time '
            f'{RESTART_REFERENCE_TIME} and not a whole number of its '
            f'{stage.restart_interval!r} restart intervals, so MPAS-Ocean '
            f'would never write the restart the next stage reads.  Choose a '
            f'restart_interval that divides {elapsed:g} s, or change the run '
            f'durations before this stage.'
        )

    duration = _interval_seconds(stage, 'run_duration')
    if _interval_seconds(stage, 'stats_interval') > duration:
        raise ValueError(
            f'Stage {stage.name!r} has stats_interval '
            f'{stage.stats_interval!r}, which is longer than its run_duration '
            f'{stage.run_duration!r}, so the statistics would hold only the '
            f'record written at startup and the diagnostics summary would '
            f"report the stage's starting state as its end-of-stage value."
        )


def _interval_seconds(stage: ForwardStage, option: str) -> float:
    """The number of seconds in one of a stage's duration options."""
    seconds = duration_to_seconds(getattr(stage, option))
    if seconds <= 0.0:
        raise ValueError(
            f'Stage {stage.name!r} has a non-positive {option} '
            f'{getattr(stage, option)!r}.'
        )
    return seconds


def _load_schedule(
    mesh_name: str, config: PolarisConfigParser
) -> Dict[str, Any]:
    """Read and validate the schedule mapping for a mesh."""
    text = _read_schedule_text(mesh_name, config)
    data = YAML(typ='rt').load(text)
    if not isinstance(data, dict) or 'dynamic_adjustment' not in data:
        raise ValueError(
            'A dynamic-adjustment schedule must start with '
            '"dynamic_adjustment:".'
        )
    options = data['dynamic_adjustment']
    if 'stages' not in options or not options['stages']:
        raise ValueError(
            'A dynamic-adjustment schedule must have a non-empty "stages:" '
            'block.'
        )
    return options


def _read_schedule_text(mesh_name: str, config: PolarisConfigParser) -> str:
    """The schedule YAML text, honoring a config path override."""
    if config.has_option(SECTION, 'schedule'):
        override = config.get(SECTION, 'schedule').strip()
        if override:
            with open(override) as schedule_file:
                return schedule_file.read()

    package_files = imp_res.files(PACKAGE)
    filename = f'{mesh_name}.yaml'
    if not package_files.joinpath(filename).is_file():
        filename = DEFAULT_SCHEDULE
    return package_files.joinpath(filename).read_text()


def _check_keys(options: Dict[str, Any], where: str) -> None:
    """
    Raise if any key does not name a ForwardStage field a schedule may set.

    A schedule that names a field which has been renamed or removed upstream
    would otherwise fall back to the config value without saying so, which is
    how the old ``time_integrator`` key went unnoticed when it was split in
    two.
    """
    unknown = [key for key in options if key not in SCHEDULE_FIELDS]
    if not unknown:
        return
    valid = ', '.join(SCHEDULE_FIELDS)
    raise ValueError(
        f'Unknown option(s) {", ".join(sorted(unknown))!s} in {where} of the '
        f'dynamic-adjustment schedule.  A schedule option must name a forward '
        f'run setting: {valid}.'
    )


def _merge(
    shared: Dict[str, Any], stage_options: Any, name: str
) -> Dict[str, Any]:
    """Merge the shared defaults with one stage's options."""
    if not isinstance(stage_options, dict):
        raise ValueError(
            f'Stage {name!r} in the dynamic-adjustment schedule must be a '
            f'mapping of options.'
        )
    _check_keys(dict(stage_options), f'stage {name!r}')
    merged = dict(shared)
    merged.update(stage_options)
    # the run duration drives the chain arithmetic, so it cannot come from
    # config; every other option falls back to [realistic_global_forward]
    if 'run_duration' not in merged:
        raise ValueError(
            f'Stage {name!r} in the dynamic-adjustment schedule is missing '
            f"required option 'run_duration'."
        )
    return merged


def _build_stage(
    base: ForwardStage,
    name: str,
    merged: Dict[str, Any],
    run_duration: str,
    start_time: str,
    do_restart: bool,
    restart_in: Optional[str],
    restart_out: str,
) -> ForwardStage:
    """
    Apply one merged stage mapping to ``base`` as a set of overrides.

    Every field the stage does not mention keeps its ``base`` value, which came
    from ``[realistic_global_forward]`` and the per-mesh config.
    """
    overrides = {key: _coerce(value, key) for key, value in merged.items()}
    # a stage writes the restart the next stage reads, so it has to write one
    # at the end of its own run rather than at the config's cadence
    overrides.setdefault('restart_interval', run_duration)
    return dataclasses.replace(
        base,
        name=name,
        do_restart=do_restart,
        start_time=start_time,
        restart_in=restart_in,
        restart_out=restart_out,
        **overrides,
    )


def _coerce(value: Any, key: str) -> Any:
    """
    Convert one YAML schedule value to the type of the ForwardStage field it
    sets, so that ``1.0e-4`` and ``'1.0e-4'`` mean the same thing and a blank
    value clears an optional field.
    """
    hint = _field_hints()[key]
    args = typing.get_args(hint)
    optional = type(None) in args
    target = next((arg for arg in args if arg is not type(None)), hint)
    text = '' if value is None else str(value).strip()
    if optional and not text:
        return None
    if target is bool:
        return _as_bool(text, key)
    if target is float:
        return float(text)
    return text


def _as_bool(text: str, key: str) -> bool:
    """A boolean schedule value, however YAML happened to render it."""
    lowered = text.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(
        f'Option {key!r} in the dynamic-adjustment schedule must be a '
        f'boolean, not {text!r}.'
    )


def _field_hints() -> Dict[str, Any]:
    """The resolved type hints of the ForwardStage fields, computed once."""
    global _FIELD_HINTS
    if _FIELD_HINTS is None:
        _FIELD_HINTS = typing.get_type_hints(ForwardStage)
    return _FIELD_HINTS


_FIELD_HINTS: Optional[Dict[str, Any]] = None


def _advance(start_time: str, run_duration: str) -> datetime.datetime:
    """The datetime ``start_time`` + ``run_duration``."""
    seconds = int(round(duration_to_seconds(run_duration)))
    return _parse_time(start_time) + datetime.timedelta(seconds=seconds)


def _parse_time(when: str) -> datetime.datetime:
    """Parse an MPAS-style ``YYYY-MM-DD_HH:MM:SS`` time."""
    return datetime.datetime.strptime(when, '%Y-%m-%d_%H:%M:%S')


def _format_time(when: datetime.datetime, time_sep: str) -> str:
    """
    Format a datetime as ``YYYY-MM-DD_HH<sep>MM<sep>SS`` with a four-digit
    year, using ``:`` for config times and ``.`` for restart filenames.
    """
    return (
        f'{when.year:04d}-{when.month:02d}-{when.day:02d}_'
        f'{when.hour:02d}{time_sep}{when.minute:02d}{time_sep}'
        f'{when.second:02d}'
    )
