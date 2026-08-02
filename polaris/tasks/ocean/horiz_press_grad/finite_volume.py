"""
The ``FiniteVolume`` horizontal pressure gradient for the two-column
``horiz_press_grad`` configurations.

This is the Python counterpart of Omega's ``PressureGradFiniteVolume``.  It is
written from the ``PGradHighOrder.md`` design document rather than from the
C++, so that the Omega-vs-Polaris comparison in the analysis steps compares two
independent implementations of the same mathematics.

The scheme evaluates the exact edge-normal acceleration -- the layer mean of
the geopotential difference taken at *fixed pressure* -- as the centered scheme
plus a remainder::

    T^p_{e,k} = -(g / d_e) * (S_{e,k} + R_{e,k})

The tidal-potential and self-attraction-and-loading terms of the design's
``[ho-discrete]`` are identically zero in these configurations and are omitted.

``S_{e,k}`` (:py:func:`centered_shift`) is the first-order conversion of a
height difference taken at fixed layer index into one taken at fixed pressure,
trapezoid-averaged over the layer's two interfaces.  It is exactly what the
centered scheme computes, so ``R_{e,k}`` is the whole difference between the
two schemes.  Only ``S`` is implemented so far.

Every horizontal difference here is the two-column edge operator of
:py:mod:`~polaris.tasks.ocean.horiz_press_grad.edge`.  The identity in
:py:func:`centered_shift` holds against
:py:meth:`polaris.tasks.ocean.horiz_press_grad.init.Init._compute_montgomery_and_hpga`
itself, not against an idealized centered form.
"""

import numpy as np
import xarray as xr

from polaris.ocean.vertical.ztilde import (
    Gravity,
    RhoSw,
    pressure_from_z_tilde,
)
from polaris.tasks.ocean.horiz_press_grad import (
    eos_expansion,
    reconstruction,
)
from polaris.tasks.ocean.horiz_press_grad.edge import edge_delta, edge_mean

__all__ = [
    'centered_shift',
    'centered_shift_accumulated',
    'shift_increments',
    'hpga_from_shift',
    'hydrostatic_scale',
    'matched_pressure_pieces',
    'anchor_difference',
    'column_scan',
    'scan_increments',
    'layer_mean_difference',
    'finite_volume_hpga',
    'layer_containing_pressure',
    'delta_specvol_at_pressure',
]


def centered_shift(ds: xr.Dataset) -> xr.DataArray:
    """
    The first-order fixed-pressure shift ``S_{e,k}`` of the design's
    ``[centered-shift]``,

    .. math::

        S_{e,k} = \\tfrac{1}{2}\\left(\\Delta_e Z_{k}
        + \\Delta_e Z_{k+1}\\right)
        + \\frac{\\bar\\alpha_{e,k}}{2g}\\left(\\Delta_e q_{k}
        + \\Delta_e q_{k+1}\\right),

    where :math:`Z` is the geometric height at layer interfaces, :math:`q` the
    gauge pressure at layer interfaces, and :math:`\\bar\\alpha_{e,k}` the edge
    average of the layer-mean specific volume.

    The centered scheme's entire Montgomery-potential apparatus is this
    conversion and nothing else, so
    ``hpga_from_shift(centered_shift(ds), dx)`` reproduces the ``HPGA`` field
    written by :py:class:`~polaris.tasks.ocean.horiz_press_grad.init.Init` to
    round-off, at any coordinate tilt.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, which must contain ``GeomZInterface``,
        ``ZTildeInterface`` and ``SpecVol``.  Invalid layers are ``NaN`` and
        propagate as ``NaN``.

    Returns
    -------
    shift : xarray.DataArray
        ``S_{e,k}`` at layer midpoints, in m, with the ``nCells`` dimension
        contracted away by the edge operator.

    """
    # PressureInterface is not carried in the dataset; pseudo-height is, and
    # p = -rho0 * g * z_tilde is an exact identity rather than a conversion.
    q = pressure_from_z_tilde(ds.ZTildeInterface)

    delta_z = edge_delta(ds.GeomZInterface)
    delta_q = edge_delta(q)
    alpha_bar = edge_mean(ds.SpecVol)

    geometric = 0.5 * (_layer_top(delta_z) + _layer_bot(delta_z))
    pressure = (
        alpha_bar
        / (2.0 * Gravity)
        * (_layer_top(delta_q) + _layer_bot(delta_q))
    )

    shift = geometric + pressure
    return shift.assign_attrs(
        {
            'long_name': 'first-order fixed-pressure height shift at layer '
            'midpoints',
            'units': 'm',
        }
    )


