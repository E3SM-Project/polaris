"""
Diagnostics of the mixed-layer eddies tasks, shared by their analysis steps.

Fields are read with MPAS-Ocean names, so one code path serves both
models.  Transports use the flux thickness of each model's continuity
equation: Omega's pseudo-thickness and MPAS-Ocean's layer thickness.
Depths and densities are geometric.  The salinity-only linear equation of
state makes density, and therefore buoyancy, a function of salinity alone.
"""

import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.eos import compute_density
from polaris.ocean.overturning import (
    bin_line_transport,
    compute_line_transport,
    compute_overturning,
    get_line_edges,
    interp_cell_to_line_edges,
)
from polaris.ocean.vertical.ztilde import RhoSw

Gravity = get_constant('standard_acceleration_of_gravity')


def get_frontal_lines(ds_mesh, frontal_zone_fraction):
    """
    Get the lines of constant y between rows of cells in the frontal zone
    around ``y = L_y / 2``

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The horizontal mesh

    frontal_zone_fraction : float
        The half-width of the frontal zone as a fraction of ``L_y``

    Returns
    -------
    lines : list of xarray.Dataset
        The lines from :py:func:`polaris.ocean.overturning.get_line_edges`
    """
    y_period = float(ds_mesh.attrs['y_period'])
    rows = np.unique(np.round(ds_mesh.yCell.values, 3))
    y_lines = 0.5 * (rows[:-1] + rows[1:])
    half_width = frontal_zone_fraction * y_period
    in_zone = np.abs(y_lines - 0.5 * y_period) < half_width
    return [get_line_edges(ds_mesh, 'y', y) for y in y_lines[in_zone]]


def get_frontal_cell_mask(ds_mesh, frontal_zone_fraction):
    """
    Get a mask of the cells in the frontal zone around ``y = L_y / 2``
    """
    y_period = float(ds_mesh.attrs['y_period'])
    half_width = frontal_zone_fraction * y_period
    return np.abs(ds_mesh.yCell - 0.5 * y_period) < half_width


def get_flux_thickness(ds):
    """
    Get the thickness that multiplies velocity in the model's continuity
    equation: ``PseudoThickness`` for Omega, ``layerThickness`` for
    MPAS-Ocean
    """
    if 'PseudoThickness' in ds:
        return ds.PseudoThickness
    return ds.layerThickness


def get_density(config, ds):
    """
    Compute the density from the tracers with the configured equation of
    state.  Temperature does not affect density in these tasks, so the
    configured constant stands in for it where output omits it.
    """
    if 'temperature' in ds:
        temperature = ds.temperature
    else:
        temperature = config.getfloat('mixed_layer_eddies', 'temperature')
    density = compute_density(config, temperature, ds.salinity)
    assert isinstance(density, xr.DataArray)
    return density


def get_geom_thickness(config, ds):
    """
    Get the geometric layer thickness, converting Omega's pseudo-thickness
    with the density of each layer if need be
    """
    if 'layerThickness' in ds:
        return ds.layerThickness
    return ds.PseudoThickness * RhoSw / get_density(config, ds)


def get_z_mid(layer_thickness, vert_dim='nVertLevels'):
    """
    Get the geometric heights of layer midpoints relative to the sea
    surface from the geometric layer thicknesses
    """
    z_bot = -layer_thickness.cumsum(dim=vert_dim)
    return z_bot + 0.5 * layer_thickness


def compute_mu(z, ml_depth):
    """
    Compute the vertical structure function of Fox-Kemper et al. (2008),
    zero below the mixed layer

    Parameters
    ----------
    z : numpy.ndarray or xarray.DataArray
        Heights (m, negative) relative to the sea surface

    ml_depth : float or numpy.ndarray or xarray.DataArray
        The mixed-layer depth H (m, positive)

    Returns
    -------
    mu : numpy.ndarray or xarray.DataArray
        The structure function, with a maximum of 1 at ``z = -H/2``
    """
    zeta = 2.0 * z / ml_depth + 1.0
    mu = (1.0 - zeta**2) * (1.0 + (5.0 / 21.0) * zeta**2)
    return np.maximum(mu, 0.0)


