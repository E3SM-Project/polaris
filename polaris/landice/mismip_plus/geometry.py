"""
The constants and bed topography of MISMIP+, from Sect. 2.1 and Table 1 of
`Asay-Davis et al. (2016) <https://doi.org/10.5194/gmd-9-2471-2016>`_
"""

import numpy as np

# the protocol's year in s, which its rates per year are converted with
SECONDS_PER_YEAR = 31556926.0

# MALI's 365-day year in s, in which MALI and Albany express velocities
MALI_SECONDS_PER_YEAR = 365.0 * 86400.0

# the length and width of the domain in m
DOMAIN_LENGTH = 640.0e3
DOMAIN_WIDTH = 80.0e3

# the position in m beyond which ice is removed
CALVING_X = 640.0e3

# the densities of ice and seawater in kg m^-3
ICE_DENSITY = 918.0
OCEAN_DENSITY = 1028.0

# the rate factor in Glen's law in Pa^-3 s^-1
FLOW_PARAM_A = 6.338e-25

# the coefficient (Pa m^-1/3 s^1/3) and exponent of the power friction law
FRICTION_COEFFICIENT = 3.160e6
FRICTION_EXPONENT = 1.0 / 3.0

# the accumulation rate in m a^-1 of ice
ACCUMULATION_RATE = 0.3

# the melt rate in m a^-1 of ice in Ice2, and where it starts in m
ICE2_MELT_RATE = 100.0
ICE2_MELT_X_MIN = 480.0e3


def bed_topography(x, y):
    """
    Compute the bed topography of MISMIP+ (Eqs. 1-4)

    Parameters
    ----------
    x : numpy.ndarray or xarray.DataArray
        The x coordinate in m

    y : numpy.ndarray or xarray.DataArray
        The y coordinate in m, with the channel's center at 40 km

    Returns
    -------
    bed : numpy.ndarray or xarray.DataArray
        The bed elevation in m
    """
    # the parameters from Table 1, in m
    b0 = -150.0
    b2 = -728.8
    b4 = 343.91
    b6 = -50.57
    x_bar = 300.0e3
    trough_depth = 500.0
    wall_width = 4.0e3
    trough_half_width = 24.0e3
    bed_max_depth = -720.0

    x_tilde = x / x_bar
    bed_x = b0 + b2 * x_tilde**2 + b4 * x_tilde**4 + b6 * x_tilde**6

    y_offset = y - 0.5 * DOMAIN_WIDTH
    bed_y = trough_depth / (
        1.0 + np.exp(-2.0 * (y_offset - trough_half_width) / wall_width)
    ) + trough_depth / (
        1.0 + np.exp(2.0 * (y_offset + trough_half_width) / wall_width)
    )

    return np.maximum(bed_x + bed_y, bed_max_depth)