def hpga_from_shift(shift: xr.DataArray, dx: float) -> xr.DataArray:
    """
    Convert a fixed-pressure height shift into an edge-normal acceleration,
    ``-(g / d_e) * shift``.

    Parameters
    ----------
    shift : xarray.DataArray
        A fixed-pressure height shift in m, such as
        :py:func:`centered_shift` returns.

    dx : float
        The distance ``d_e`` between the two columns in m.

    Returns
    -------
    hpga : xarray.DataArray
        The edge-normal pressure-gradient acceleration in m s-2.

    """
    if dx == 0.0:
        raise ValueError('dx must be non-zero for finite differences.')

    hpga = -(Gravity / dx) * shift
    return hpga.assign_attrs(
        {
            'long_name': 'along-layer pressure gradient acceleration at layer '
            'midpoints',
            'units': 'm s-2',
        }
    )


def hydrostatic_scale(ds: xr.Dataset) -> float:
    """
    An upper bound on the magnitude of the two hydrostatic terms that cancel
    in :py:func:`centered_shift`.

    At 3500 m those terms are each of order 3500 m and they cancel to
    millimetres or less, so an absolute tolerance says nothing about whether a
    cancellation is at machine precision.  Every round-off assertion against
    this scheme should be written as a multiple of this scale instead
    (``PGradHighOrder.md`` §3.7.5).

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, as for :py:func:`centered_shift`.

    Returns
    -------
    scale : float
        The bound, in m.  Multiply by ``Gravity / dx`` to scale a tolerance on
        an acceleration.

    """
    q = pressure_from_z_tilde(ds.ZTildeInterface)
    z_magnitude = float(np.abs(ds.GeomZInterface).max())
    pressure_magnitude = float(ds.SpecVol.max() * np.abs(q).max() / Gravity)
    return z_magnitude + pressure_magnitude


def _layer_top(field: xr.DataArray) -> xr.DataArray:
    """
    The value at each layer's top interface, as a layer-indexed field.

    """
    return field.isel(nVertLevelsP1=slice(0, -1)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )


def _layer_bot(field: xr.DataArray) -> xr.DataArray:
    """
    The value at each layer's bottom interface, as a layer-indexed field.

    """
    return field.isel(nVertLevelsP1=slice(1, None)).rename(
        {'nVertLevelsP1': 'nVertLevels'}
    )