def compute_buoyancy_gradient(config, ds_mesh, ds, cell_mask, ml_depth):
    """
    Compute the mixed-layer mean cross-front buoyancy gradient from
    differences of area-weighted means over y-bands one row of cells wide

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options

    ds_mesh : xarray.Dataset
        The horizontal mesh

    ds : xarray.Dataset
        Model output with tracers and a thickness, with or without ``Time``

    cell_mask : xarray.DataArray
        The cells whose bands contribute to the mean gradient

    ml_depth : float
        The depth of the mixed layer (m)

    Returns
    -------
    buoyancy_gradient : xarray.DataArray
        The mean gradient (s-2), with ``Time`` if ``ds`` has it
    """
    density = get_density(config, ds)
    thickness = get_geom_thickness(config, ds)
    z_mid = get_z_mid(thickness)
    in_ml = z_mid > -ml_depth
    weights = (thickness * ds_mesh.areaCell).where(in_ml, 0.0)
    buoyancy = -Gravity * (density - RhoSw) / RhoSw

    rows = np.round(ds_mesh.yCell.values, 3)
    row_values = np.unique(rows)
    row_index = xr.DataArray(
        np.searchsorted(row_values, rows), dims=('nCells',), name='nRows'
    )
    weighted = (buoyancy * weights).sum(dim='nVertLevels')
    total = weights.sum(dim='nVertLevels')
    band_buoyancy = (
        weighted.groupby(row_index).sum() / total.groupby(row_index).sum()
    )

    gradient = band_buoyancy.diff(dim='nRows') / np.diff(row_values).mean()
    mask_rows = np.unique(rows[cell_mask.values])
    in_zone = np.isin(row_values[1:], mask_rows) & np.isin(
        row_values[:-1], mask_rows
    )
    return gradient.isel(nRows=np.flatnonzero(in_zone)).mean(dim='nRows')


def compute_line_overturning(lines, normal_velocity, flux_thickness):
    """
    Compute the overturning stream function per unit length along each line,
    at layer interfaces

    Returns
    -------
    overturning : xarray.DataArray
        The stream function (m2 s-1) with dimension ``nLines`` added
    """
    psi = []
    for line in lines:
        transport = compute_line_transport(
            line, normal_velocity, flux_thickness
        )
        psi.append(compute_overturning(transport) / line.attrs['length'])
    return xr.concat(psi, dim='nLines')


def compute_line_interface_depths(lines, geom_thickness):
    """
    Compute the along-line mean geometric depths of the layer interfaces of
    each line, relative to the sea surface

    Returns
    -------
    z_interface : xarray.DataArray
        Heights (m, negative) with dimensions ``nLines`` and
        ``nVertLevelsP1`` (and any others of ``geom_thickness``)
    """
    z_inter = []
    for line in lines:
        thickness = interp_cell_to_line_edges(line, geom_thickness)
        mean_thickness = (thickness * line.weight).sum(
            dim='nLineEdges'
        ) / line.attrs['length']
        z_inter.append(_interfaces_from_thickness(mean_thickness))
    return xr.concat(z_inter, dim='nLines')


