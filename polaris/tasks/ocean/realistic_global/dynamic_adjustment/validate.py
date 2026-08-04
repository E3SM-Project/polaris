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
    it for obvious failures: per-stage maximum-temperature and CFL thresholds,
    and a "settling" heuristic that the stage-over-stage growth of the mean
    kinetic energy is decelerating.

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
        cfl_max = config.getfloat(SECTION, 'cfl_max')
        ke_num = config.getint(SECTION, 'ke_check_num_stages')
        ke_tol = config.getfloat(SECTION, 'ke_check_rel_tolerance')

        for stage_name, row in zip(self.stage_names, rows, strict=False):
            _check_temperature_max(
                row['temperature_max_in_stage'],
                temperature_max,
                stage_name,
                logger,
            )
            _check_cfl_max(
                row['cfl_max_in_stage'], cfl_max, stage_name, logger
            )

        mean_ke = [row['kinetic_energy_mean'] for row in rows]
        _check_ke_growth_decelerates(
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


def _check_cfl_max(value, cfl_max, stage_name, logger):
    """
    Raise if the stage went above the allowed CFL number at any point.

    This is a stability guard rather than a physical one, and it applies to
    every stage rather than to a trend: a schedule whose time step is too long
    for its stage shows up here before it shows up as a blow-up, and it stays
    caught even if the run happens to survive.  ``value`` is the largest CFL
    reached at any point in the stage.

    ``None`` means the model reports no CFL number, which is the case for
    Omega, and there is nothing to check.
    """
    if value is None:
        logger.info(
            f'Stage {stage_name!r}: no CFL number reported; skipping the '
            f'CFL check.'
        )
        return
    if value > cfl_max:
        raise ValueError(
            f'Stage {stage_name!r}: CFL number reached {value:.3f}, above the '
            f'allowed {cfl_max:.3f}; its time step is too long for the flow '
            f'it produced.'
        )
    logger.info(f'Stage {stage_name!r}: max CFL {value:.3f} <= {cfl_max:.3f}.')


def _check_ke_growth_decelerates(stage_names, mean_ke, ke_num, ke_tol, logger):
    """
    Raise if the mean kinetic energy is growing faster stage over stage.

    An earlier version of this required the kinetic energy itself not to
    increase.  That is the wrong thing to ask of a run that starts from rest
    under wind forcing: the circulation spins up, so kinetic energy rises for
    tens of days for reasons that have nothing to do with the fast waves the
    adjustment exists to remove, and the check failed on a healthy run.

    What settling means for a forced spin-up is that the change is slowing --
    each stage moves the mean kinetic energy proportionally less than the one
    before.  So the quantity checked is the *fractional* change from stage to
    stage, ``|KE_n / KE_(n-1) - 1|``, which must be non-increasing to within
    ``ke_tol``.  Taking the magnitude matters: a run converging from above has
    ratios rising towards one and a run converging from below has them falling
    towards one, and both are settling.

    The mean, rather than the maximum, because the maximum is dominated by the
    transient released whenever the damping steps down, which decays within the
    stage and says nothing about the trend.

    What this does not catch: a perfectly constant growth rate passes, since
    its fractional change never increases.  The check detects acceleration
    rather than growth, which is the most that can be asked of three or four
    stages -- over a span this short, an asymptote and a straight line are not
    reliably distinguishable.  The CFL and temperature thresholds are what
    guard against a run that is simply diverging.

    Skipped when fewer than three stages reported a mean kinetic energy, since
    two changes are the fewest that can show a trend, and when the configured
    model reports no mean kinetic energy at all (Omega).
    """
    if any(value is None for value in mean_ke):
        logger.info(
            'Mean kinetic energy was not reported for every stage; skipping '
            'the settling check.'
        )
        return
    changes = [
        (stage_names[index], abs(mean_ke[index] / mean_ke[index - 1] - 1.0))
        for index in range(1, len(mean_ke))
        if mean_ke[index - 1] > 0.0
    ]
    if len(changes) < 2:
        logger.info(
            'Fewer than three stages with a mean kinetic energy; skipping the '
            'settling check.'
        )
        return

    tail = changes[-ke_num:]
    for index in range(1, len(tail)):
        previous_name, previous = tail[index - 1]
        name, current = tail[index]
        if current > previous * (1.0 + ke_tol):
            raise ValueError(
                f'Stage {name!r}: the mean kinetic energy changed by '
                f'{current:.1%} from the previous stage, more than the '
                f'{previous:.1%} it changed across {previous_name!r}; the '
                f'adjustment is not settling.'
            )
    trend = ' -> '.join(f'{change:.1%}' for _, change in tail)
    logger.info(
        f'The change in mean kinetic energy is shrinking over the last '
        f'{len(tail)} stage transitions ({trend}).'
    )
