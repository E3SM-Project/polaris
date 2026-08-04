from polaris import Step
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.diagnostics import (  # noqa: E501
    collect_stage_diagnostics,
    log_summary,
    stage_stats_path,
    write_summary,
)
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
)

SUMMARY_FILENAME = 'dynamic_adjustment_stats.csv'


class Validate(Step):
    """
    A step that summarizes a completed dynamic-adjustment sequence and checks
    it for obvious failures: a per-stage maximum-temperature threshold
    (numerical blow-up) and a "settling" heuristic that the maximum cell
    kinetic energy is not increasing over the last several stages.

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

    def __init__(self, component, stages, indir):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        stages : list of ForwardStage
            The stages of the adjustment, in schedule order.  The stages
            themselves are needed, rather than just their names, because a
            stage's run duration is what turns a change across the stage into
            a per-day drift rate.

        indir : str
            The directory the step is in, to which ``validate`` is appended.
        """
        super().__init__(component=component, name='validate', indir=indir)
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

        temperature_max = config.getfloat(SECTION, 'temperature_max')
        ke_num = config.getint(SECTION, 'ke_check_num_stages')
        ke_tol = config.getfloat(SECTION, 'ke_check_rel_tolerance')

        for stage_name, row in zip(self.stage_names, rows, strict=False):
            _check_temperature_max(
                row['temperature_max_in_stage'],
                temperature_max,
                stage_name,
                logger,
            )

        max_ke = [row['kinetic_energy_max'] for row in rows]
        _check_ke_flattening(self.stage_names, max_ke, ke_num, ke_tol, logger)

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
        return [
            collect_stage_diagnostics(
                component=self.component,
                config=config,
                stage=stage,
                stats_filename=stage_stats_path(stage.name, model),
                output_filename=f'output_{stage.name}.nc',
                logger=self.logger,
            )
            for stage in self.stages
        ]


def _check_temperature_max(value, temperature_max, stage_name, logger):
    """
    Raise if the stage's maximum temperature exceeds the threshold.

    ``value`` is the largest temperature reached at any point in the stage, not
    only at its end, so a blow-up that the stage recovered from is still
    caught.  ``None`` means the model reported no temperature at all, in which
    case there is nothing to check.
    """
    if value is None:
        logger.info(
            f'Stage {stage_name!r}: no temperature reported; skipping the '
            f'maximum-temperature check.'
        )
        return
    if value > temperature_max:
        raise ValueError(
            f'Stage {stage_name!r}: maximum temperature {value:.2f} exceeds '
            f'the allowed {temperature_max:.2f}.'
        )
    logger.info(
        f'Stage {stage_name!r}: max temperature {value:.2f} <= '
        f'{temperature_max:.2f}.'
    )


def _check_ke_flattening(stage_names, max_ke, ke_num, ke_tol, logger):
    """
    Raise if the maximum cell kinetic energy increases by more than ``ke_tol``
    (a fraction) between any two of the last ``ke_num`` stages.  Skipped when
    there are fewer than ``ke_num`` stages (e.g. the coarse default schedule),
    since a single damped-to-undamped transition is not a meaningful trend, and
    when any of those stages did not report a kinetic energy.
    """
    if len(stage_names) < ke_num:
        logger.info(
            f'Fewer than {ke_num} stages; skipping the kinetic-energy '
            f'flattening check.'
        )
        return
    tail_names = stage_names[-ke_num:]
    tail_ke = max_ke[-ke_num:]
    if any(value is None for value in tail_ke):
        logger.info(
            'Kinetic energy was not reported for every stage; skipping the '
            'flattening check.'
        )
        return
    for index in range(1, len(tail_ke)):
        previous = tail_ke[index - 1]
        current = tail_ke[index]
        if previous > 0.0 and current > previous * (1.0 + ke_tol):
            raise ValueError(
                f'Stage {tail_names[index]!r}: maximum cell kinetic energy '
                f'{current:.3e} increased by more than {ke_tol:.1%} over the '
                f'previous stage ({previous:.3e}); the adjustment is not '
                f'settling.'
            )
    logger.info(
        f'Maximum cell kinetic energy is flattening over the last {ke_num} '
        f'stages ({tail_ke[0]:.3e} -> {tail_ke[-1]:.3e}).'
    )