def compute_eddy_overturning(lines, snapshots, bins, config):
    """
    Compute the eddy overturning along each line in the thickness-weighted,
    salinity-binned framework of Shrestha & Manucharyan (2022): the
    residual overturning in salinity classes minus the Eulerian-mean
    overturning at the mean depth of each class (Abernathey et al. 2011),
    both averaged over the snapshots

    Parameters
    ----------
    lines : list of xarray.Dataset
        The lines from :py:func:`get_frontal_lines`

    snapshots : iterable of xarray.Dataset
        Model output at each time, with ``normalVelocity``, ``salinity``,
        ``temperature`` and a thickness

    bins : numpy.ndarray
        The boundaries of the salinity classes, increasing

    config : polaris.config.PolarisConfigParser
        Config options, for the equation of state

    Returns
    -------
    ds_eddy : xarray.Dataset
        A dataset with dimensions ``nLines`` and ``nBinsP1`` (salinity class
        boundaries) containing ``psiResidual``, ``psiEulerian`` and
        ``psiEddy`` (m2 s-1) and ``zClass``, the mean depth of each class
        boundary (m)
    """
    nlines = len(lines)
    nbins = len(bins) - 1
    transport_sum = np.zeros((nlines, nbins))
    class_thickness_sum = np.zeros((nlines, nbins))
    psi_eul_sum = None
    z_inter_sum = None
    count = 0
    for ds in snapshots:
        flux_thickness = get_flux_thickness(ds)
        geom_thickness = get_geom_thickness(config, ds)
        z_inter = compute_line_interface_depths(lines, geom_thickness).values
        psi_eul = np.zeros(z_inter.shape)
        for index, line in enumerate(lines):
            transport = compute_line_transport(
                line, ds.normalVelocity, flux_thickness
            )
            psi_eul[index, :] = (
                compute_overturning(transport) / line.attrs['length']
            ).values
            ds_binned = bin_line_transport(
                transport,
                interp_cell_to_line_edges(line, geom_thickness),
                interp_cell_to_line_edges(line, ds.salinity),
                bins,
            )
            transport_sum[index, :] += ds_binned.transport.sum(
                dim='nLineEdges'
            ).values
            class_thickness_sum[index, :] += (
                (ds_binned.thickness * line.weight).sum(dim='nLineEdges')
            ).values
        if psi_eul_sum is None:
            psi_eul_sum = psi_eul
            z_inter_sum = z_inter
        else:
            assert z_inter_sum is not None
            psi_eul_sum = psi_eul_sum + psi_eul
            z_inter_sum = z_inter_sum + z_inter
        count += 1

    if count == 0 or psi_eul_sum is None or z_inter_sum is None:
        raise ValueError('No snapshots to compute the eddy overturning from')

    lengths = np.array([line.attrs['length'] for line in lines])
    transport_mean = transport_sum / (count * lengths[:, np.newaxis])
    class_thickness_mean = class_thickness_sum / (
        count * lengths[:, np.newaxis]
    )
    psi_eul_mean = psi_eul_sum / count
    z_inter_mean = z_inter_sum / count

    # accumulate from the lightest (freshest) class, at the surface
    zeros = np.zeros((nlines, 1))
    psi_res = np.concatenate(
        [zeros, np.cumsum(transport_mean, axis=1)], axis=1
    )
    z_class = np.concatenate(
        [zeros, -np.cumsum(class_thickness_mean, axis=1)], axis=1
    )
    psi_eul_at_class = np.zeros_like(psi_res)
    for index in range(nlines):
        # np.interp needs increasing heights
        psi_eul_at_class[index, :] = np.interp(
            z_class[index, :],
            z_inter_mean[index, ::-1],
            psi_eul_mean[index, ::-1],
        )

    dims = ('nLines', 'nBinsP1')
    ds_eddy = xr.Dataset()
    ds_eddy['psiResidual'] = (dims, psi_res)
    ds_eddy['psiEulerian'] = (dims, psi_eul_at_class)
    ds_eddy['psiEddy'] = (dims, psi_res - psi_eul_at_class)
    ds_eddy['zClass'] = (dims, z_class)
    ds_eddy['salinityClass'] = ('nBinsP1', np.asarray(bins, dtype=float))
    ds_eddy['yLine'] = (
        ('nLines',),
        np.array([line.attrs['value'] for line in lines]),
    )
    return ds_eddy


def fit_mu_amplitude(psi, z, ml_depth):
    """
    Fit ``psi(z) = amplitude * mu(z)`` by least squares over the mixed layer

    Parameters
    ----------
    psi : numpy.ndarray
        Stream function values

    z : numpy.ndarray
        Heights (m, negative) of ``psi``

    ml_depth : float
        The mixed-layer depth H (m)

    Returns
    -------
    amplitude : float
        The fitted amplitude, the stream function at ``z = -H/2``
    """
    mu = compute_mu(z, ml_depth)
    valid = np.logical_and(np.isfinite(psi), mu > 0.0)
    return float(np.sum(psi[valid] * mu[valid]) / np.sum(mu[valid] ** 2))


