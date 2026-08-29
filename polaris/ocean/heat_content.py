r"""
Ocean heat content, as a mass-weighted integral of conservative temperature.

Over an elevation range, heat content per unit area is

.. math::
    Q = c_p^0 \int \rho \, \Theta \, dz
      \approx c_p^0 \sum_k \Theta_k \, m_k

where :math:`m_k` is the mass per unit area of the part of layer :math:`k`
within the range, from
:py:func:`polaris.ocean.vertical.elevation.elevation_range_weights`.

Weighting by mass rather than by a geometric thickness times a reference
density is what makes the reference density drop out of the answer.  For a
range covering whole layers, :math:`m_k` is the layer's mass exactly --- for
Omega by the definition of pseudo-height, for MPAS-Ocean because it is
Boussinesq --- so the in-situ-versus-reference density error of a few tenths
of a percent that a volume integral carries is not made here at all.

This module is deliberately dependency-light, so that the same kernel serves
the heat content maps, which integrate a climatology, and the heat content
time series, which integrates a month at a time.
"""

import xarray as xr


def heat_content(temperature, weights, specific_heat):
    r"""
    Get the vertically integrated ocean heat content per unit area

    Parameters
    ----------
    temperature : xarray.DataArray
        Conservative temperature in degC, with an ``nVertLevels`` dimension.
        Because Omega carries conservative temperature, :math:`c_p^0 \Theta`
        is potential enthalpy per unit mass by the definition of TEOS-10, so
        the integral below is heat content rather than an approximation to
        it.

    weights : xarray.DataArray
        The mass per unit area of the part of each layer that is being
        integrated over, in kg m-2, zero outside it

    specific_heat : float
        The specific heat capacity of seawater in J kg-1 K-1

    Returns
    -------
    da : xarray.DataArray
        The heat content per unit area in J m-2, without an ``nVertLevels``
        dimension, masked where the column holds no mass within the range
    """
    # a layer that weighs nothing contributes nothing, whatever the model
    # wrote for its temperature: below the seafloor that may be a fill value,
    # which arrives as NaN and would otherwise poison the sum
    weighted = xr.where(weights > 0.0, temperature * weights, 0.0)
    total_weight = weights.sum('nVertLevels', skipna=False)

    # summing without skipping missing values is what keeps the line above
    # from being a way of hiding one.  A layer that weighs nothing is already
    # zero, so the only NaN left to propagate is a temperature that is
    # missing where there is mass, which is a broken input and not a hole in
    # the ocean.
    integral = weighted.sum('nVertLevels', skipna=False)

    # a column with no mass in the range has no heat content to report rather
    # than a heat content of zero, so it is masked.  A global integral sums
    # over the mask and is unaffected, while a map shows a hole where there
    # is nothing to show.
    da = (specific_heat * integral).where(total_weight > 0.0)
    da = da.rename('heat_content')
    da.attrs = dict(
        units='J m-2',
        long_name='vertically integrated ocean heat content per unit area',
    )
    return da
