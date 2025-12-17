from mpas_tools.cime.constants import constants

# Should match config_density0
rho_sw = 1026.0

cp_sw = constants['SHR_CONST_CPSW']


def compute_total_mass(ds_mesh, ds):
    ds = reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    total_mass = rho_sw * (
        area_cell * layer_thickness.sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_mass


def compute_total_mass_nonboussinesq(ds_mesh, ds):
    ds = reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    rho = ds.density
    total_mass = rho * (
        area_cell * (layer_thickness * rho).sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_mass


def compute_total_energy(ds_mesh, ds):
    ds = reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    temperature = ds.temperature
    total_energy = (
        rho_sw
        * cp_sw
        * (
            area_cell * (layer_thickness * temperature).sum(dim='nVertLevels')
        ).sum(dim='nCells')
    )
    return total_energy


def compute_total_salt(ds_mesh, ds):
    ds = reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    salinity = ds.salinity
    total_energy = (
        area_cell * (layer_thickness * salinity).sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_energy


def reduce_dataset_time_dim(ds):
    for time_dim in ['time', 'Time']:
        if time_dim in ds.dims:
            if ds.sizes[time_dim] > 1:
                raise ValueError(
                    'compute_total_energy is designed to work on a dataset '
                    'with one time slice'
                )
            else:
                ds = ds.isel(time_dim=0)
    return ds


# def compute_net_mass_flux(ds):
#    netMassFlux = &
#         + accumulatedRainFlux &
#         + accumulatedSnowFlux &
#         + accumulatedEvaporationFlux &
#         + accumulatedSeaIceFlux &
#         + accumulatedRiverRunoffFlux &
#         + accumulatedIceRunoffFlux &
#         + accumulatedIcebergFlux &
#         + accumulatedFrazilFlux &
#         + accumulatedLandIceFlux
# note, accumulatedLandIceFrazilFlux not added because already in
# accumulatedFrazilFlux
#    if (config_subglacial_runoff_mode == 'data'):
#         netMassFlux = netMassFlux + accumulatedSubglacialRunoffFlux
#    return net_mass_flux
#
# def compute_net_salt_flux(ds):
#    netSaltFlux = accumulatedSeaIceSalinityFlux &
#                + accumulatedFrazilSalinityFlux
#
#    if (config_subglacial_runoff_mode == 'data'):
#       netSaltFlux = netSaltFlux + accumulatedSubglacialRunoffSalinityFlux
#    return net_salt_flux
#
# def compute_net_energy_flux(ds):
#         netEnergyFlux = &
#                accumulatedSeaIceHeatFlux           &
#              + accumulatedShortWaveHeatFlux        &
#              + accumulatedLongWaveHeatFluxUp       &
#              + accumulatedLongWaveHeatFluxDown     &
#              + accumulatedLatentHeatFlux           &
#              + accumulatedSensibleHeatFlux         &
#              + accumulatedMeltingSnowHeatFlux      &
#              + accumulatedMeltingIceRunoffHeatFlux &
#              + accumulatedIcebergHeatFlux          &
#              + accumulatedFrazilHeatFlux           &
#              + accumulatedLandIceHeatFlux          &
#              + accumulatedRainTemperatureFlux   *rho_sw*cp_sw &
#              + accumulatedEvapTemperatureFlux   *rho_sw*cp_sw &
#              + accumulatedSeaIceTemperatureFlux *rho_sw*cp_sw &
#              + accumulatedRiverRunoffTemperatureFlux   *rho_sw*cp_sw &
#              + accumulatedIcebergTemperatureFlux*rho_sw*cp_sw
# note, accumulatedLandIceFrazilHeatFlux not added because already in
# accumulatedFrazilHeatFlux
#    if (config_subglacial_runoff_mode == 'data'):
#            netEnergyFlux += accumulatedSubglacialRunoffTemperatureFlux * \
#                rho_sw*cp_sw
#    return net_energy_flux