def compute_fk11_stream_function(
    config, ds_mesh, ds, edges, mld, n2_top, mle_section, model, ml_index=None
):
    """
    Evaluate the stream function of the Fox-Kemper et al. (2011)
    parameterization on edges from model output, as the models discretize
    it.  Given each model's mixed-layer depth and buoyancy frequency, the
    mixed-layer means of the buoyancy gradient and the buoyancy frequency are
    thickness-weighted means over layer interfaces, from the surface to the
    top of the first layer whose midpoint is below the mixed-layer depth.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options

    ds_mesh : xarray.Dataset
        The horizontal mesh

    ds : xarray.Dataset
        Model output at one time

    edges : numpy.ndarray
        Zero-based indices of the edges to evaluate the stream function on

    mld : xarray.DataArray
        The model's mixed-layer depth (m) on cells

    n2_top : xarray.DataArray
        The model's buoyancy frequency squared (s-2) at the top of each layer
        on cells, with dimension ``nVertLevels`` or ``nVertLevelsP1``

    mle_section : str
        The config section with the parameterization's settings

    model : {'omega', 'mpas-ocean'}
        The model, which sets four details: Omega measures the mixed-layer
        depth from the sea surface and MPAS-Ocean from z = 0; the
        mixed-layer depth on edges is the minimum of the two cells' in Omega
        and the mean in MPAS-Ocean; Omega takes the gradient of specific
        volume and MPAS-Ocean that of density; and MPAS-Ocean uses the
        gradient at the second interface for the top half-layer

    ml_index : numpy.ndarray, optional
        The model's zero-based index on cells of the first layer whose
        midpoint is below the mixed-layer depth.  By default, it is found
        from ``mld``, which is ambiguous where the model clamps the
        mixed-layer depth to a layer midpoint and the output layer depths
        come from a different stage of a time step

    Returns
    -------
    psi : numpy.ndarray
        The stream function (m3 s-1 per m along the edge's normal direction,
        i.e. m2 s-1) at layer interfaces, with shape
        ``(len(edges), nVertLevels + 1)``
    """
    section = config[mle_section]
    tau = section.getfloat('tau')
    ce = section.getfloat('ce')
    lf_min = section.getfloat('lf_min')
    ds_max = section.getfloat('ds_max')
    tiny = 1e-12 if model == 'omega' else 1e-20

    density = get_density(config, ds).values
    spec_vol = 1.0 / density
    flux_thickness = get_flux_thickness(ds).values
    geom_thickness = get_geom_thickness(config, ds)
    if 'zMid' in ds:
        z_mid = ds.zMid.transpose('nCells', 'nVertLevels').values
    else:
        z_mid = get_z_mid(geom_thickness).values
    geom_thickness = geom_thickness.values
    ssh = ds.ssh.values if 'ssh' in ds else np.zeros(density.shape[0])
    n2 = n2_top.transpose('nCells', ...).values
    nlevels = density.shape[1]

    if ml_index is None:
        # the first layer whose midpoint is below the mixed-layer depth
        depth_mid = -z_mid
        if model == 'omega':
            depth_mid = depth_mid + ssh[:, np.newaxis]
        ml_index = np.sum(depth_mid < mld.values[:, np.newaxis], axis=1)
        ml_index = np.minimum(ml_index, nlevels - 1)

    cells_on_edge = ds_mesh.cellsOnEdge.values[edges] - 1
    cell1 = cells_on_edge[:, 0]
    cell2 = cells_on_edge[:, 1]
    dc_edge = ds_mesh.dcEdge.values[edges][:, np.newaxis]
    f_edge = ds_mesh.fEdge.values[edges]

    h_flux = 0.5 * (flux_thickness[cell1] + flux_thickness[cell2])
    h_geom = 0.5 * (geom_thickness[cell1] + geom_thickness[cell2])
    if model == 'omega':
        grad = -Gravity * RhoSw * (spec_vol[cell2] - spec_vol[cell1])
    else:
        grad = (Gravity / RhoSw) * (density[cell2] - density[cell1])
    grad = grad / dc_edge
    dz_dn = (z_mid[cell2] - z_mid[cell1]) / dc_edge
    spec_vol_edge = 0.5 * (spec_vol[cell1] + spec_vol[cell2])
    n2_edge = 0.5 * (n2[cell1, :nlevels] + n2[cell2, :nlevels])
    n_edge = np.sqrt(
        0.5
        * (
            np.maximum(tiny, n2[cell1, :nlevels])
            + np.maximum(tiny, n2[cell2, :nlevels])
        )
    )

    # layer quantities interpolated to the top interface of each layer
    grad_inter = _to_interfaces(grad, h_flux)
    dz_dn_inter = _to_interfaces(dz_dn, h_flux)
    spec_vol_inter = _to_interfaces(spec_vol_edge, h_flux)
    grad_inter = grad_inter + dz_dn_inter * RhoSw * spec_vol_inter * n2_edge
    if model != 'omega':
        # MPAS-Ocean uses the second interface for the top half-layer;
        # Omega fills its surface buoyancy frequency from the second
        # interface itself
        grad_inter[:, 0] = grad_inter[:, 1]
        n_edge[:, 0] = n_edge[:, 1]

    weights = 0.5 * h_flux
    weights[:, 1:] += 0.5 * h_flux[:, :-1]
    index_ml = np.minimum(ml_index[cell1], ml_index[cell2])
    levels = np.arange(nlevels)[np.newaxis, :]
    weights = np.where(levels <= index_ml[:, np.newaxis], weights, 0.0)
    total = weights.sum(axis=1)
    grad_ml = (weights * grad_inter).sum(axis=1) / total
    n_ml = (weights * n_edge).sum(axis=1) / total

    h_ml = _edge_mld(mld.values, cell1, cell2, model)

    time_scale = np.sqrt(f_edge**2 + 1.0 / tau**2)
    frontal_width = np.maximum(
        lf_min,
        np.maximum(
            np.abs(grad_ml) * h_ml / time_scale**2,
            n_ml * h_ml / time_scale,
        ),
    )
    delta_s = np.minimum(dc_edge[:, 0], ds_max)
    amplitude = ce * (delta_s / frontal_width) * h_ml**2 * grad_ml / time_scale

    z_inter = np.zeros((len(edges), nlevels + 1))
    z_inter[:, 1:] = -np.cumsum(h_geom, axis=1)
    return amplitude[:, np.newaxis] * compute_mu(z_inter, h_ml[:, np.newaxis])


