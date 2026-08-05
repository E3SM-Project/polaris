import os

from polaris import Step
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.checks import (
    check_cfl_max,
    check_ke_growth_decelerates,
    check_salinity_max,
    check_temperature_max,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    collect_stage_diagnostics,
    extreme_and_day,
    log_summary,
    stage_stats_path,
    write_summary,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
    excluded_days_in_stage,
)

SUMMARY_FILENAME = 'dynamic_adjustment_stats.csv'


class Validate(Step):
    """
    A step that summarizes a completed dynamic-adjustment sequence and applies
    the one check no single stage can make: that the stage-over-stage change in
    the mean kinetic energy is shrinking.

    The per-stage thresholds live in :py:class:`StageCheck`, which runs as soon
    as its own stage finishes.

    The step first builds one row of diagnostics per stage (see
    :py:mod:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics`)
    and writes it to ``dynamic_adjustment_stats.csv``.  Those rows are what the
    checks are then made against, so the summary a user reads and the checks
    that passed or failed cannot disagree.

    Diagnostics come from each stage's global-statistics file where the
    configured model reports them and from ``output.nc`` otherwise.  Both files
    are read through ``open_model_dataset``, so Omega's variable names are
    mapped to the MPAS-Ocean ones the metrics are written in.  The baseline
    comparison of the final stage is handled separately by that forward step's
    ``validate_vars``.

    One caveat the threshold cannot express: Omega's temperature is
    conservative temperature where MPAS-Ocean's is potential temperature, so
    ``temperature_max`` is not literally the same quantity in the two models.
    Against a blow-up threshold the difference is immaterial.

    Attributes
    ----------
    stages : list of ForwardStage
        The stages of the adjustment, in schedule order.

    stage_names : list of str
        The stage subdirectory names, in schedule order.
    """

    def __init__(self, component, subdir, stages):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        stages : list of ForwardStage
            The stages of the adjustment, in schedule order.  The stages
            themselves are needed, rather than just their names, because a
            stage's run duration is what turns a change across the stage into
            a per-day drift rate.
        """
        super().__init__(component=component, name='validate', subdir=subdir)
        self.stages = list(stages)
        self.stage_names = [stage.name for stage in self.stages]
        for stage_name in self.stage_names:
            self.add_input_file(
                filename=f'output_{stage_name}.nc',
                target=f'../{stage_name}/output.nc',
            )
        self.add_output_file(filename=SUMMARY_FILENAME)

    def run(self):
        """
        Summarize the sequence, then check it against the summary.
        """
        super().run()
        config = self.config
        logger = self.logger

        rows = self._collect()
        write_summary(SUMMARY_FILENAME, self.stage_names, rows)
        log_summary(logger, self.stage_names, rows)

        ke_num = config.getint(SECTION, 'ke_check_num_stages')
        ke_tol = config.getfloat(SECTION, 'ke_check_rel_tolerance')

        # the per-stage thresholds have already been applied by each stage's
        # own check step, which is what makes a bad first stage fail in
        # minutes rather than after the whole sequence has run.  What is left
        # is the one thing no single stage can see.
        mean_ke = [row['kinetic_energy_mean'] for row in rows]
        check_ke_growth_decelerates(
            self.stage_names, mean_ke, ke_num, ke_tol, logger
        )

    def _collect(self):
        """
        One row of diagnostics per stage.

        The global-statistics file is looked up by path rather than declared as
        a step input, so that a stage which did not write one (or wrote one
        this Polaris cannot read) degrades to computing what it can from
        ``output.nc`` instead of failing the whole step.
        """
        config = self.config
        model = config.get('ocean', 'model')
        # the same window the stage checks used, so the summary a user reads
        # and the checks that passed cannot disagree
        sequence_start = self.stages[0].start_time
        exclusion = config.get(SECTION, 'startup_exclusion_duration').strip()
        return [
            collect_stage_diagnostics(
                component=self.component,
                config=config,
                stage=stage,
                stats_filename=stage_stats_path(stage.name, model),
                output_filename=f'output_{stage.name}.nc',
                logger=self.logger,
                exclude_days=excluded_days_in_stage(
                    stage, sequence_start, exclusion
                ),
            )
            for stage in self.stages
        ]


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
        self, component, subdir, stage, sequence_start='0001-01-01_00:00:00'
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
        """
        super().__init__(
            component=component, name=f'{stage.name}_check', subdir=subdir
        )
        self.stage = stage
        self.sequence_start = sequence_start

    def run(self):
        """
        Check this stage's tracer and CFL extremes.
        """
        super().run()
        config = self.config
        logger = self.logger
        stage_name = self.stage.name

        model = config.get('ocean', 'model')
        path = stage_stats_path(stage_name, model)
        if path is None or not os.path.exists(path):
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

        ds = self.component.open_model_dataset(path, config)
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
