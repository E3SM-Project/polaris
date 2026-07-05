"""
Parse a dynamic-adjustment schedule YAML into a chain of
:py:class:`~polaris.tasks.ocean.realistic_global.forward.stage.ForwardStage`
objects.

A schedule has a small ``shared`` block of per-stage defaults plus an ordered
``stages`` mapping.  Each stage key maps directly onto a ``ForwardStage``
field; this module only adds the restart chaining (cumulative start/stop times
and the shared restart filenames), so the parser stays a thin adapter rather
than a second configuration system.
"""

import datetime
import importlib.resources as imp_res
from typing import Any, Dict, List, Optional

from ruamel.yaml import YAML

from polaris.config import PolarisConfigParser
from polaris.mpas.time import duration_to_seconds
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage

PACKAGE = 'polaris.tasks.ocean.realistic_global.dynamic_adjustment'
DEFAULT_SCHEDULE = 'default.yaml'
SECTION = 'realistic_global_dynamic_adjustment'


def load_schedule_stages(
    mesh_name: str,
    config: Optional[PolarisConfigParser] = None,
) -> List[ForwardStage]:
    """
    Build the ordered list of restart-chained stages for a mesh.

    Parameters
    ----------
    mesh_name : str
        The MPAS mesh name.  A ``<mesh_name>.yaml`` schedule in the package is
        used when present; otherwise the shared ``default.yaml`` is used.

    config : polaris.config.PolarisConfigParser, optional
        The task config.  When it sets ``[realistic_global_dynamic_adjustment]
        schedule`` to a file path, that file overrides the built-in schedule.

    Returns
    -------
    list of ForwardStage
        One stage per entry in the schedule's ``stages`` block, with
        ``do_restart``, ``start_time``, ``restart_in`` and ``restart_out`` set
        so the stages form a restart chain.
    """
    options = _load_schedule(mesh_name, config)
    shared = options.get('shared', {})
    stages_dict = options['stages']

    stages: List[ForwardStage] = []
    start_time = str(shared.get('start_time', '0001-01-01_00:00:00'))
    restart_in: Optional[str] = None
    do_restart = False
    for name, stage_options in stages_dict.items():
        merged = _merge(shared, stage_options, name)
        run_duration = str(merged['run_duration'])
        stop = _advance(start_time, run_duration)
        stop_colons = _format_time(stop, ':')
        restart_out = f'restarts/rst.{_format_time(stop, ".")}.nc'
        stages.append(
            _build_stage(
                name=name,
                merged=merged,
                run_duration=run_duration,
                start_time=start_time,
                do_restart=do_restart,
                restart_in=restart_in,
                restart_out=restart_out,
            )
        )
        start_time = stop_colons
        restart_in = restart_out
        do_restart = True

    return stages


def _load_schedule(
    mesh_name: str, config: Optional[PolarisConfigParser]
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


def _read_schedule_text(
    mesh_name: str, config: Optional[PolarisConfigParser]
) -> str:
    """The schedule YAML text, honoring a config path override."""
    if config is not None and config.has_option(SECTION, 'schedule'):
        override = config.get(SECTION, 'schedule').strip()
        if override:
            with open(override) as schedule_file:
                return schedule_file.read()

    package_files = imp_res.files(PACKAGE)
    filename = f'{mesh_name}.yaml'
    if not package_files.joinpath(filename).is_file():
        filename = DEFAULT_SCHEDULE
    return package_files.joinpath(filename).read_text()


def _merge(
    shared: Dict[str, Any], stage_options: Any, name: str
) -> Dict[str, Any]:
    """Merge the shared defaults with one stage's options."""
    if not isinstance(stage_options, dict):
        raise ValueError(
            f'Stage {name!r} in the dynamic-adjustment schedule must be a '
            f'mapping of options.'
        )
    merged = dict(shared)
    merged.update(stage_options)
    for required in ('run_duration', 'output_interval'):
        if required not in merged:
            raise ValueError(
                f'Stage {name!r} in the dynamic-adjustment schedule is '
                f'missing required option {required!r}.'
            )
    return merged


def _build_stage(
    name: str,
    merged: Dict[str, Any],
    run_duration: str,
    start_time: str,
    do_restart: bool,
    restart_in: Optional[str],
    restart_out: str,
) -> ForwardStage:
    """Map one merged stage mapping onto a ForwardStage."""
    restart_interval = merged.get('restart_interval', run_duration)
    return ForwardStage(
        name=name,
        run_duration=run_duration,
        output_interval=str(merged['output_interval']),
        restart_interval=str(restart_interval),
        time_integrator=str(
            merged.get('time_integrator', 'split_explicit_ab2')
        ),
        dt=_opt_str(merged, 'dt'),
        btr_dt=_opt_str(merged, 'btr_dt'),
        dt_per_km=_opt_float(merged, 'dt_per_km'),
        btr_dt_per_km=_opt_float(merged, 'btr_dt_per_km'),
        damping=_opt_float(merged, 'damping'),
        do_restart=do_restart,
        start_time=start_time,
        restart_in=restart_in,
        restart_out=restart_out,
    )


def _advance(start_time: str, run_duration: str) -> datetime.datetime:
    """The datetime ``start_time`` + ``run_duration``."""
    start = datetime.datetime.strptime(start_time, '%Y-%m-%d_%H:%M:%S')
    seconds = int(round(duration_to_seconds(run_duration)))
    return start + datetime.timedelta(seconds=seconds)


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


def _opt_str(merged: Dict[str, Any], key: str) -> Optional[str]:
    """A string option, or ``None`` when absent or blank."""
    if key not in merged or merged[key] is None:
        return None
    value = str(merged[key]).strip()
    return value or None


def _opt_float(merged: Dict[str, Any], key: str) -> Optional[float]:
    """A float option, or ``None`` when absent or blank."""
    if key not in merged or merged[key] is None:
        return None
    value = str(merged[key]).strip()
    return float(value) if value else None
