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

# Map from the ``hmix_scaling`` config option to the MPAS-Ocean flags it sets.
#
# MPAS-Ocean spells this as two booleans, and they are *nested* rather than
# independent (``ocn_meshScaling`` in ``mpas_ocn_mesh.F``)::
#
#     if (config_hmix_scaleWithMesh) then
#        if (config_hmix_use_ref_cell_width) then
#           ! scale by (cellWidth / config_hmix_ref_cell_width)**n
#        else
#           ! scale by the meshDensity field
#     else
#        ! no scaling: meshScaling = 1 everywhere
#
# So ``config_hmix_use_ref_cell_width`` is read *only* when
# ``config_hmix_scaleWithMesh`` is true.  Setting the former without the latter
# reads as a request for width-based scaling and silently gets none, which is
# why ``ref_cell_width`` here sets both.
#
# The meshDensity branch is deliberately not offered.  ``meshDensity`` is a
# legacy field holding ``(cellWidthMin / cellWidth)**4``, and E3SM v4 meshes --
# including every mesh Polaris builds -- write it as uniformly 1.0, which makes
# that branch a no-op as well.  Mixing that is to follow resolution has to go
# through ``ref_cell_width``.
_HMIX_SCALING_FLAGS: Dict[str, Dict[str, bool]] = {
    'none': {
        'config_hmix_scaleWithMesh': False,
        'config_hmix_use_ref_cell_width': False,
    },
    'ref_cell_width': {
        'config_hmix_scaleWithMesh': True,
        'config_hmix_use_ref_cell_width': True,
    },
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

    stats_interval : str
        The interval between writes of the global statistics, which is
        deliberately separate from ``output_interval``: the statistics are a
        handful of scalars, so they can be written far more often than the 3-D
        output and are what makes an excursion within a stage visible.
        MPAS-Ocean only -- Omega's ``GlobalStats`` reduction period is baked
        into the variable names that ``mpaso_to_omega`` maps, so its statistics
        stay daily.

    mpaso_time_integrator : str
        The time integrator to use for MPAS-Ocean.

    omega_time_integrator : str
        The time integrator to use for Omega, in neutral (MPAS-Ocean) naming;
        it is translated to the Omega name in
        :py:meth:`model_replacements`.

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

    mom_del2 : float or None
        The harmonic momentum viscosity (m^2/s); ``None`` turns it off.

    mom_del4 : float or None
        The biharmonic momentum viscosity (m^4/s); ``None`` turns it off.

    mom_del4_div_factor : float or None
        A factor applied to the divergence part of the biharmonic momentum
        operator alone, leaving the rotational part at ``mom_del4``; ``None``
        leaves the model default of 1.0, the true biharmonic.

    tracer_del2 : float or None
        The harmonic tracer diffusivity (m^2/s); ``None`` turns it off.

    tracer_del4 : float or None
        The biharmonic tracer diffusivity (m^4/s); ``None`` turns it off.

    use_Leith_del2 : bool
        Whether to use the Leith closure for harmonic momentum mixing.

    hmix_scaling : str
        How horizontal mixing coefficients are scaled across the mesh; either
        ``'none'`` or ``'ref_cell_width'``.

    hmix_ref_cell_width : float or None
        The reference cell width (m), used only when ``hmix_scaling`` is
        ``'ref_cell_width'``.  The ``del2`` coefficients then apply at this
        width and scale as ``cellWidth``, and the ``del4`` ones as
        ``cellWidth**3``.

    use_GM : bool
        Whether to use the Gent-McWilliams eddy transport parameterization.

    GM_closure : str or None
        The GM closure; ``None`` leaves the model default.

    GM_constant_kappa : float or None
        The constant GM kappa (m^2/s); ``None`` leaves the model default.

    use_Redi : bool
        Whether to use Redi isopycnal mixing.

    use_frazil_ice_formation : bool
        Whether to form frazil ice.

    do_restart : bool
        Whether the run continues from an existing restart.

    start_time : str
        The simulation start time.

    restart_in : str or None
        The restart file to continue from when ``do_restart`` is ``True``, as a
        path relative to the task work directory (e.g.
        ``restarts/rst.0001-01-11_00.00.00.nc``).  The forward step declares it
        as an input, and the model reaches it through the restart stream's
        ``filename_template`` at ``start_time``; there is no separate
        restart-pointer file.

    restart_out : str or None
        The restart file this stage produces for the next stage, as a path
        relative to the task work directory.  When set, the forward step writes
        restarts to the shared ``restarts`` directory and declares this file as
        an output so the chain is inspectable.
    """

    name: str = 'forward'
    run_duration: str = '0001_00:00:00'
    output_interval: str = '0001_00:00:00'
    restart_interval: str = '0001_00:00:00'
    stats_interval: str = '0001_00:00:00'
    mpaso_time_integrator: str = 'split_explicit_ab2'
    omega_time_integrator: str = 'RK4'
    dt: Optional[str] = None
    btr_dt: Optional[str] = None
    dt_per_km: Optional[float] = None
    btr_dt_per_km: Optional[float] = None
    damping: Optional[float] = None
    mom_del2: Optional[float] = None
    mom_del4: Optional[float] = None
    mom_del4_div_factor: Optional[float] = None
    tracer_del2: Optional[float] = None
    tracer_del4: Optional[float] = None
    use_Leith_del2: bool = False
    hmix_scaling: str = 'none'
    hmix_ref_cell_width: Optional[float] = None
    use_GM: bool = False
    GM_closure: Optional[str] = None
    GM_constant_kappa: Optional[float] = None
    use_Redi: bool = False
    use_frazil_ice_formation: bool = False
    do_restart: bool = False
    start_time: str = '0001-01-01_00:00:00'
    restart_in: Optional[str] = None
    restart_out: Optional[str] = None

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
            stats_interval=config.get(section, 'stats_interval').strip(),
            mpaso_time_integrator=config.get(
                section, 'mpaso_time_integrator'
            ).strip(),
            omega_time_integrator=config.get(
                section, 'omega_time_integrator'
            ).strip(),
            dt=_opt_str(config, section, 'dt'),
            btr_dt=_opt_str(config, section, 'btr_dt'),
            dt_per_km=_opt_float(config, section, 'dt_per_km'),
            btr_dt_per_km=_opt_float(config, section, 'btr_dt_per_km'),
            damping=_opt_float(config, section, 'damping'),
            mom_del2=_opt_float(config, section, 'mom_del2'),
            mom_del4=_opt_float(config, section, 'mom_del4'),
            mom_del4_div_factor=_opt_float(
                config, section, 'mom_del4_div_factor'
            ),
            tracer_del2=_opt_float(config, section, 'tracer_del2'),
            tracer_del4=_opt_float(config, section, 'tracer_del4'),
            use_Leith_del2=config.getboolean(section, 'use_Leith_del2'),
            hmix_scaling=_hmix_scaling(config, section),
            hmix_ref_cell_width=_opt_float(
                config, section, 'hmix_ref_cell_width'
            ),
            use_GM=config.getboolean(section, 'use_GM'),
            GM_closure=_opt_str(config, section, 'GM_closure'),
            GM_constant_kappa=_opt_float(config, section, 'GM_constant_kappa'),
            use_Redi=config.getboolean(section, 'use_Redi'),
            use_frazil_ice_formation=config.getboolean(
                section, 'use_frazil_ice_formation'
            ),
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

        The time integrator is the one setting that is chosen per model rather
        than shared, since the two models do not currently support the same
        integrators; see ``mpaso_time_integrator`` and
        ``omega_time_integrator``.  The time step follows from that choice, so
        the two models can also end up with different time steps.

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
        if model == 'omega':
            time_integrator = self.omega_time_integrator
        else:
            time_integrator = self.mpaso_time_integrator
        if time_integrator in _SPLIT_TIME_INTEGRATORS:
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
        if model == 'omega':
            if time_integrator in _OMEGA_TIME_INTEGRATORS:
                time_integrator = _OMEGA_TIME_INTEGRATORS[time_integrator]
            elif not at_setup:
                # only an error at run time; at setup the user may still change
                # the config option to a supported integrator before running
                supported = ', '.join(sorted(_OMEGA_TIME_INTEGRATORS))
                raise ValueError(
                    f'omega_time_integrator {time_integrator!r} is not '
                    f'supported for Omega; supported integrators are: '
                    f'{supported}.'
                )
        output_freq = int(round(duration_to_seconds(self.output_interval)))
        stats_freq = int(round(duration_to_seconds(self.stats_interval)))
        restart_freq = int(round(duration_to_seconds(self.restart_interval)))
        return dict(
            run_duration=self.run_duration,
            output_interval=self.output_interval,
            restart_interval=self.restart_interval,
            stats_interval=self.stats_interval,
            output_freq=str(output_freq),
            restart_freq=str(restart_freq),
            stats_freq=str(stats_freq),
            dt=dt,
            btr_dt=btr_dt,
            time_integrator=time_integrator,
            start_time=self.start_time,
            do_restart='true' if self.do_restart else 'false',
        )

    def check_damping_supported(self, model: str) -> None:
        """
        Raise when the configured model cannot honor this stage's damping.

        Omega has no Rayleigh damping
        (https://github.com/E3SM-Project/Omega/issues/495), and
        ``config_Rayleigh_damping_coeff`` has no counterpart in
        ``mpaso_to_omega``, so a damped stage would run undamped with nothing
        said.  For a staged adjustment that is not a small difference in a
        low-level control: the ramp is the whole purpose of the damped stages,
        and dropping it silently would make a run look adjusted when it is not.

        A stage with no damping -- the final ``simulation`` stage, and every
        stage of a simple forward run -- is unaffected.

        Parameters
        ----------
        model : str
            The configured ocean model, ``'mpas-ocean'`` or ``'omega'``.

        Raises
        ------
        ValueError
            If ``damping`` is set and ``model`` is Omega.
        """
        if self.damping is None or model != 'omega':
            return
        raise ValueError(
            f'Stage {self.name!r} sets Rayleigh damping '
            f'({self.damping:g} 1/s), which Omega does not support; see '
            f'https://github.com/E3SM-Project/Omega/issues/495.  Run this '
            f'stage with MPAS-Ocean, or drop "damping" from the schedule to '
            f'run it undamped.'
        )

    def bottom_drag_options(self) -> Dict[str, Any]:
        """
        MPAS-Ocean bottom-drag config options implied by the damping setting.

        When ``damping`` is set, this turns Rayleigh damping on with that
        coefficient.  When it is not, the coefficient is set to zero rather
        than left at the MPAS-Ocean Registry default of 1.0e-4: the default is
        unused, because ``forward.yaml`` pins the drag type to ``constant``,
        but a namelist that says ``config_Rayleigh_damping_coeff = 1.0e-4``
        reads as though the run were damped.  An undamped stage should look
        undamped.

        Applied by the forward step for MPAS-Ocean only, because Omega has no
        Rayleigh damping; :py:meth:`check_damping_supported` is what keeps that
        from being a silent omission.

        Returns
        -------
        dict
            The MPAS-Ocean config options to add.
        """
        if self.damping is None:
            return {'config_Rayleigh_damping_coeff': 0.0}
        return {
            'config_implicit_bottom_drag_type': 'constant_and_rayleigh',
            'config_Rayleigh_damping_coeff': self.damping,
        }

    def restart_stream_replacements(self) -> Dict[str, str]:
        """
        Template replacements for ``restart_streams.yaml``.

        MPAS-Ocean needs nothing here -- its restart stream is both an input
        and an output stream, so ``config_do_restart`` and
        ``config_start_time`` from ``forward.yaml`` already drive the read
        side.  Omega reads through a separate ``RestartRead`` stream that has
        to be switched off for the first stage, which is what these express:
        a stage that is not restarting reads its state from ``InitialState``
        instead, and ``RestartRead`` is pushed out of the way with a start time
        it will never reach.

        Returns
        -------
        dict of str
            The template replacements for ``restart_streams.yaml``.
        """
        if self.do_restart:
            return dict(
                init_freq_units='never',
                restart_read_use_start_end='false',
                restart_read_time=self.start_time,
            )
        return dict(
            init_freq_units='OnStartup',
            restart_read_use_start_end='true',
            restart_read_time='99999-12-31_00:00:00',
        )

    def horiz_mixing_options(self) -> Dict[str, Any]:
        """
        Horizontal mixing options that both models support.

        These are given in MPAS-Ocean naming and applied with
        ``config_model='ocean'``, so that they are translated to Omega by
        ``mpaso_to_omega``.  A coefficient of ``None`` turns its term off
        rather than leaving the model default, so that the config is the only
        thing deciding whether a term is active.

        Returns
        -------
        dict
            The model config options to add.
        """
        options: Dict[str, Any] = {}
        for coeff, use_option, coeff_option in [
            (self.mom_del2, 'config_use_mom_del2', 'config_mom_del2'),
            (self.mom_del4, 'config_use_mom_del4', 'config_mom_del4'),
            (self.tracer_del2, 'config_use_tracer_del2', 'config_tracer_del2'),
            (self.tracer_del4, 'config_use_tracer_del4', 'config_tracer_del4'),
        ]:
            options[use_option] = coeff is not None
            if coeff is not None:
                options[coeff_option] = coeff
        return options

    def mpaso_physics_options(self) -> Dict[str, Any]:
        """
        Physics options that only MPAS-Ocean has.

        The Leith closure, the horizontal-mixing scaling, the del4 divergence
        factor, Gent-McWilliams, Redi and frazil ice have no Omega equivalent,
        and GM and Redi are not expected to gain one, so these are applied with
        ``config_model='mpas-ocean'``.

        Returns
        -------
        dict
            The MPAS-Ocean config options to add.
        """
        options: Dict[str, Any] = {
            'config_use_Leith_del2': self.use_Leith_del2,
            'config_use_GM': self.use_GM,
            'config_use_Redi': self.use_Redi,
            'config_use_frazil_ice_formation': self.use_frazil_ice_formation,
        }

        _check_hmix_scaling(self.hmix_scaling)
        # both flags every time, so that turning scaling off in a user config
        # undoes a per-mesh config that turned it on
        options.update(_HMIX_SCALING_FLAGS[self.hmix_scaling])
        if (
            self.hmix_scaling == 'ref_cell_width'
            and self.hmix_ref_cell_width is not None
        ):
            options['config_hmix_ref_cell_width'] = self.hmix_ref_cell_width

        if self.mom_del4_div_factor is not None:
            options['config_mom_del4_div_factor'] = self.mom_del4_div_factor

        if self.use_GM:
            if self.GM_closure is not None:
                options['config_GM_closure'] = self.GM_closure
            if self.GM_constant_kappa is not None:
                options['config_GM_constant_kappa'] = self.GM_constant_kappa
        return options


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


def _hmix_scaling(config: PolarisConfigParser, section: str) -> str:
    """Read and validate the ``hmix_scaling`` option."""
    value = config.get(section, 'hmix_scaling').strip()
    _check_hmix_scaling(value)
    return value


def _check_hmix_scaling(value: str) -> None:
    """Raise unless ``value`` names a supported ``hmix_scaling``."""
    if value in _HMIX_SCALING_FLAGS:
        return
    valid = ', '.join(sorted(_HMIX_SCALING_FLAGS))
    raise ValueError(
        f'Unknown hmix_scaling {value!r}; valid options are: {valid}.'
    )


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
