from dataclasses import dataclass
from typing import Any, Dict, Optional

from polaris.config import PolarisConfigParser
from polaris.mpas.time import duration_to_seconds, get_time_interval_string

# Map from the neutral (MPAS-Ocean) time-integrator names to the Omega names.
# Only integrators with an Omega equivalent appear here; a neutral name that is
# absent (e.g. ``split_explicit_ab2``) is not yet supported for Omega.  A
# split-explicit integrator for Omega is in development.
_OMEGA_TIME_INTEGRATORS = {
    'RK4': 'RungeKutta4',
}

# Integrators that use split (barotropic/baroclinic) time stepping.  These use
# the long ``dt_per_km`` baroclinic step for ``config_dt`` and the short
# ``btr_dt_per_km`` step for ``config_btr_dt``.  Every other integrator (e.g.
# RK4 / Omega's RungeKutta4) has no barotropic subcycling and must advance on
# the short barotropic step.
_SPLIT_TIME_INTEGRATORS = {
    'split_explicit_ab2',
}


@dataclass
class ForwardStage:
    """
    Model-agnostic settings for a single realistic-global forward run (or one
    stage of a multi-stage workflow such as dynamic adjustment).

    A simple forward run builds one of these from a
    ``[realistic_global_forward]`` config section via :py:meth:`from_config`.
    Future workflows (restart tests, dynamic adjustment) build a sequence of
    them and set the restart-in fields to chain runs.

    Attributes
    ----------
    name : str
        A name for the stage.

    run_duration : str
        The run duration as an MPAS-style duration string
        (``DDDD_HH:MM:SS``).

    output_interval : str
        The interval between writes to the output stream.

    restart_interval : str
        The interval between writes to the restart stream.

    time_integrator : str
        The time integrator, in neutral (MPAS-Ocean) naming.

    dt : str or None
        An explicit baroclinic time step; when ``None`` it is derived from
        ``dt_per_km`` and the mesh minimum resolution.

    btr_dt : str or None
        An explicit barotropic time step; when ``None`` it is derived from
        ``btr_dt_per_km`` and the mesh minimum resolution.

    dt_per_km : float or None
        The baroclinic time step per km of minimum resolution (s/km).

    btr_dt_per_km : float or None
        The barotropic time step per km of minimum resolution (s/km).

    damping : float or None
        A Rayleigh damping coefficient (1/s); ``None`` disables Rayleigh
        damping.

    do_restart : bool
        Whether the run continues from an existing restart.

    start_time : str
        The simulation start time.

    restart_in : str or None
        The restart file to continue from when ``do_restart`` is ``True``.
    """

    name: str = 'forward'
    run_duration: str = '0001_00:00:00'
    output_interval: str = '0001_00:00:00'
    restart_interval: str = '0001_00:00:00'
    time_integrator: str = 'split_explicit_ab2'
    dt: Optional[str] = None
    btr_dt: Optional[str] = None
    dt_per_km: Optional[float] = None
    btr_dt_per_km: Optional[float] = None
    damping: Optional[float] = None
    do_restart: bool = False
    start_time: str = '0001-01-01_00:00:00'
    restart_in: Optional[str] = None

    @classmethod
    def from_config(
        cls,
        config: PolarisConfigParser,
        name: str = 'forward',
        section: str = 'realistic_global_forward',
    ) -> 'ForwardStage':
        """
        Build a stage from a config section.

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            The config options containing ``section``.

        name : str, optional
            A name for the stage.

        section : str, optional
            The config section to read the settings from.

        Returns
        -------
        ForwardStage
            The settings read from config.
        """
        run_duration = config.get(section, 'run_duration').strip()
        restart_interval = _opt_str(config, section, 'restart_interval')
        if restart_interval is None:
            restart_interval = run_duration
        return cls(
            name=name,
            run_duration=run_duration,
            output_interval=config.get(section, 'output_interval').strip(),
            restart_interval=restart_interval,
            time_integrator=config.get(section, 'time_integrator').strip(),
            dt=_opt_str(config, section, 'dt'),
            btr_dt=_opt_str(config, section, 'btr_dt'),
            dt_per_km=_opt_float(config, section, 'dt_per_km'),
            btr_dt_per_km=_opt_float(config, section, 'btr_dt_per_km'),
            damping=_opt_float(config, section, 'Rayleigh_damping_coeff'),
            start_time=config.get(section, 'start_time').strip(),
        )

    def model_replacements(
        self, model: str, min_res: float, at_setup: bool = False
    ) -> Dict[str, str]:
        """
        Map the stage onto template replacements for ``forward.yaml``.

        This is the single place where model-agnostic settings become
        model-facing values.  The neutral values (run duration, time step,
        time integrator) are auto-translated to Omega by ``mpaso_to_omega``;
        only the time-integrator name is mapped here because its value differs.

        Parameters
        ----------
        model : str
            The configured ocean model, ``'mpas-ocean'`` or ``'omega'``.

        min_res : float
            The mesh minimum resolution in km, used to derive the time step
            from ``dt_per_km``/``btr_dt_per_km`` when it is not explicit.

        at_setup : bool, optional
            Whether the replacements are being built during setup, as opposed
            to at run time.  An unsupported time integrator is only an error at
            run time, so that a user can set the step up and change the config
            option before running.

        Returns
        -------
        dict of str
            The template replacements for ``forward.yaml``.
        """
        if self.time_integrator in _SPLIT_TIME_INTEGRATORS:
            # split time stepping: a long baroclinic step (config_dt) and a
            # short barotropic subcycling step (config_btr_dt)
            dt = _time_step_string(
                self.dt, self.dt_per_km, min_res, 'dt_per_km'
            )
            btr_dt = _time_step_string(
                self.btr_dt, self.btr_dt_per_km, min_res, 'btr_dt_per_km'
            )
        else:
            # non-split integrators (RK4, Omega RungeKutta4) have no
            # barotropic subcycling and must advance on the short barotropic
            # time step; config_btr_dt is unused, so mirror config_dt into it
            dt = _time_step_string(
                self.dt, self.btr_dt_per_km, min_res, 'btr_dt_per_km'
            )
            btr_dt = self.btr_dt if self.btr_dt is not None else dt
        time_integrator = self.time_integrator
        if model == 'omega':
            if time_integrator in _OMEGA_TIME_INTEGRATORS:
                time_integrator = _OMEGA_TIME_INTEGRATORS[time_integrator]
            elif not at_setup:
                # only an error at run time; at setup the user may still change
                # the config option to a supported integrator before running
                supported = ', '.join(sorted(_OMEGA_TIME_INTEGRATORS))
                raise ValueError(
                    f'Time integrator {time_integrator!r} is not supported '
                    f'for Omega; supported integrators are: {supported}.'
                )
        output_freq = int(round(duration_to_seconds(self.output_interval)))
        restart_freq = int(round(duration_to_seconds(self.restart_interval)))
        return dict(
            run_duration=self.run_duration,
            output_interval=self.output_interval,
            restart_interval=self.restart_interval,
            output_freq=str(output_freq),
            restart_freq=str(restart_freq),
            dt=dt,
            btr_dt=btr_dt,
            time_integrator=time_integrator,
            start_time=self.start_time,
            do_restart='true' if self.do_restart else 'false',
        )

    def bottom_drag_options(self) -> Dict[str, Any]:
        """
        MPAS-Ocean bottom-drag config options implied by the damping setting.

        Returns Rayleigh damping options when ``damping`` is set, and an empty
        dict otherwise so the model default is left untouched.  Applied by the
        forward step for MPAS-Ocean only; an Omega equivalent is a future hook.

        Returns
        -------
        dict
            The MPAS-Ocean config options to add, possibly empty.
        """
        if self.damping is None:
            return {}
        return {
            'config_implicit_bottom_drag_type': 'constant_and_rayleigh',
            'config_Rayleigh_damping_coeff': self.damping,
        }


def _time_step_string(
    explicit: Optional[str],
    per_km: Optional[float],
    min_res: float,
    name: str,
) -> str:
    """The explicit time step if set, else ``per_km * min_res`` as a string."""
    if explicit is not None:
        return explicit
    if per_km is None:
        raise ValueError(f'Set an explicit time step or {name} on the stage')
    return get_time_interval_string(seconds=per_km * min_res)


def _opt_str(
    config: PolarisConfigParser, section: str, option: str
) -> Optional[str]:
    """Read a config option, returning ``None`` when it is blank."""
    value = config.get(section, option).strip()
    return value or None


def _opt_float(
    config: PolarisConfigParser, section: str, option: str
) -> Optional[float]:
    """Read a float config option, returning ``None`` when it is blank."""
    value = config.get(section, option).strip()
    return float(value) if value else None
