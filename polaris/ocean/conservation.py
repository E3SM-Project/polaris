from polaris.constants import get_constant

cp_sw = get_constant('seawater_specific_heat_capacity_reference')
rho_sw = get_constant('seawater_density_reference')


def compute_total_mass(ds_mesh, ds):
    """
    Compute the total mass in an ocean model output file using a constant
    density
    """
    ds = _reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = _get_layer_thickness(ds)
    total_mass = rho_sw * (
        area_cell * layer_thickness.sum(dim='nVertLevels')
    ).sum(dim='nCells')
    return total_mass


def compute_total_energy(ds_mesh, ds):
    """
    Compute the total heat content in an ocean model output file
    """
    ds = _reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = _get_layer_thickness(ds)
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
    Compute the total tracer in an ocean model output file
    """
    ds = _reduce_dataset_time_dim(ds)
    area_cell = ds_mesh.areaCell
    layer_thickness = _get_layer_thickness(ds)
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


def _get_layer_thickness(ds):
    if 'PseudoThickness' in ds:
        return ds.PseudoThickness
    elif 'layerThickness' in ds:
        return ds.layerThickness
    else:
        raise ValueError(
            'compute_total_energy requires either PseudoThickness or '
            'layerThickness to be present in the dataset'
        )
