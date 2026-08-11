import numpy as np

from polaris.constants import get_constant
from polaris.ocean.model.time import get_days_since_start

# TODO cp_sw = get_constant('seawater_specific_heat_capacity_reference')
cp_sw = {'omega': 3991.86795711963, 'mpas-ocean': 3996.0}
rho_sw = get_constant('seawater_density_reference')
latent_heat_fusion = {
    'omega': get_constant('latent_heat_of_fusion_reference'),
    'mpas-ocean': 3.337e5,
}
# Freshwater/mass fluxes that the model adds to the (pseudo-)thickness
# equation.  ``seaIceSalinityFlux`` also enters the thickness equation, so it
# appears in the mass budget as well as the salt budget.
# flux variables (polaris/native names) that enter each budget
MASS_FLUX_VARS = [
    'snowFlux',
    'rainFlux',
    'evaporationFlux',
    'seaIceFreshWaterFlux',
    'iceRunoffFlux',
    'riverRunoffFlux',
    'icebergFreshWaterFlux',  # Note: not available for Omega
]

MASS_ASSOC_SALT_FLUX_VARS = [
    'seaIceSalinityFlux',  # Note: this is not correct for MPAS-O
]

HEAT_FLUX_VARS = [
    'latentHeatFlux',
    'sensibleHeatFlux',
    'shortWaveHeatFlux',
    'longWaveHeatFluxUp',
    'longWaveHeatFluxDown',
    'seaIceHeatFlux',
    'icebergHeatFlux',
]

# mass fluxes (kg/m^2/s) that enter the heat budget as -flux * L_f
FUSION_FLUX_VARS = [
    'snowFlux',
    'iceRunoffFlux',
]

SALT_FLUX_VARS = ['seaIceSalinityFlux']

# mass fluxes that also carry an SST-dependent enthalpy flux; if any is
# nonzero, the heat budget cannot be closed with these terms alone
ENTHALPY_FLUX_VARS = [
    'rainFlux',
    'evaporationFlux',
    'riverRunoffFlux',
]

_FLUX_VARS = {
    'mass': MASS_FLUX_VARS,
    'energy': HEAT_FLUX_VARS,
    'salt': SALT_FLUX_VARS,
}


def compute_total_mass(ds_mesh, ds):
    """
    Compute the total mass in an ocean model output file

    If a pseudo-thickness field is present, a non-Boussinesq approach is
    used, in which the pseudo-thickness carries the layer mass per unit area
    (``rho_sw * pseudoThickness``).  Otherwise, the mass is computed from the
    layer thickness using a constant reference density.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The dataset containing a layer thickness or pseudo-thickness for a
        single time slice

    Returns
    -------
    total_mass : float
        The total mass in kg over the whole domain
    """
    ds = _reduce_dataset_time_dim(ds, caller='compute_total_mass')
    area_cell = ds_mesh.areaCell
    thickness = _get_mass_thickness(ds)
    # For omega this is equivalent to \rho * h * A
    # For mpas-ocean this is equivalent to \rho_ref * h * A
    total_mass = rho_sw * (area_cell * thickness.sum(dim='nVertLevels')).sum(
        dim='nCells'
    )
    return total_mass


def compute_total_energy(ds_mesh, ds, model):
    """
    Compute the total heat content in an ocean model output file

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The dataset containing ``temperature`` and a layer thickness for a
        single time slice

    Returns
    -------
    total_energy : float
        The total heat content in J over the whole domain
    """
    ds = _reduce_dataset_time_dim(ds, caller='compute_total_energy')
    area_cell = ds_mesh.areaCell
    thickness = _get_mass_thickness(ds)
    temperature = ds.temperature
    total_energy = (
        rho_sw
        * cp_sw[model]
        * (area_cell * (thickness * temperature).sum(dim='nVertLevels')).sum(
            dim='nCells'
        )
    )
    return total_energy


