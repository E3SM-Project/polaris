"""
Jerlov water-type optical properties and their Omega equivalents.

MPAS-Ocean absorbs shortwave radiation with the two-band Jerlov scheme in
``mpas_ocn_tracer_short_wave_absorption_jerlov.F``::

    w(z) = rfac * exp(-z / depth1) + (1 - rfac) * exp(-z / depth2)

Omega instead uses the three-band Manizza et al. (2005) form in
``PenetratingShortwaveOnCell`` (``TendencyTerms.h``)::

    w(z) = NearIrFraction * exp(-NearIrCoeff * z)
         + RedFraction    * exp(-Kr * z)
         + BlueFraction   * exp(-Kb * z)

the two are identical when the near-infrared band carries the Jerlov
``rfac`` and the red and blue bands together carry the remainder with a
common extinction coefficient, which is what
:py:func:`omega_jerlov_equivalent` returns.
"""

import numpy as np

# Jerlov water type:      I     IA    IB    II    III
JERLOV_WATER_TYPES = {
    1: 'I',
    2: 'IA',
    3: 'IB',
    4: 'II',
    5: 'III',
}

JERLOV_RFAC = {1: 0.58, 2: 0.62, 3: 0.67, 4: 0.77, 5: 0.78}

JERLOV_DEPTH1 = {1: 0.35, 2: 0.60, 3: 1.00, 4: 1.50, 5: 1.40}

JERLOV_DEPTH2 = {1: 23.0, 2: 20.0, 3: 17.0, 4: 14.0, 5: 7.90}

# The Manizza band fractions Omega defaults to, used to split the visible
# fraction between the red and blue bands in the same proportion.
MANIZZA_RED_FRACTION = 0.21
MANIZZA_BLUE_FRACTION = 0.21


def omega_jerlov_equivalent(water_type):
    """
    Get the Omega band parameters that reproduce an MPAS-Ocean Jerlov water
    type

    The visible fraction ``1 - rfac`` is split between the red and blue bands
    in the Manizza proportion.  Both bands are given the same extinction
    coefficient, so the split does not affect the absorption profile.

    Parameters
    ----------
    water_type : int
        The Jerlov water type, between 1 (I) and 5 (III)

    Returns
    -------
    options : dict
        The ``NearIrFraction``, ``NearIrCoeff``, ``RedFraction`` and
        ``BlueFraction`` config options for Omega's
        ``Tendencies:PenetratingShortwaveTendency`` section

    extinction_coeff : float
        The extinction coefficient to use for both the red and blue bands
        in 1/m
    """
    _validate_water_type(water_type)
    rfac = JERLOV_RFAC[water_type]
    visible_fraction = 1.0 - rfac
    manizza_visible = MANIZZA_RED_FRACTION + MANIZZA_BLUE_FRACTION
    options = {
        'NearIrFraction': rfac,
        'NearIrCoeff': 1.0 / JERLOV_DEPTH1[water_type],
        'RedFraction': (
            visible_fraction * MANIZZA_RED_FRACTION / manizza_visible
        ),
        'BlueFraction': (
            visible_fraction * MANIZZA_BLUE_FRACTION / manizza_visible
        ),
    }
    return options, 1.0 / JERLOV_DEPTH2[water_type]


def manizza_scale(water_type):
    """
    Get the factor that scales the reference Manizza extinction coefficients
    to a given Jerlov water type

    The reference coefficients describe the clearest water (type I), so they
    are scaled by the ratio of visible extinction coefficients,
    ``depth2(I) / depth2(water_type)``.  Scaling both bands preserves their
    ratio, so the red and blue bands stay distinct as the water grows more
    turbid.

    Parameters
    ----------
    water_type : int
        The Jerlov water type, between 1 (I) and 5 (III)

    Returns
    -------
    scale : float
        The factor to apply to the reference red and blue extinction
        coefficients
    """
    _validate_water_type(water_type)
    return JERLOV_DEPTH2[1] / JERLOV_DEPTH2[water_type]