def centered_shift_accumulated(
    ds: xr.Dataset, anchor: str = 'surface'
) -> xr.DataArray:
    """
    ``S_{e,k}`` accumulated down the column through ``[gamma-increments]``.

    Mathematically identical to :py:func:`centered_shift`, but it never forms
    the two large terms that cancel there.  With
    ``Gamma_{e,k} = Delta_e Z_k + (alphabar_{e,k}/g) Delta_e q_k`` and
    ``Gamma^+_{e,k}`` the same at interface ``k+1``, so that
    ``S_{e,k} = (Gamma + Gamma^+)/2``, the design's ``[gamma-increments]``
    gives

        Gamma^+_{e,k} - Gamma_{e,k}
            = -rho0 * htildebar_{e,k} * Delta_e alpha_k
        Gamma_{e,k+1} - Gamma^+_{e,k}
            = (Delta_e q_{k+1}/g) * (alphabar_{e,k+1} - alphabar_{e,k})

    Both increments are a small factor times a bounded one -- the *horizontal*
    contrast in specific volume within a layer, and the *vertical* contrast
    between adjacent layers -- so the walk introduces no cancellation of large
    numbers anywhere.  The starting value is the inverse-barometer residual at
    the sea surface, itself small for a state at rest.

    Per §3.7.5 this is why a single-precision build might pass at all: the
    round-off exposure of the centered scheme lives entirely in the two ~3500 m
    terms of ``[centered-shift]``, and this form never builds them.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, as for :py:func:`centered_shift`.

    anchor : {'surface', 'bathymetry'}
        Which end of the column to accumulate from.  §3.7.4 leaves this open as
        a round-off question rather than a consistency one; the two agree to
        round-off in double precision, which
        ``tests/ocean/horiz_press_grad/test_finite_volume.py`` measures.

    Returns
    -------
    shift : xarray.DataArray
        ``S_{e,k}`` at layer midpoints, in m.

    """
    if anchor not in ('surface', 'bathymetry'):
        raise ValueError(
            f"anchor must be 'surface' or 'bathymetry'; got {anchor!r}."
        )

    pieces = _shift_pieces(ds)
    within = pieces['within_layer'].values
    between = pieces['between_layers'].values
    gamma_top = pieces['gamma_surface'].values
    gamma_bottom = pieces['gamma_bathymetry'].values
    valid = pieces['valid'].values

    shift = np.full(within.shape, np.nan)
    for index in np.ndindex(within.shape[:-1]):
        levels = np.where(valid[index])[0]
        if len(levels) == 0:
            continue
        column_within = within[index][levels]
        # between_layers[k] is the step from layer k to layer k+1
        column_between = between[index][levels]

        if anchor == 'surface':
            gamma = gamma_top[index]
            for position, level in enumerate(levels):
                gamma_plus = gamma + column_within[position]
                shift[index + (level,)] = 0.5 * (gamma + gamma_plus)
                gamma = gamma_plus + column_between[position]
        else:
            gamma_plus = gamma_bottom[index]
            for position in range(len(levels) - 1, -1, -1):
                level = levels[position]
                gamma = gamma_plus - column_within[position]
                shift[index + (level,)] = 0.5 * (gamma + gamma_plus)
                if position > 0:
                    gamma_plus = gamma - column_between[position - 1]

    return xr.DataArray(
        data=shift,
        dims=pieces['within_layer'].dims,
        attrs={
            'long_name': 'first-order fixed-pressure height shift at layer '
            'midpoints, accumulated',
            'units': 'm',
        },
    )


def shift_increments(ds: xr.Dataset) -> xr.Dataset:
    """
    The two increments of ``[gamma-increments]``, for the D7 measurement.

    Deliverable D7 of the plan asks how much precision the accumulation saves,
    and the quantitative form of "no large-number cancellation occurs" is the
    ratio of the largest increment to the largest of ``Delta_e Z`` -- the
    quantity ``[centered-shift]`` differences directly.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, as for :py:func:`centered_shift`.

    Returns
    -------
    increments : xarray.Dataset
        ``within_layer`` (``Gamma^+_k - Gamma_k``), ``between_layers``
        (``Gamma_{k+1} - Gamma^+_k``), and ``delta_z_interface``
        (``Delta_e Z`` at interfaces) to scale them against.  All in m.

    """
    pieces = _shift_pieces(ds)
    return xr.Dataset(
        {
            'within_layer': pieces['within_layer'],
            'between_layers': pieces['between_layers'],
            'delta_z_interface': pieces['delta_z_interface'],
        }
    )


