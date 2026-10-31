import os

from polaris import Step
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.checks import (
    check_cfl_max,
    check_salinity_max,
    check_temperature_max,
    check_temperature_min,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    _CFL_VELOCITY_STATS,
    estimate_cfl_from_stats,
    extreme_and_day,
    open_stage_stats,
    stage_stats_path,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
    excluded_days_in_stage,
)


class StageCheck(Step):
    """
    A step that applies the per-stage thresholds to one stage, as soon as that
    stage has finished.

    Running the whole sequence and only then discovering that the first stage
    was already out of bounds wastes most of a job; on the finer meshes that is
    hours.  So each stage gets its own check, and the sequence stops at the
    stage that broke.

    It is a separate step rather than something the forward step does after the
    model exits: an MPI step should not carry Python work afterwards, which
    would hold the model's whole allocation open to compare a few scalars.

    The checks report *when* an extreme occurred as well as how large it was,
    because that is what separates a problem the stage created from one it
    inherited -- an extreme at day zero is the initial condition, before the
    model has taken a step.

    Attributes
    ----------
    stage : ForwardStage
        The stage being checked.

    sequence_start : str
        The start time of the first stage, from which the startup window is
        measured.
    """

    def __init__(
        self,
        component,
        subdir,
        stage,
        sequence_start='0001-01-01_00:00:00',
        min_res=None,
        mesh_target=None,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stage : ForwardStage
            The stage whose statistics are checked.

        sequence_start : str, optional
            The start time of the first stage of the adjustment.  The startup
            window is measured from here rather than from this stage, so a
            stage knows how much of the window it is covered by.  The default
            matches ``ForwardStage.start_time``, which is where a
            single-stage sequence begins.

        min_res : float, optional
            The mesh minimum resolution in km, used for a per-kilometer Omega
            timestep.

        mesh_target : str, optional
            The static horizontal mesh file used for the Omega CFL estimate,
            relative to the base work directory.  It is linked into the step
            as ``mesh.nc``.
        """
        super().__init__(
            component=component, name=f'{stage.name}_check', subdir=subdir
        )
        self.stage = stage
        self.sequence_start = sequence_start
        self.min_res = min_res
        self.mesh_filename = None
        if mesh_target is not None:
            self.add_input_file(
                filename='mesh.nc', work_dir_target=mesh_target
            )
            self.mesh_filename = 'mesh.nc'

    def run(self):
        """
        Check this stage's tracer and CFL extremes.
        """
        super().run()
        config = self.config
        logger = self.logger
        stage_name = self.stage.name

        model = config.get('ocean', 'model')
        path = stage_stats_path(self.stage, model)
        if not os.path.exists(path):
            logger.info(
                f'Stage {stage_name!r} wrote no global statistics; skipping '
                f'its checks.'
            )
            return

        exclude_days = excluded_days_in_stage(
            self.stage,
            self.sequence_start,
            config.get(SECTION, 'startup_exclusion_duration').strip(),
        )
        if exclude_days > 0.0:
            logger.info(
                f'Stage {stage_name!r}: its first {exclude_days:g} day(s) are '
                f'inside the startup window, so the tracer extremes there are '
                f'not checked.'
            )

        ds = open_stage_stats(self.component, path, config)
        with ds:
            temperature, when = extreme_and_day(
                ds, 'temperatureMax', 'max', exclude_days
            )
            check_temperature_max(
                temperature,
                when,
                config.getfloat(SECTION, 'temperature_max'),
                stage_name,
                logger,
            )
            temperature, when = extreme_and_day(
                ds, 'temperatureMin', 'min', exclude_days
            )
            check_temperature_min(
                temperature,
                when,
                config.getfloat(SECTION, 'temperature_min'),
                stage_name,
                logger,
            )
            salinity, when = extreme_and_day(
                ds, 'salinityMax', 'max', exclude_days
            )
            check_salinity_max(
                salinity,
                when,
                config.getfloat(SECTION, 'salinity_max'),
                stage_name,
                logger,
            )
            # deliberately not given the startup window: the opening hours are
            # where a time step that is too long shows itself
            cfl, when = extreme_and_day(ds, 'CFLNumberGlobal', 'max')
            check_cfl_max(
                cfl,
                when,
                config.getfloat(SECTION, 'cfl_max'),
                stage_name,
                logger,
            )
            if model == 'omega':
                if any(name not in ds for name in _CFL_VELOCITY_STATS):
                    logger.info(
                        f'Stage {stage_name!r}: normal-velocity extrema are '
                        'not available; skipping the conservative CFL '
                        'estimate.'
                    )
                elif self.min_res is None or self.mesh_filename is None:
                    raise ValueError(
                        'The Omega CFL estimate requires the mesh minimum '
                        'resolution and horizontal mesh filename.'
                    )
                else:
                    cfl_estimate = estimate_cfl_from_stats(
                        component=self.component,
                        config=config,
                        ds_stats=ds,
                        stage=self.stage,
                        min_res=self.min_res,
                        mesh_filename=self.mesh_filename,
                    )
                    if cfl_estimate is not None:
                        logger.info(
                            f'Stage {stage_name!r}: conservative '
                            f'Polaris-only horizontal CFL estimate '
                            f'{cfl_estimate:.4g} (not threshold-checked).'
                        )
