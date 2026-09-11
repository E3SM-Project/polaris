"""
Reference-state expansion of the equation of state, shared across the edge.

This is §3.3 of ``PGradHighOrder.md``.  The finite-volume pressure gradient
never integrates TEOS-10; it expands specific volume to first order about a
reference state, ``[alpha-taylor]``,

.. math::

    \\hat\\alpha(\\Theta, S, p) = \\alpha_0
    + \\alpha_\\Theta (\\Theta - \\Theta_{\\rm ref})
    + \\alpha_S (S - S_{\\rm ref})
    + \\alpha_p (p - p_{\\rm ref}),

so that :math:`\\hat\\alpha` is a low-order polynomial in pressure once
:math:`\\Theta` and :math:`S` are reconstructed as polynomials in pressure, and
every integral the scheme needs is available in closed form.

**The expansion point is shared across the edge** (§3.3.1, ``[edge-ref]``).
The four coefficients are computed once per cell per layer at that cell's own
state and are then averaged to the edge, together with the reference state
itself, and *both* columns are evaluated with the single resulting set.  If
instead each column expanded about its own state, the two would be using two
different approximations to the same equation of state; their specific-volume
profiles would disagree even for a resting ocean the reconstruction reproduces
perfectly, and the scheme would generate spurious flow from nothing but its own
equation of state.  Under the reduced target of §3.2 this is the *only*
remaining way for exactness to fail on a resolved profile, so it is
load-bearing rather than a refinement.

Note on cost: Requirement 2.2 bounds the number of TEOS-10 *calls*, and the
design's claim is that one evaluation yields all four coefficients because the
derivatives are analytic derivatives of the same polynomial at the same
normalized state.  The Python here necessarily makes two calls, because
``gsw.specvol_first_derivatives`` returns the derivatives without the value.
That is a limitation of the Python bindings and says nothing about Omega's call
count; do not read this module as evidence about cost.
"""

import gsw
import numpy as np
import xarray as xr

from polaris.tasks.ocean.horiz_press_grad.edge import edge_mean

__all__ = [
    'specvol_coefficients',
    'edge_expansion',
    'edge_specvol',
    'edge_specvol_layer_mean',
]

# gsw takes pressure in dbar and returns the pressure derivative of specific
# volume per Pa -- the convention of neither argument.  Asserted in
# tests/ocean/horiz_press_grad/test_eos_expansion.py rather than trusted.
_PA_TO_DBAR = 1.0e-4