def _shift_pieces(ds: xr.Dataset) -> dict:
    """The increments and anchors of ``[gamma-increments]``, and the mask of
    layers valid in both columns.

    """
    q = pressure_from_z_tilde(ds.ZTildeInterface)
    delta_q = edge_delta(q)
    delta_z = edge_delta(ds.GeomZInterface)
    alpha_bar = edge_mean(ds.SpecVol)
    delta_alpha = edge_delta(ds.SpecVol)
    thickness_bar = edge_mean(ds.PseudoThickness)

    within = -RhoSw * thickness_bar * delta_alpha

    # the step from layer k to layer k+1, stored at k; the deepest layer has no
    # neighbour below and its entry is never read
    alpha_below = alpha_bar.shift(nVertLevels=-1)
    between = _layer_bot(delta_q) / Gravity * (alpha_below - alpha_bar)
    between = between.fillna(0.0)

    valid = np.isfinite(within)

    gamma_surface = _first_valid(
        _layer_top(delta_z) + alpha_bar / Gravity * _layer_top(delta_q), valid
    )
    gamma_bathymetry = _last_valid(
        _layer_bot(delta_z) + alpha_bar / Gravity * _layer_bot(delta_q), valid
    )

    return {
        'within_layer': within.assign_attrs({'units': 'm'}),
        'between_layers': between.assign_attrs({'units': 'm'}),
        'delta_z_interface': delta_z.assign_attrs({'units': 'm'}),
        'gamma_surface': gamma_surface,
        'gamma_bathymetry': gamma_bathymetry,
        'valid': valid,
    }


def _first_valid(field: xr.DataArray, valid: xr.DataArray) -> xr.DataArray:
    """The value in the shallowest layer valid in both columns."""
    return _at_valid_end(field, valid, first=True)


def _last_valid(field: xr.DataArray, valid: xr.DataArray) -> xr.DataArray:
    """The value in the deepest layer valid in both columns."""
    return _at_valid_end(field, valid, first=False)


def _at_valid_end(
    field: xr.DataArray, valid: xr.DataArray, first: bool
) -> xr.DataArray:
    values = field.values
    mask = valid.values
    result = np.full(values.shape[:-1], np.nan)
    for index in np.ndindex(values.shape[:-1]):
        levels = np.where(mask[index])[0]
        if len(levels) == 0:
            continue
        result[index] = values[index][levels[0 if first else -1]]
    return xr.DataArray(data=result, dims=field.dims[:-1])


def matched_pressure_pieces(
    ds: xr.Dataset, guards: set[str] | None = None
) -> dict:
    """
    Everything the matched-pressure integrand needs, computed once per state.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state, which must contain ``temperature``, ``salinity``,
        ``pressure``, ``ZTildeInterface`` and ``maxLevelCell``.

    Returns
    -------
    pieces : dict
        ``expansion`` (the edge-shared coefficients per edge layer),
        ``theta``/``salinity`` and their reconstruction ``slope``s and
        ``pressure_mid``, each column's ``interface`` pressures and its
        ``deepest`` valid layer, and the edge-layer interface pressures
        ``edge_interface``.

    """
    interface = pressure_from_z_tilde(ds.ZTildeInterface).isel(Time=0).values
    deepest = ds.maxLevelCell.values.astype(int) - 1

    guards = guards or set()
    expansion = eos_expansion.edge_expansion(
        ds.temperature, ds.salinity, ds.pressure
    ).isel(Time=0)
    # The cell-local coefficients are always built, even though only the
    # ``cell_local_expansion`` guard reads them: making them conditional on the
    # guard means a guard passed to an evaluation function but not to this one
    # fails with an AttributeError instead of doing what it says.  One extra
    # equation-of-state evaluation per state is not worth that trap.
    coefficients = eos_expansion.specvol_coefficients(
        ds.temperature, ds.salinity, ds.pressure
    ).isel(Time=0)
    cell_local = xr.Dataset(
        {
            name: coefficients[name]
            for name in ['alpha_0', 'alpha_theta', 'alpha_s', 'alpha_p']
        }
    )
    cell_local['theta_ref'] = ds.temperature.isel(Time=0)
    cell_local['s_ref'] = ds.salinity.isel(Time=0)
    cell_local['p_ref'] = ds.pressure.isel(Time=0)

    return {
        'guards': guards,
        'cell_local': cell_local,
        'expansion': expansion,
        'theta': ds.temperature.isel(Time=0).values,
        'salinity': ds.salinity.isel(Time=0).values,
        'slope_theta': reconstruction.linear_slope(ds.temperature, ds.pressure)
        .isel(Time=0)
        .values,
        'slope_salinity': reconstruction.linear_slope(ds.salinity, ds.pressure)
        .isel(Time=0)
        .values,
        'pressure_mid': ds.pressure.isel(Time=0).values,
        'interface': interface,
        'deepest': deepest,
        'edge_interface': 0.5 * (interface[0, :] + interface[1, :]),
        'surface_height': ds.GeomZInterface.isel(
            Time=0, nVertLevelsP1=0
        ).values,
    }


