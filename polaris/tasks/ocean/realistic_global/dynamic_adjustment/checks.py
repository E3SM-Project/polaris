"""
The checks a dynamic-adjustment sequence is held to.

They live here rather than in a step because they are applied from two places:
the per-stage ``check`` steps, which run as soon as their stage finishes, and
the final ``validate`` step, which is the only place a cross-stage trend can be
assessed.

Each check takes values rather than datasets, so that the step decides what to
read and the check decides what is acceptable.
"""

from typing import Any, Optional, Sequence


def check_temperature_max(
    value: Optional[float],
    when: Optional[float],
    temperature_max: float,
    stage_name: str,
    logger: Any,
) -> None:
    """
    Raise if the stage's maximum temperature exceeds the threshold.

    Parameters
    ----------
    value : float or None
        The largest temperature reached at any point in the stage, not only at
        its end, so a blow-up the run recovered from is still caught.  ``None``
        means the model reported no temperature, and there is nothing to check.

    when : float or None
        The day, measured from the start of the stage, at which that maximum
        occurred.  Reported because it is what distinguishes a problem the run
        created from one it inherited: a maximum at day zero is the initial
        condition, before the model has taken a step.

    temperature_max : float
        The largest allowed temperature.

    stage_name : str
        The stage being checked.

    logger : logging.Logger
        A logger for the passing case.
    """
    _check_upper_bound(
        value=value,
        when=when,
        limit=temperature_max,
        stage_name=stage_name,
        quantity='temperature',
        units=' degC',
        logger=logger,
        consequence='it is above the threshold for numerical blow-up',
    )


def check_cfl_max(
    value: Optional[float],
    when: Optional[float],
    cfl_max: float,
    stage_name: str,
    logger: Any,
) -> None:
    """
    Raise if the stage went above the allowed CFL number at any point.

    A stability guard rather than a physical one, and it applies to every stage
    rather than to a trend: a schedule whose time step is too long for its
    stage shows up here before it shows up as a blow-up, and it stays caught
    even if the run happens to survive.

    ``value`` is ``None`` when the model reports no CFL number, which is the
    case for Omega.  See :py:func:`check_temperature_max` for the arguments.
    """
    _check_upper_bound(
        value=value,
        when=when,
        limit=cfl_max,
        stage_name=stage_name,
        quantity='CFL number',
        units='',
        logger=logger,
        consequence='its time step is too long for the flow it produced',
    )


def _check_upper_bound(
    value: Optional[float],
    when: Optional[float],
    limit: float,
    stage_name: str,
    quantity: str,
    units: str,
    logger: Any,
    consequence: str,
) -> None:
    """Raise if ``value`` is above ``limit``, saying when it got there."""
    if value is None:
        logger.info(
            f'Stage {stage_name!r}: no {quantity} reported; skipping that '
            f'check.'
        )
        return
    if value > limit:
        raise ValueError(
            f'Stage {stage_name!r}: {quantity} reached {value:.4g}{units}'
            f'{_at_day(when)}, above the allowed {limit:.4g}{units}; '
            f'{consequence}.'
        )
    logger.info(
        f'Stage {stage_name!r}: max {quantity} {value:.4g}{units}'
        f'{_at_day(when)} <= {limit:.4g}{units}.'
    )


def _at_day(when: Optional[float]) -> str:
    """
    Where in the stage an extreme occurred, phrased so that the initial
    condition is unmistakable.
    """
    if when is None:
        return ''
    if when <= 0.0:
        return ' at the start of the stage, before any time step'
    return f' {when:g} days into the stage'


def check_ke_growth_decelerates(
    stage_names: Sequence[str],
    mean_ke: Sequence[Optional[float]],
    ke_num: int,
    ke_tol: float,
    logger: Any,
) -> None:
    """
    Raise if the mean kinetic energy is changing faster stage over stage.

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
    reliably distinguishable.  The per-stage CFL and temperature thresholds are
    what guard against a run that is simply diverging.

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
        (stage_names[index], abs(mean_ke[index] / mean_ke[index - 1] - 1.0))  # type: ignore[operator]
        for index in range(1, len(mean_ke))
        if mean_ke[index - 1] > 0.0  # type: ignore[operator]
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