def specvol_coefficients(
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    pressure: xr.DataArray,
) -> xr.Dataset:
    """
    The four coefficients of ``[alpha-derivs]``, evaluated at each cell's own
    layer-mean state.

    Parameters
    ----------
    temperature : xarray.DataArray
        Conservative temperature in degC.  Invalid layers may be ``NaN`` and
        stay ``NaN``.

    salinity : xarray.DataArray
        Absolute salinity in g kg-1, on the same points.

    pressure : xarray.DataArray
        Sea gauge pressure in **Pa**, on the same points.  This module follows
        the rest of Polaris in using Pa, and converts to dbar at the ``gsw``
        call.

    Returns
    -------
    coefficients : xarray.Dataset
        ``alpha_0`` (m3 kg-1), ``alpha_theta`` (m3 kg-1 degC-1), ``alpha_s``
        (m3 kg-1 / (g kg-1)) and ``alpha_p`` (m3 kg-1 Pa-1), on the dims of the
        inputs.
    """
    conservative_temperature = np.asarray(temperature.values, dtype=float)
    absolute_salinity = np.asarray(salinity.values, dtype=float)
    pressure_pa = np.asarray(pressure.values, dtype=float)

    if not (
        conservative_temperature.shape
        == absolute_salinity.shape
        == pressure_pa.shape
    ):
        raise ValueError(
            'temperature, salinity and pressure must have the same shape; got '
            f'{conservative_temperature.shape}, {absolute_salinity.shape} and '
            f'{pressure_pa.shape}.'
        )

    valid = (
        np.isfinite(conservative_temperature)
        & np.isfinite(absolute_salinity)
        & np.isfinite(pressure_pa)
    )

    coefficients = {
        name: np.full(conservative_temperature.shape, np.nan)
        for name in ['alpha_0', 'alpha_theta', 'alpha_s', 'alpha_p']
    }

    if np.any(valid):
        pressure_dbar = pressure_pa[valid] * _PA_TO_DBAR
        coefficients['alpha_0'][valid] = gsw.specvol(
            absolute_salinity[valid],
            conservative_temperature[valid],
            pressure_dbar,
        )
        alpha_s, alpha_theta, alpha_p = gsw.specvol_first_derivatives(
            absolute_salinity[valid],
            conservative_temperature[valid],
            pressure_dbar,
        )
        coefficients['alpha_theta'][valid] = alpha_theta
        coefficients['alpha_s'][valid] = alpha_s
        coefficients['alpha_p'][valid] = alpha_p

    units = {
        'alpha_0': 'm3 kg-1',
        'alpha_theta': 'm3 kg-1 degC-1',
        'alpha_s': 'm3 kg-1 kg g-1',
        'alpha_p': 'm3 kg-1 Pa-1',
    }
    long_names = {
        'alpha_0': 'specific volume at the reference state',
        'alpha_theta': 'derivative of specific volume with respect to '
        'conservative temperature',
        'alpha_s': 'derivative of specific volume with respect to absolute '
        'salinity',
        'alpha_p': 'derivative of specific volume with respect to pressure',
    }

    return xr.Dataset(
        {
            name: xr.DataArray(
                data=values,
                dims=temperature.dims,
                attrs={
                    'long_name': long_names[name],
                    'units': units[name],
                },
            )
            for name, values in coefficients.items()
        }
    )


def edge_expansion(
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    pressure: xr.DataArray,
) -> xr.Dataset:
    """
    The edge-shared expansion of ``[edge-ref]``: the four coefficients and the
    reference state, each averaged over the two cells of the edge.

    Parameters
    ----------
    temperature : xarray.DataArray
        Layer-mean conservative temperature in degC, with an ``nCells``
        dimension of size 2.

    salinity : xarray.DataArray
        Layer-mean absolute salinity in g kg-1, on the same points.

    pressure : xarray.DataArray
        Layer-mean sea gauge pressure in Pa (``PressureMid``), on the same
        points.

    Returns
    -------
    expansion : xarray.Dataset
        ``alpha_0``, ``alpha_theta``, ``alpha_s``, ``alpha_p`` and the
        reference
        state ``theta_ref``, ``s_ref``, ``p_ref``, with ``nCells`` contracted
        away by the edge average.

        Note that ``alpha_0`` is the *average of the two cells' specific
        volumes*, each evaluated at its own state -- not specific volume
        evaluated at the averaged state.  The difference is second order in the
        cross-edge contrast, and is exactly what source 4 of the remainder
        accounts for.
    """
    coefficients = specvol_coefficients(
        temperature=temperature, salinity=salinity, pressure=pressure
    )

    expansion = xr.Dataset(
        {
            name: edge_mean(coefficients[name]).assign_attrs(
                coefficients[name].attrs
            )
            for name in coefficients.data_vars
        }
    )

    for name, field, long_name, units in [
        ('theta_ref', temperature, 'conservative temperature', 'degC'),
        ('s_ref', salinity, 'absolute salinity', 'g kg-1'),
        ('p_ref', pressure, 'sea gauge pressure', 'Pa'),
    ]:
        expansion[name] = edge_mean(field).assign_attrs(
            {
                'long_name': f'edge-shared expansion point, {long_name}',
                'units': units,
            }
        )

    return expansion