def jerlov_absorption_fraction(depth, water_type):
    """
    Compute the MPAS-Ocean two-band Jerlov absorption fraction

    Parameters
    ----------
    depth : numpy.ndarray
        The depth below the surface in m, positive down

    water_type : int
        The Jerlov water type, between 1 (I) and 5 (III)

    Returns
    -------
    fraction : numpy.ndarray
        The fraction of the incident shortwave flux reaching each depth
    """
    _validate_water_type(water_type)
    rfac = JERLOV_RFAC[water_type]
    fraction = rfac * np.exp(-depth / JERLOV_DEPTH1[water_type]) + (
        1.0 - rfac
    ) * np.exp(-depth / JERLOV_DEPTH2[water_type])
    # MPAS-Ocean truncates the profile below 200 m
    return np.where(depth > 200.0, 0.0, fraction)


def manizza_absorption_fraction(
    depth,
    near_ir_fraction,
    near_ir_coeff,
    red_fraction,
    blue_fraction,
    extinction_coeff_red,
    extinction_coeff_blue,
):
    """
    Compute Omega's three-band absorption fraction

    Parameters
    ----------
    depth : numpy.ndarray
        The depth below the surface in m, positive down

    near_ir_fraction : float
        The fraction of the incident flux in the near-infrared band

    near_ir_coeff : float
        The near-infrared extinction coefficient in 1/m

    red_fraction : float
        The fraction of the incident flux in the red band

    blue_fraction : float
        The fraction of the incident flux in the blue band

    extinction_coeff_red : float
        The red-band extinction coefficient in 1/m

    extinction_coeff_blue : float
        The blue-band extinction coefficient in 1/m

    Returns
    -------
    fraction : numpy.ndarray
        The fraction of the incident shortwave flux reaching each depth
    """
    depth = np.asarray(depth, dtype=float)
    if not np.all(np.isfinite(depth)) or np.any(depth < 0.0):
        raise ValueError('Depth must be finite and nonnegative')
    validate_manizza_parameters(
        near_ir_fraction=near_ir_fraction,
        near_ir_coeff=near_ir_coeff,
        red_fraction=red_fraction,
        blue_fraction=blue_fraction,
        extinction_coeff_red=extinction_coeff_red,
        extinction_coeff_blue=extinction_coeff_blue,
    )
    return (
        near_ir_fraction * np.exp(-near_ir_coeff * depth)
        + red_fraction * np.exp(-extinction_coeff_red * depth)
        + blue_fraction * np.exp(-extinction_coeff_blue * depth)
    )


def validate_manizza_parameters(
    near_ir_fraction,
    near_ir_coeff,
    red_fraction,
    blue_fraction,
    extinction_coeff_red,
    extinction_coeff_blue,
):
    """Validate fractions and extinction coefficients for Manizza optics."""
    fractions = np.asarray(
        [near_ir_fraction, red_fraction, blue_fraction], dtype=float
    )
    coefficients = np.asarray(
        [near_ir_coeff, extinction_coeff_red, extinction_coeff_blue],
        dtype=float,
    )
    if not np.all(np.isfinite(fractions)):
        raise ValueError('Manizza band fractions must be finite')
    if np.any((fractions < 0.0) | (fractions > 1.0)):
        raise ValueError('Manizza band fractions must be between 0 and 1')
    if not np.isclose(fractions.sum(), 1.0, rtol=0.0, atol=1.0e-12):
        raise ValueError('Manizza band fractions must sum to one')
    if not np.all(np.isfinite(coefficients)):
        raise ValueError('Manizza extinction coefficients must be finite')
    if np.any(coefficients < 0.0):
        raise ValueError('Manizza extinction coefficients must be nonnegative')


def _validate_water_type(water_type):
    if water_type not in JERLOV_WATER_TYPES:
        raise ValueError(
            f'Unknown Jerlov water type {water_type}; expected one of '
            f'{sorted(JERLOV_WATER_TYPES)}'
        )