def compute_model_stream_function(config, ds_mesh, ds, edges, eddy_velocity):
    """
    Recover the stream function a model's parameterization computed on edges
    from its eddy velocity, which both models define as minus the difference
    of the stream function across a layer divided by the layer's mean
    geometric thickness on the edge

    Returns
    -------
    psi : numpy.ndarray
        The stream function (m2 s-1) at layer interfaces, with shape
        ``(len(edges), nVertLevels + 1)``
    """
    geom_thickness = get_geom_thickness(config, ds).values
    cells_on_edge = ds_mesh.cellsOnEdge.values[edges] - 1
    h_geom = 0.5 * (
        geom_thickness[cells_on_edge[:, 0]]
        + geom_thickness[cells_on_edge[:, 1]]
    )
    velocity = eddy_velocity.transpose('nEdges', 'nVertLevels').values[edges]
    psi = np.zeros((len(edges), h_geom.shape[1] + 1))
    psi[:, 1:] = np.cumsum(velocity * h_geom, axis=1)
    return psi


def get_consistent_edges(
    config, ds_mesh, ds, edges, eddy_velocity, mld, model
):
    """
    Find the edges where the mixed-layer depth in the output is the one the
    eddy velocity in the output was computed with: the depth lies within the
    deepest layer with a nonzero eddy velocity.  The two can come from
    different stages of a time step, and the mixed-layer depth can jump by
    layers between them where the mixed layer is nearly neutral.

    Returns
    -------
    consistent : numpy.ndarray
        A boolean mask over ``edges``; edges with no eddy velocity are not
        consistent
    """
    geom_thickness = get_geom_thickness(config, ds).values
    cells_on_edge = ds_mesh.cellsOnEdge.values[edges] - 1
    cell1 = cells_on_edge[:, 0]
    cell2 = cells_on_edge[:, 1]
    h_geom = 0.5 * (geom_thickness[cell1] + geom_thickness[cell2])
    depth_inter = np.zeros((len(edges), h_geom.shape[1] + 1))
    depth_inter[:, 1:] = np.cumsum(h_geom, axis=1)

    velocity = eddy_velocity.transpose('nEdges', 'nVertLevels').values[edges]
    active = velocity != 0.0
    has_velocity = active.any(axis=1)
    nlevels = active.shape[1]
    deepest = nlevels - 1 - np.argmax(active[:, ::-1], axis=1)
    rows = np.arange(len(edges))
    top = depth_inter[rows, deepest]
    bottom = depth_inter[rows, deepest + 1]
    h_ml = _edge_mld(mld.values, cell1, cell2, model)
    return has_velocity & (h_ml >= top) & (h_ml <= bottom)