def layer_containing_pressure(
    pieces: dict, icell: int, pressure: np.ndarray
) -> np.ndarray:
    """
    The index of *column* ``icell``'s own layer containing each pressure.

    This is the lookup the whole scheme turns on, and writing it as a lookup
    rather than assuming "edge layer ``k`` means column layer ``k``" is the
    difference between comparing at matched pressure and comparing at matched
    index.  Under tilt the two columns' layer ``k`` span different pressure
    ranges -- at 50 m/km and 64 m layers they are offset by nearly three layer
    thicknesses and do not overlap at all -- so assuming the index is not a
    small approximation, it is a different scheme, and it is the defect that
    the previous formulation failed on.

    Pressures above the column's surface or below its floor are clamped to the
    outermost valid layer, which extrapolates that layer's reconstruction.
    Exactness does not depend on this (design §3.5, consequence 3): an
    extrapolated reconstruction still reproduces a profile it resolves, so the
    difference is still zero on the exact set.  What it costs off the exact set
    is deliverable D8'.

    Parameters
    ----------
    pieces : dict
        From :py:func:`matched_pressure_pieces`.

    icell : int
        Which column.

    pressure : numpy.ndarray
        Sea gauge pressures in Pa.

    Returns
    -------
    index : numpy.ndarray
        Zero-based layer indices, in ``[0, maxLevelCell - 1]``.

    """
    deepest = int(pieces['deepest'][icell])
    interface = pieces['interface'][icell, : deepest + 2]
    index = np.searchsorted(interface, np.asarray(pressure), side='right') - 1
    return np.clip(index, 0, deepest)


def delta_specvol_at_pressure(
    pieces: dict,
    edge_layer: int,
    pressure: np.ndarray,
    guards: set[str] | None = None,
) -> np.ndarray:
    """
    The design's ``[dalpha]``: the fixed-pressure contrast in specific volume.

    .. math::

        \\Delta_e\\hat\\alpha(p) =
        \\bar\\alpha_\\Theta^{e,k}\\,\\Delta_e\\Theta(p)
        + \\bar\\alpha_S^{e,k}\\,\\Delta_e S(p)

    Both columns use the edge-shared coefficients of **edge layer**
    ``edge_layer``, and each supplies its own :math:`\\Theta(p)`, :math:`S(p)`
    from whichever of *its own* layers contains ``p``.  The
    :math:`\\bar\\alpha_0` and :math:`\\bar\\alpha_p(p-\\bar p^e)` terms are
    the same numbers in both columns and cancel, so they are not formed at all.

    This is the central property of the scheme: the result is a coefficient
    times a horizontal contrast at matched pressure, so it is **identically
    zero pointwise** whenever the two columns' reconstructions describe the
    same water -- independently of the coefficients, of the quadrature, and of
    whether the interfaces line up.

    Parameters
    ----------
    pieces : dict
        From :py:func:`matched_pressure_pieces`.

    edge_layer : int
        The edge layer whose shared coefficient set to use.

    pressure : numpy.ndarray
        Sea gauge pressures in Pa, all within edge layer ``edge_layer``.

    Returns
    -------
    delta_specvol : numpy.ndarray
        :math:`\\Delta_e\\hat\\alpha(p)` in m3 kg-1.

    """
    pressure = np.atleast_1d(np.asarray(pressure, dtype=float))
    if guards is None:
        guards = pieces.get('guards', set())

    level = {}
    for icell in range(2):
        if 'state_by_index' in guards:
            # guard: assume edge layer k means column layer k
            level[icell] = np.full(
                len(pressure),
                min(edge_layer, int(pieces['deepest'][icell])),
            )
        else:
            level[icell] = layer_containing_pressure(pieces, icell, pressure)

    state = {}
    for name in ['theta', 'salinity']:
        values = np.empty((2, len(pressure)))
        for icell in range(2):
            index = level[icell]
            values[icell] = pieces[name][icell, index] + pieces[
                f'slope_{name}'
            ][icell, index] * (pressure - pieces['pressure_mid'][icell, index])
        state[name] = values

    total = np.zeros(len(pressure))
    for icell, sign in [(0, -1.0), (1, 1.0)]:
        coefficients = _coefficients_for(
            pieces, edge_layer, icell, level[icell], guards
        )
        total = total + sign * (
            coefficients['alpha_theta'] * state['theta'][icell]
            + coefficients['alpha_s'] * state['salinity'][icell]
        )
    return total


