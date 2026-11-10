MONTH_ABBREVIATIONS = (
    'jan',
    'feb',
    'mar',
    'apr',
    'may',
    'jun',
    'jul',
    'aug',
    'sep',
    'oct',
    'nov',
    'dec',
)


def get_woa23_month(config):
    """
    Get the month of the WOA23 monthly climatology to use.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with a ``[woa23]`` section.

    Returns
    -------
    month : int
        The month, from 1 (January) to 12 (December).
    """
    month = config.getint('woa23', 'month')
    if month < 1 or month > 12:
        raise ValueError(
            f'[woa23] month must be between 1 and 12, got {month}.'
        )
    return month


def get_month_abbreviation(month):
    """
    Get the lowercase three-letter abbreviation for a month.

    Parameters
    ----------
    month : int
        The month, from 1 (January) to 12 (December).

    Returns
    -------
    abbreviation : str
        The abbreviation, e.g. ``'oct'`` for 10.
    """
    return MONTH_ABBREVIATIONS[month - 1]