def compute_potential_energy(config, ds_mesh, ds):
    """
    Compute the potential energy per unit area, g rho z h summed over the
    column and averaged over the domain (J m-2)
    """
    density = get_density(config, ds)
    thickness = get_geom_thickness(config, ds)
    if 'zMid' in ds:
        z_mid = ds.zMid
    else:
        z_mid = get_z_mid(thickness)
    column = (Gravity * density * z_mid * thickness).sum(dim='nVertLevels')
    area = ds_mesh.areaCell
    return (column * area).sum(dim='nCells') / area.sum()


def compute_mixed_layer_n2(config, ds_mesh, ds, cell_mask, ml_depth):
    """
    Compute the mean buoyancy frequency squared over the mixed layer of the
    frontal zone (s-2)
    """
    density = get_density(config, ds)
    thickness = get_geom_thickness(config, ds)
    z_mid = get_z_mid(thickness)
    dz = -z_mid.diff(dim='nVertLevels')
    drho = density.diff(dim='nVertLevels')
    n2 = (Gravity / RhoSw) * drho / dz
    in_ml = (z_mid > -ml_depth).isel(nVertLevels=slice(1, None))
    weights = (dz * ds_mesh.areaCell).where(in_ml & cell_mask, 0.0)
    return (n2 * weights).sum(dim=('nCells', 'nVertLevels')) / weights.sum(
        dim=('nCells', 'nVertLevels')
    )


def _interfaces_from_thickness(thickness, vert_dim='nVertLevels'):
    """
    Heights of layer interfaces relative to the surface from layer
    thicknesses, with ``vert_dim`` replaced by ``nVertLevelsP1``
    """
    z_bot = -thickness.cumsum(dim=vert_dim)
    surface = xr.zeros_like(thickness.isel({vert_dim: [0]}))
    z_inter = xr.concat([surface, z_bot], dim=vert_dim)
    z_inter = z_inter.rename({vert_dim: 'nVertLevelsP1'})
    dims = [
        'nVertLevelsP1' if dim == vert_dim else dim for dim in thickness.dims
    ]
    return z_inter.transpose(*dims)


def _to_interfaces(layer_field, thickness):
    """
    Interpolate a layer field (edges by layers) to the top interface of
    each layer, weighting the two adjacent layers by their thickness; the
    top interface takes the top layer's value
    """
    inter = layer_field.copy()
    weight_above = thickness[:, :-1] / (thickness[:, :-1] + thickness[:, 1:])
    inter[:, 1:] = (
        weight_above * layer_field[:, :-1]
        + (1.0 - weight_above) * layer_field[:, 1:]
    )
    return inter


def _edge_mld(mld, cell1, cell2, model):
    """
    The mixed-layer depth on edges: the minimum of the two cells' in Omega
    and the mean in MPAS-Ocean
    """
    if model == 'omega':
        return np.minimum(mld[cell1], mld[cell2])
    return 0.5 * (mld[cell1] + mld[cell2])