def anchor_difference(
    pieces: dict, order: int = 2, guards: set[str] | None = None
) -> float:
    """
    The design's ``[anchor]``: the fixed-pressure height difference at the
    edge's topmost interface.

    .. math::

        D_1 = \\Delta_e Z_1 - \\frac{1}{g}\\,\\Delta_e
        \\int_{p^{\\rm surf}_i}^{\\bar q_1} \\hat\\alpha^{(e)}_i(p)\\,dp

    The two columns sit at different surface pressures, so this is the
    sea-surface height difference corrected to the common pressure
    :math:`\\bar q_1`.  The two short integrals are over *different* pressure
    ranges and so cannot be combined into a matched-pressure difference the way
    the interior can; each is taken inside that column's own top layer.

    For a resting ocean whose sea surface satisfies the inverse-barometer
    relation this is zero, and **exactness of the whole scheme inherits that**
    (design §3.5.1).  It is the one place the scheme's robustness depends on
    something outside the pressure gradient, namely the consistency of the
    initialized sea-surface height with the surface pressure.

    Parameters
    ----------
    pieces : dict
        From :py:func:`matched_pressure_pieces`.

    order : int
        Number of Gauss-Legendre points, matching Omega's ``QuadraturePoints``.
        The integrand is linear in pressure within a layer, so 2 integrates it
        exactly.

    Returns
    -------
    anchor : float
        :math:`D_1` in m.


    """
    guards = guards if guards is not None else pieces.get('guards', set())
    delta_z = pieces['surface_height'][1] - pieces['surface_height'][0]
    if 'anchor_delta_z_only' in guards:
        # guard: the sea-surface height difference without correcting to a
        # common pressure
        return float(delta_z)

    nodes, weights = np.polynomial.legendre.leggauss(order)
    common = pieces['edge_interface'][0]

    correction = np.empty(2)
    for icell in range(2):
        surface = pieces['interface'][icell, 0]
        middle = 0.5 * (surface + common)
        half = 0.5 * (common - surface)
        probe = middle + half * nodes
        level = layer_containing_pressure(pieces, icell, probe)
        theta = pieces['theta'][icell, level] + pieces['slope_theta'][
            icell, level
        ] * (probe - pieces['pressure_mid'][icell, level])
        salinity = pieces['salinity'][icell, level] + pieces['slope_salinity'][
            icell, level
        ] * (probe - pieces['pressure_mid'][icell, level])
        expansion = pieces['expansion'].isel(nVertLevels=0)
        specvol = (
            float(expansion.alpha_0)
            + float(expansion.alpha_theta)
            * (theta - float(expansion.theta_ref))
            + float(expansion.alpha_s) * (salinity - float(expansion.s_ref))
            + float(expansion.alpha_p) * (probe - float(expansion.p_ref))
        )
        correction[icell] = half * float(np.sum(weights * specvol))

    return float(delta_z - (correction[1] - correction[0]) / Gravity)


