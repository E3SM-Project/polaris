"""
The checks a dynamic-adjustment sequence is held to.

They live here rather than in a step because a step decides what to read and
a check decides what is acceptable.  All of them are per-stage, applied by the
``check`` steps that run as soon as their stage finishes.

There is deliberately no cross-stage "is it settling yet" check.  One existed
and was rewritten three times -- comparing kinetic-energy levels, then the
fractional change stage over stage, then that change per unit time -- and every
revision was forced by a healthy run failing it.  It was inferring a trend from
three points, over stages of unequal length, across the moment the Rayleigh
damping is switched off; none of those are comparable.  Whether an adjustment
has settled is read from the ``viz`` figure and the diagnostics table, which
show the whole series rather than three samples of it.  What is left here are
bounds on quantities with real failure modes behind them.

Each check takes values rather than datasets, so that the step decides what to
read and the check decides what is acceptable.
"""

from typing import Any, Optional


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
        occurred.  Reported because where in a stage an extreme sits is most of
        the diagnosis.  The caller is expected to have excluded the sample
        written before the first time step, which describes what the stage was
        handed rather than what it did, along with any part of the stage inside
        the sequence's startup window.

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


def check_salinity_max(
    value: Optional[float],
    when: Optional[float],
    salinity_max: float,
    stage_name: str,
    logger: Any,
) -> None:
    """
    Raise if the stage's maximum salinity exceeds the threshold.

    The companion to :py:func:`check_temperature_max`, and for the same reason:
    a runaway shows up in the tracer extremes before it shows up anywhere else.
    Salinity earns its own check rather than riding on temperature because the
    two fail independently -- the WOA23 source data carries a warm artifact off
    Sumatra and a salty one in the Red Sea, in different places.

    See :py:func:`check_temperature_max` for the arguments.
    """
    _check_upper_bound(
        value=value,
        when=when,
        limit=salinity_max,
        stage_name=stage_name,
        quantity='salinity',
        units=' PSU',
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
