from polaris import Step
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    collect_stage_diagnostics,
    log_summary,
    stage_stats_path,
    write_summary,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
    excluded_days_in_stage,
)

SUMMARY_FILENAME = 'dynamic_adjustment_stats.csv'


class Summary(Step):
    """
    A step that summarizes a completed dynamic-adjustment sequence as one row
    of diagnostics per stage (see
    :py:mod:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics`),
    written to ``dynamic_adjustment_stats.csv`` and logged as a table.

    It applies no checks of its own.  The thresholds live in
    :py:class:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.validate.StageCheck`,
    which runs as soon as its own stage finishes, so a stage that is already
    out of bounds stops the sequence rather than costing the whole job.
    Whether the adjustment has *settled* is a judgement read from this summary
    and the ``viz`` figure rather than from a threshold; see
    :py:mod:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.checks`
    for why the automated version of that judgement was removed.

    Diagnostics come from each stage's global-statistics file where the
    configured model reports them and from ``output.nc`` otherwise.  Both files
    are read with Omega's variable names mapped to the MPAS-Ocean ones the
    metrics are written in: ``output.nc`` through ``open_model_dataset`` and
    the statistics through
    :py:func:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics.open_stage_stats`.
    The baseline
    comparison of the final stage is handled separately by that forward step,
    which validates the ``'state'`` class of variables.

    One caveat the thresholds cannot express: Omega's temperature is
    conservative temperature where MPAS-Ocean's is potential temperature, and
    its salinity is absolute salinity where MPAS-Ocean's is practical
    salinity, so the bounds are not literally on the same quantities in the
    two models.  Against these thresholds the difference is immaterial.

    Attributes
    ----------
    stages : list of ForwardStage
        The stages of the adjustment, in schedule order.

    stage_names : list of str
        The stage subdirectory names, in schedule order.
    """

    def __init__(
        self, component, subdir, stages, min_res=None, mesh_target=None
    ):
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
            a per-day rate.

        min_res : float, optional
            The mesh minimum resolution in km, used for a per-kilometer Omega
            timestep.

        mesh_target : str, optional
            The static horizontal mesh file used for the Omega CFL estimate,
            relative to the base work directory.  It is linked into the step
            as ``mesh.nc``.
        """
        super().__init__(component=component, name='summary', subdir=subdir)
        self.stages = list(stages)
        self.stage_names = [stage.name for stage in self.stages]
        self.min_res = min_res
        self.mesh_filename = None
        if mesh_target is not None:
            self.add_input_file(
                filename='mesh.nc', work_dir_target=mesh_target
            )
            self.mesh_filename = 'mesh.nc'
        for stage_name in self.stage_names:
            self.add_input_file(
                filename=f'output_{stage_name}.nc',
                target=f'../{stage_name}/output.nc',
            )
        self.add_output_file(filename=SUMMARY_FILENAME)

    def run(self):
        """
        Summarize the sequence.
        """
        super().run()
        rows = self._collect()
        write_summary(SUMMARY_FILENAME, self.stage_names, rows)
        log_summary(self.logger, self.stage_names, rows)

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
                stats_filename=stage_stats_path(stage, model),
                output_filename=f'output_{stage.name}.nc',
                logger=self.logger,
                exclude_days=excluded_days_in_stage(
                    stage, sequence_start, exclusion
                ),
                min_res=self.min_res,
                mesh_filename=self.mesh_filename,
            )
            for stage in self.stages
        ]