def column_scan(
    pieces: dict, order: int = 2, guards: set[str] | None = None
) -> np.ndarray:
    """
    The design's ``[d-recurrence]``: :math:`D_k = \\Delta_e z(\\bar q_k)`
    accumulated down the edge's column from the sea surface.

    .. math::

        D_{k+1} = D_k - \\frac{1}{g}
        \\int_{\\bar q_k}^{\\bar q_{k+1}} \\Delta_e\\hat\\alpha(p)\\,dp

    Every quantity here is small.  :math:`D_k` is a fixed-pressure height
    difference -- order :math:`10^{-1}` m for a realistic baroclinic column and
    zero for a resting one -- against the :math:`10^{2}` m height differences
    at fixed layer index that a scheme comparing at fixed index has to form and
    cancel.  The increments are smaller still, being integrals of a horizontal
    contrast.  There is no cancellation of large quantities anywhere.

    Parameters
    ----------
    pieces : dict
        From :py:func:`matched_pressure_pieces`.

    order : int
        Number of Gauss-Legendre points for the layer integrals, matching
        Omega's ``QuadraturePoints``.

    Returns
    -------
    difference : numpy.ndarray
        :math:`D_k` at every edge interface valid in both columns, in m, with
        ``difference[0]`` the anchor.


    """
    nodes, weights = np.polynomial.legendre.leggauss(order)
    edges = pieces['edge_interface']
    deepest = int(min(pieces['deepest']))

    difference = np.empty(deepest + 2)
    difference[0] = anchor_difference(pieces, order=order, guards=guards)
    for edge_layer in range(deepest + 1):
        top, bot = edges[edge_layer], edges[edge_layer + 1]
        middle, half = 0.5 * (top + bot), 0.5 * (bot - top)
        contrast = delta_specvol_at_pressure(
            pieces, edge_layer, middle + half * nodes, guards=guards
        )
        integral = half * float(np.sum(weights * contrast))
        difference[edge_layer + 1] = (
            difference[edge_layer] - integral / Gravity
        )

    return difference


def scan_increments(
    pieces: dict, order: int = 2, guards: set[str] | None = None
) -> np.ndarray:
    """
    The per-layer increments of :py:func:`column_scan`, for the smallness
    assertion of §3.7.5.

    Parameters
    ----------
    pieces : dict
        From :py:func:`matched_pressure_pieces`.

    order : int
        Number of Gauss-Legendre points, matching Omega's
        ``QuadraturePoints``.

    Returns
    -------
    increments : numpy.ndarray
        ``D_{k+1} - D_k`` for each edge layer, in m.


    """
    return np.diff(column_scan(pieces, order=order, guards=guards))


def layer_mean_difference(
    pieces: dict, order: int = 2, guards: set[str] | None = None
) -> np.ndarray:
    """
    The layer mean of :math:`\\Delta_e z(p)` over each edge layer.

    Within an edge layer ``[qbar_k, qbar_{k+1}]``,
    :math:`\\Delta_e z(p) = D_k - \\frac{1}{g}\\int_{\\bar q_k}^{p}
    \\Delta_e\\hat\\alpha`, so averaging over the layer and integrating the
    double integral by parts gives

    .. math::

        \\langle\\Delta_e z\\rangle_k = D_k - \\frac{1}{g\\,\\Delta p_{e,k}}
        \\int_{\\bar q_k}^{\\bar q_{k+1}}
        (\\bar q_{k+1} - p)\\,\\Delta_e\\hat\\alpha(p)\\,dp

    which is the "second moment of the same integrand over the same interval"
    of design §3.5.1, on the same quadrature points as the scan.

    Parameters
    ----------
    pieces : dict
        From :py:func:`matched_pressure_pieces`.

    order : int
        Number of Gauss-Legendre points, matching Omega's
        ``QuadraturePoints``.

    guards : set of str, optional
        Verification-only switches; see :py:func:`finite_volume_hpga`.

    Returns
    -------
    mean : numpy.ndarray
        :math:`\\langle\\Delta_e z\\rangle_k` in m, one per edge layer.

    """
    nodes, weights = np.polynomial.legendre.leggauss(order)
    edges = pieces['edge_interface']
    difference = column_scan(pieces, order=order, guards=guards)
    deepest = int(min(pieces['deepest']))

    mean = np.empty(deepest + 1)
    for edge_layer in range(deepest + 1):
        top, bot = edges[edge_layer], edges[edge_layer + 1]
        middle, half = 0.5 * (top + bot), 0.5 * (bot - top)
        probe = middle + half * nodes
        contrast = delta_specvol_at_pressure(
            pieces, edge_layer, probe, guards=guards
        )
        moment = half * float(np.sum(weights * (bot - probe) * contrast))
        mean[edge_layer] = difference[edge_layer] - moment / (
            Gravity * (bot - top)
        )

    return mean