def compute_total_tracer(ds_mesh, ds, tracer_name='tracer1'):
    """
    Compute the total tracer in an ocean model output file

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The dataset containing the tracer and a layer thickness for a single
        time slice

    tracer_name : str, optional
        The name of the tracer to integrate

    Returns
    -------
    total_tracer : float
        The volume integral of the tracer over the whole domain
    """
    ds = _reduce_dataset_time_dim(ds, caller='compute_total_tracer')
    area_cell = ds_mesh.areaCell
    thickness = _get_mass_thickness(ds)
    tracer = ds[tracer_name]
    total_tracer = (
        area_cell * (thickness * tracer).sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_tracer


def compute_total_salt(ds_mesh, ds):
    """
    Compute the total mass of salt in an ocean model output file using a
    constant density

    Salinity is assumed to be in g/kg (i.e. grams of salt per kilogram of
    seawater), so the volume integral of ``layerThickness * salinity`` is
    converted to a salt mass with ``rho_sw / 1000``.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The dataset containing ``salinity`` and a layer thickness

    Returns
    -------
    total_salt : float
        The total mass of salt in kg over the whole domain
    """
    total_salinity = compute_total_tracer(ds_mesh, ds, tracer_name='salinity')
    print('compute_total_salt')
    return (rho_sw / 1000.0) * total_salinity


def get_elapsed_seconds(ds):
    """
    Elapsed seconds between two time indices of an output dataset, supporting
    Omega's numeric ``time`` and MPAS-Ocean's ``daysSinceStartOfSim``.
    """
    # start_time = get_days_since_start(ds.isel(Time=0)) * 86400.0
    start_time = 0.0
    end_time = get_days_since_start(ds.isel(Time=-1)) * 86400.0
    return end_time - start_time


def compute_flux_forcing(ds_mesh, ds, budget, dt, model=None):
    """
    Integrate the surface forcing fluxes that contribute to a given budget
    over the duration of a run, assuming the fluxes are constant in time

    Only the flux variables that are present in ``ds`` contribute, so the
    forcing fields must be included in the output stream for the
    corresponding budget to be checked against the forcing.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The output dataset, which may contain surface forcing flux variables

    budget : {'mass', 'energy', 'salt'}
        The budget for which to accumulate the surface fluxes

    dt : float
        The elapsed time of the run in seconds

    model : {'omega', 'mpas-ocean'}, optional
        The model name, required for the energy budget when
        enthalpy-carrying mass fluxes (e.g. rain, evaporation, runoff) are
        active

    Returns
    -------
    total : float
        The accumulated flux in the same units as the corresponding
        ``compute_total_*`` function (kg for mass and salt, J for energy).
        Zero if none of the relevant variables are present in ``ds``.
    """
    if budget not in _FLUX_VARS:
        raise ValueError(f'Unknown conservation budget "{budget}"')
    area_cell = ds_mesh.areaCell
    total = 0.0
    for var in _FLUX_VARS[budget]:
        if var in ds:
            flux = _drop_time(ds[var])
            inst_flux = float((flux * area_cell).sum(dim='nCells').values)
            print(f'{var}: {inst_flux}')
            total += inst_flux

    if budget == 'mass':
        # salt fluxes (kg salt / m^2 / s) also add mass to the (pseudo-)
        # thickness equation
        for var in MASS_ASSOC_SALT_FLUX_VARS:
            if var in ds:
                flux = _drop_time(ds[var])
                inst_flux = float((flux * area_cell).sum(dim='nCells').values)
                print(f'{var} (mass-associated): {inst_flux}')
                total += inst_flux

    if budget == 'salt' and model == 'mpas-ocean':
        # MPAS-Ocean applies seaIceSalinityFlux * sflux_factor
        # (sflux_factor = 1) as a tendency of h*S in psu m/s, so the
        # corresponding change in salt mass (as computed by
        # compute_total_salt) carries the same rho_sw/1000 conversion
        total *= rho_sw / 1000.0

    if budget == 'energy':
        for var in FUSION_FLUX_VARS:
            if var in ds:
                flux = _drop_time(ds[var])
                inst_flux = float((flux * area_cell).sum(dim='nCells').values)
                total -= latent_heat_fusion[model] * inst_flux
                print(f'{var}: {-latent_heat_fusion[model] * inst_flux}')

        total += _compute_enthalpy_forcing(ds_mesh, ds, model)

    return total * dt


def _compute_enthalpy_forcing(ds_mesh, ds, model):
    """
    Accumulate the SST-dependent enthalpy heat flux carried by mass fluxes
    such as rain, evaporation and runoff, i.e. ``flux * cp_sw * SST``

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The output dataset, which may contain surface forcing flux variables

    model : {'omega', 'mpas-ocean'}
        The model name, used to select the specific heat capacity

    Returns
    -------
    total : float
        The instantaneous enthalpy heat flux in W, zero if no
        enthalpy-carrying mass fluxes are present
    """
    active = [var for var in ENTHALPY_FLUX_VARS if var in ds]
    if not active:
        return 0.0

    if model not in cp_sw:
        raise ValueError(
            'An enthalpy-carrying mass flux is present in the output but '
            f'"model" is "{model}", which is not one of '
            f'{sorted(cp_sw.keys())}.  A valid model name is required to '
            'compute the enthalpy contribution to the energy budget.'
        )

    if 'temperature' not in ds:
        raise ValueError(
            'An enthalpy-carrying mass flux is present in the output but '
            '"temperature" is not available, so the enthalpy contribution '
            'to the energy budget cannot be computed.'
        )

    area_cell = ds_mesh.areaCell
    sst = _drop_time(ds.temperature).isel(nVertLevels=0)

    total = 0.0
    for var in active:
        flux = _drop_time(ds[var])
        inst_flux = float(
            np.sum(
                (cp_sw[model] * flux * sst * area_cell)
                .sum(dim='nCells')
                .values
            )
        )
        print(f'{var} (enthalpy): {inst_flux}')
        total += inst_flux
    return total


def _drop_time(da):
    """
    Return a data array with any time dimension removed, using the first time
    slice since the forcing is assumed constant in time
    """
    for time_dim in ['time', 'Time']:
        if time_dim in da.dims:
            da = da.isel({time_dim: 0})
    return da


def _reduce_dataset_time_dim(ds, caller):
    """
    Drop the time dimension from a dataset, which must contain at most a
    single time slice

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to reduce

    caller : str
        The name of the calling function, used in the error message

    Returns
    -------
    ds : xarray.Dataset
        The dataset with any time dimension removed
    """
    for time_dim in ['time', 'Time']:
        if time_dim in ds.dims:
            if ds.sizes[time_dim] > 1:
                print(
                    f'Warning: {caller} requires a dataset with a single '
                    f'time slice but the "{time_dim}" dimension has size '
                    f'{ds.sizes[time_dim]}, using last time slice.'
                )
                ds = ds.isel({time_dim: -1})
    return ds


def _get_mass_thickness(ds):
    """
    Return the thickness field to use in the mass budget, preferring the
    pseudo-thickness (non-Boussinesq) over the layer thickness (Boussinesq)

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset containing a layer thickness or pseudo-thickness

    Returns
    -------
    thickness : xarray.DataArray
        The thickness field to integrate
    """
    for var in ['pseudoThickness', 'PseudoThickness']:
        if var in ds:
            return ds[var]
    return ds.layerThickness
