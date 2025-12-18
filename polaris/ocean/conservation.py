from mpas_tools.cime.constants import constants

# Should match config_density0
rho_sw = 1026.0

cp_sw = constants['SHR_CONST_CPSW']


def compute_total_mass(ds_mesh, ds):
    """
    Compute the total mass in an ocean model output file using a constant
    density
    """
    ds = _reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    total_mass = rho_sw * (
        area_cell * layer_thickness.sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_mass


def compute_total_mass_nonboussinesq(ds_mesh, ds):
    """
    Compute the total mass in an ocean model output file using the density
    field given in the output file
    """
    ds = _reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    rho = ds.density
    total_mass = rho * (
        area_cell * (layer_thickness * rho).sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_mass


def compute_total_energy(ds_mesh, ds):
    """
    Compute the total heat content an ocean model output file
    """
    ds = _reduce_dataset_time_dim(ds)
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


def compute_total_tracer(ds_mesh, ds, tracer_name='tracer1'):
    """
    Compute the total salt in an ocean model output file
    """
    ds = _reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = ds.layerThickness
    tracer = ds[tracer_name]
    total_tracer = (
        area_cell * (layer_thickness * tracer).sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_tracer


def compute_total_salt(ds_mesh, ds):
    """
    Compute the total salt in an ocean model output file
    """
    return compute_total_tracer(ds_mesh, ds, tracer_name='salinity')


def _reduce_dataset_time_dim(ds):
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