def finite_volume_hpga(
    ds: xr.Dataset,
    dx: float,
    order: int = 2,
    guards: set[str] | None = None,
) -> xr.DataArray:
    """
    The assembled ``FiniteVolume`` horizontal pressure-gradient acceleration,
    design ``[ho-exact]``.

    .. math::

        T^p_{e,k} = -\\frac{g}{d_e}\\,\\langle\\Delta_e z\\rangle_k

    The tidal-potential and self-attraction-and-loading terms are identically
    zero in these configurations and are omitted.

    Parameters
    ----------
    ds : xarray.Dataset
        The two-column state.

    dx : float
        The distance ``d_e`` between the two columns in m.

    order : int
        Number of Gauss-Legendre points, matching Omega's ``QuadraturePoints``.
        Exactness does not depend on it (design §3.5, consequence 2), so it is
        an ordinary accuracy knob -- but it is **not** a free one: Omega and
        Polaris must integrate with the same rule, or
        ``omega_vs_polaris_rms_threshold`` compares two different algorithms
        rather than two implementations of one.  Both are driven by the
        ``quadrature_points`` config option.

    guards : set of str, optional
        Verification-only switches, each deliberately breaking one rule:

        ``'cell_local_expansion'``
            expand about each cell's own state instead of the edge-shared one.
        ``'state_by_index'``
            evaluate each column at its own layer ``k`` instead of the layer
            containing the pressure.
        ``'anchor_delta_z_only'``
            take the anchor as ``Delta_e Z_1`` alone, dropping the correction
            to a common pressure.

    Returns
    -------
    hpga : xarray.DataArray
        The edge-normal acceleration in m s-2, at layer midpoints, ``NaN``
        where a layer is not valid in both columns.

    """
    if dx == 0.0:
        raise ValueError('dx must be non-zero for finite differences.')

    pieces = matched_pressure_pieces(ds, guards=guards)
    mean = layer_mean_difference(pieces, order=order, guards=guards)

    values = np.full(ds.sizes['nVertLevels'], np.nan)
    values[: len(mean)] = -(Gravity / dx) * mean

    hpga = xr.DataArray(
        data=values[np.newaxis, :],
        dims=['Time', 'nVertLevels'],
        attrs={
            'long_name': 'along-layer pressure gradient acceleration at layer '
            'midpoints, finite-volume scheme',
            'units': 'm s-2',
        },
    )
    return hpga


def _coefficients_for(
    pieces: dict,
    edge_layer: int,
    icell: int,
    level: np.ndarray,
    guards: set[str],
) -> dict:
    """
    The equation-of-state coefficients a column uses at a set of pressures.

    Correctly, both columns use the edge-shared set of the *edge* layer.  The
    ``cell_local_expansion`` guard breaks the *sharing*, and that does break
    exactness: design §3.5 consequence 1 says the shared coefficients may take
    any value, not that the two columns may use different ones.  ``[dalpha]``
    only collapses to a coefficient times a contrast when one coefficient set
    multiplies both columns.

    """
    if 'cell_local_expansion' in guards:
        source = pieces['cell_local'].isel(nCells=icell)
        return {
            'alpha_theta': source.alpha_theta.values[level],
            'alpha_s': source.alpha_s.values[level],
        }
    source = pieces['expansion'].isel(nVertLevels=edge_layer)
    return {
        'alpha_theta': float(source.alpha_theta),
        'alpha_s': float(source.alpha_s),
    }