def edge_specvol(
    expansion: xr.Dataset,
    temperature: xr.DataArray | float,
    salinity: xr.DataArray | float,
    pressure: xr.DataArray | float,
) -> xr.DataArray:
    """
    Evaluate the edge-shared profile ``[alpha-taylor]`` at a given state.

    The arguments may carry an ``nCells`` dimension while ``expansion`` does
    not, in which case both columns are evaluated with the one shared set of
    coefficients -- which is the whole point of ``[edge-ref]``.

    Parameters
    ----------
    expansion : xarray.Dataset
        The edge-shared expansion from :py:func:`edge_expansion`.

    temperature : xarray.DataArray or float
        Conservative temperature in degC at which to evaluate.

    salinity : xarray.DataArray or float
        Absolute salinity in g kg-1 at which to evaluate.

    pressure : xarray.DataArray or float
        Sea gauge pressure in Pa at which to evaluate.

    Returns
    -------
    specvol : xarray.DataArray
        :math:`\\hat\\alpha^{(e)}` in m3 kg-1, with the dimensions of the state
        arguments in their original order.
    """
    specvol = (
        expansion.alpha_0
        + expansion.alpha_theta * (temperature - expansion.theta_ref)
        + expansion.alpha_s * (salinity - expansion.s_ref)
        + expansion.alpha_p * (pressure - expansion.p_ref)
    )

    # ``expansion`` has no nCells dimension, so xarray broadcasts it to the end
    # and the result comes back with the state's dimensions permuted.  Restore
    # the caller's order: a field written to init.nc or masked by index with
    # silently transposed dimensions is a hard bug to see.
    template = _template(temperature, salinity, pressure)
    if template is not None:
        specvol = specvol.transpose(*template.dims, ...)

    return specvol.assign_attrs(
        {
            'long_name': 'edge-shared specific volume',
            'units': 'm3 kg-1',
        }
    )


def edge_specvol_layer_mean(
    expansion: xr.Dataset,
    temperature: xr.DataArray,
    salinity: xr.DataArray,
    pressure: xr.DataArray,
) -> xr.DataArray:
    """
    The layer mean of the edge-shared profile, ``[alpha-edge-layer-mean]``.

    This is :py:func:`edge_specvol` evaluated at the *layer-mean* state, and it
    is the same arithmetic for a reason worth stating rather than leaving to be
    rediscovered: ``[alpha-taylor]`` is linear in :math:`\\Theta`, :math:`S`
    and :math:`p` jointly, so the layer mean of :math:`\\hat\\alpha^{(e)}` is
    :math:`\\hat\\alpha^{(e)}` evaluated at the layer means of its arguments.
    The reconstruction of §3.4 is mean-preserving, so the layer means of
    :math:`\\Theta(p)` and :math:`S(p)` are the prognostic layer means; and
    ``PressureMid`` is the exact arithmetic midpoint of the two interface
    pressures, so the layer mean of :math:`p` is ``PressureMid``.  The shape of
    the reconstruction inside the layer therefore cannot affect this quantity.

    It is source 4 of the remainder that needs it: the mismatch against
    ``VertCoord``'s own increment, ``[eos-remainder]``, is the second-order
    Taylor remainder of the equation of state across the edge.

    Parameters
    ----------
    expansion : xarray.Dataset
        The edge-shared expansion from :py:func:`edge_expansion`.

    temperature : xarray.DataArray
        Layer-mean conservative temperature in degC.

    salinity : xarray.DataArray
        Layer-mean absolute salinity in g kg-1.

    pressure : xarray.DataArray
        Layer-mean sea gauge pressure in Pa (``PressureMid``).

    Returns
    -------
    specvol : xarray.DataArray
        The layer mean of :math:`\\hat\\alpha^{(e)}` in m3 kg-1.
    """
    return edge_specvol(
        expansion=expansion,
        temperature=temperature,
        salinity=salinity,
        pressure=pressure,
    ).assign_attrs(
        {
            'long_name': 'layer mean of the edge-shared specific volume',
            'units': 'm3 kg-1',
        }
    )


def _template(*values: xr.DataArray | float) -> xr.DataArray | None:
    """
    The first argument that is a ``DataArray``, whose dimension order
    :py:func:`edge_specvol` restores, or ``None`` if all are scalars.
    """
    for value in values:
        if isinstance(value, xr.DataArray):
            return value
    return None
