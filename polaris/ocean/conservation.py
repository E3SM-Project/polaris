import numpy as np

from polaris.constants import get_constant
from polaris.ocean.eos import compute_ct_freezing
from polaris.ocean.model.time import get_days_since_start

# TODO update once this is used by Omega
# cp_sw = get_constant('seawater_specific_heat_capacity_reference')
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

# mass fluxes (kg/m^2/s)
MASS_ASSOC_SALT_FLUX_VARS = [
    'seaIceSalinityFlux',  # Note: this is not correct for MPAS-O
]

# heat fluxes (W/m^2)
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

# Mass fluxes that may also carry an enthalpy flux, ``flux * cp_sw * T``.
# Which of these are active, and the temperature ``T`` applied to each, is
# model dependent and is resolved by ``_get_enthalpy_flux_vars``.
ENTHALPY_FLUX_VARS = [
    'rainFlux',
    'evaporationFlux',
    'riverRunoffFlux',
    'snowFlux',
    'iceRunoffFlux',
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
    return (rho_sw / 1000.0) * total_salinity


def get_elapsed_seconds(ds, time_index_start=None, time_index_end=-1):
    """
    Elapsed seconds between two states of an output dataset, supporting
    Omega's numeric ``time`` and MPAS-Ocean's ``daysSinceStartOfSim``.

    Parameters
    ----------
    ds : xarray.Dataset
        The output dataset

    time_index_start : int, optional
        The time index in ``ds`` at the start of the interval.  By default,
        the interval starts at the beginning of the simulation (the initial
        condition), rather than at a time in the output file.

    time_index_end : int, optional
        The time index in ``ds`` at the end of the interval

    Returns
    -------
    dt : float
        The elapsed time in seconds
    """
    if time_index_start is None:
        start_time = 0.0
    else:
        start_time = (
            get_days_since_start(ds.isel(Time=time_index_start)) * 86400.0
        )
    end_time = get_days_since_start(ds.isel(Time=time_index_end)) * 86400.0
    return end_time - start_time


def compute_flux_forcing(ds_mesh, ds, budget, dt, model=None, config=None):
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

    config : polaris.config.PolarisConfigParser, optional
        Configuration options, used to compute the freezing temperature from
        the equation of state when a frozen mass flux carries an enthalpy
        flux and the model's freezing temperature is not in the output

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
            total += inst_flux

    if budget == 'mass':
        # salt fluxes (kg salt / m^2 / s) also add mass to the (pseudo-)
        # thickness equation
        for var in MASS_ASSOC_SALT_FLUX_VARS:
            if var in ds:
                flux = _drop_time(ds[var])
                inst_flux = float((flux * area_cell).sum(dim='nCells').values)
                total += inst_flux

    if budget == 'salt' and model == 'mpas-ocean':
        # MPAS-Ocean applies seaIceSalinityFlux * sflux_factor
        # (sflux_factor = 1) as a tendency of h*S in psu m/s, so the
        # corresponding change in salt mass (as computed by
        # compute_total_salt) carries the same rho_sw/1000 conversion
        total *= rho_sw / 1000.0

    if budget == 'energy':
        # frozen mass fluxes are melted by the ocean, absorbing the latent
        # heat of fusion.  The enthalpy of the resulting meltwater is handled
        # below, since the two models apply different temperatures to it.
        for var in FUSION_FLUX_VARS:
            if var in ds:
                flux = _drop_time(ds[var])
                inst_flux = float((flux * area_cell).sum(dim='nCells').values)
                total -= latent_heat_fusion[model] * inst_flux

        # MPAS-Ocean applies an evaporation enthalpy flux
        # (accumulatedEvapTemperatureFlux) and clamps the river runoff
        # temperature at 0 C, whereas Omega folds the evaporation enthalpy
        # into LatentHeatFlux, applies no clamp, and additionally adds the
        # cp_sw * T_f enthalpy of the meltwater from frozen mass fluxes (see
        # SfcTracerForcingOnCell).
        if model == 'mpas-ocean':
            temperature_sources = {
                'rainFlux': 'surface',
                'evaporationFlux': 'surface',
                'riverRunoffFlux': 'surface_clamped',
            }
        elif model == 'omega':
            temperature_sources = {
                'rainFlux': 'surface',
                'riverRunoffFlux': 'surface',
                'snowFlux': 'freezing',
                'iceRunoffFlux': 'freezing',
            }
        else:
            raise ValueError(
                f'"model" is "{model}", which is not one of '
                f'{sorted(cp_sw.keys())}.  A valid model name is required '
                'to compute the enthalpy contribution to the energy budget.'
            )
        temperature_sources = {
            var: source
            for var, source in temperature_sources.items()
            if var in ENTHALPY_FLUX_VARS
        }

        total += _compute_enthalpy_forcing(
            ds_mesh, ds, model, temperature_sources, config
        )

    return total * dt


def _compute_enthalpy_forcing(
    ds_mesh, ds, model, temperature_sources, config=None
):
    """
    Accumulate the enthalpy heat flux carried by mass fluxes such as rain,
    evaporation and runoff, i.e. ``flux * cp_sw * T``

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        The mesh dataset, containing ``areaCell``

    ds : xarray.Dataset
        The output dataset, which may contain surface forcing flux variables

    model : {'omega', 'mpas-ocean'}
        The model name, used to select the specific heat capacity

    temperature_sources : dict of str
        A mapping from flux variable name to the temperature the model
        applies to that flux, one of:

        * ``'surface'``: the temperature of the top model layer
        * ``'surface_clamped'``: the top-layer temperature clamped to be
          >= 0 C, since fresh water cannot be colder than 0 C
        * ``'freezing'``: the local freezing temperature, applied to frozen
          mass fluxes that the ocean melts

    config : polaris.config.PolarisConfigParser, optional
        Configuration options, used to compute the freezing temperature from
        the equation of state when it is not available in the output

    Returns
    -------
    total : float
        The instantaneous enthalpy heat flux in W, zero if no
        enthalpy-carrying mass fluxes are present
    """
    active = {
        var: source for var, source in temperature_sources.items() if var in ds
    }
    if not active:
        return 0.0

    if 'temperature' not in ds:
        raise ValueError(
            'An enthalpy-carrying mass flux is present in the output but '
            '"temperature" is not available, so the enthalpy contribution '
            'to the energy budget cannot be computed.'
        )

    area_cell = ds_mesh.areaCell
    surface_temperature = _drop_time(ds.temperature).isel(nVertLevels=0)

    total = 0.0
    for var, source in active.items():
        if source == 'surface':
            temperature = surface_temperature
        elif source == 'surface_clamped':
            # fresh water cannot be colder than 0 C
            temperature = np.maximum(surface_temperature, 0.0)
        elif source == 'freezing':
            temperature = _get_freezing_temperature(ds, config)
        else:
            raise ValueError(
                f'Unknown enthalpy temperature source "{source}" for "{var}"'
            )
        flux = _drop_time(ds[var])
        inst_flux = float(
            (cp_sw[model] * flux * temperature * area_cell)
            .sum(dim='nCells')
            .values
        )
        total += inst_flux
    return total


def _get_freezing_temperature(ds, config=None):
    """
    Return the freezing temperature of the top model layer

    The model's own freezing temperature is used if it is available in the
    output.  Otherwise, it is computed from the surface salinity with the
    equation of state given by the config options, neglecting the (small)
    gauge pressure at the surface.

    Parameters
    ----------
    ds : xarray.Dataset
        The output dataset

    config : polaris.config.PolarisConfigParser, optional
        Configuration options, required if the freezing temperature is not
        in the output

    Returns
    -------
    t_freezing : xarray.DataArray
        The freezing temperature in the top layer of each column
    """
    for var in ['freezingTemperature', 'CtFreezing', 'TFreezing']:
        if var in ds:
            t_freezing = _drop_time(ds[var])
            if 'nVertLevels' in t_freezing.dims:
                t_freezing = t_freezing.isel(nVertLevels=0)
            return t_freezing

    if 'salinity' not in ds:
        raise ValueError(
            'A frozen mass flux carries an enthalpy flux at the freezing '
            'temperature, but neither a freezing temperature nor "salinity" '
            'is available in the output to compute it.'
        )
    if config is None:
        raise ValueError(
            'A frozen mass flux carries an enthalpy flux at the freezing '
            'temperature, which is not in the output, so config options are '
            'required to compute it from the equation of state.'
        )
    salinity = _drop_time(ds.salinity).isel(nVertLevels=0)
    return compute_ct_freezing(config, salinity, pressure=0.0)


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
