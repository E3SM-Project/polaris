import importlib.resources as imp_res
from typing import Optional, Tuple

import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.vector.reconstruct import reconstruct_variable
from ruamel.yaml import YAML

from polaris.ocean.vertical.diagnostics import (
    geom_thickness_from_ds,
    pseudothickness_from_ds,
)

# ---------------------------------------------------------------------------
# Module-level lazy caches (populated on first use)
# ---------------------------------------------------------------------------

_var_maps: Optional[Tuple[dict, dict]] = None  # (dim_map, var_map)
# keyed by model string -> (horiz_mesh_vars, vert_coord_vars)
_variable_lists: dict = {}


def _get_var_maps() -> Tuple[dict, dict]:
    """Return (mpaso_to_omega_dim_map, mpaso_to_omega_var_map)."""
    global _var_maps
    if _var_maps is None:
        package = 'polaris.ocean.model'
        yaml_file = 'mpaso_to_omega.yaml'
        text = imp_res.files(package).joinpath(yaml_file).read_text()
        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        _var_maps = (nested_dict['dimensions'], nested_dict['variables'])
    return _var_maps


def _get_variable_lists(model: str) -> Tuple[list, list]:
    """Return (horiz_mesh_vars, vert_coord_vars) for the given model."""
    global _variable_lists
    if model not in _variable_lists:
        package = 'polaris.ocean.model'
        text = imp_res.files(package).joinpath('variables.yaml').read_text()
        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        horiz_mesh_vars = nested_dict['ocean']['horiz_mesh_variables']
        vert_coord_vars = list(nested_dict['ocean']['vert_coord_variables'])
        model_section_map = {'mpas-ocean': 'mpas-ocean', 'omega': 'Omega'}
        model_key = model_section_map.get(model or '')
        if model_key:
            extra = nested_dict.get(model_key, {}).get(
                'vert_coord_variables', []
            )
            vert_coord_vars.extend(extra)
        _variable_lists[model] = (horiz_mesh_vars, vert_coord_vars)
    return _variable_lists[model]


def _check_vars_present(ds, native_vars, context):
    """Raise ValueError if any variable in native_vars is absent from ds."""
    missing = [v for v in native_vars if v not in ds]
    if missing:
        raise ValueError(
            f'{context} requires the following variables that are '
            'missing from the dataset: ' + ', '.join(missing)
        )


# ---------------------------------------------------------------------------
# Public I/O functions
# ---------------------------------------------------------------------------


def map_to_native_model_vars(ds, model):
    """
    If the model is Omega, rename dimensions and variables in a dataset
    from their MPAS-Ocean names to the Omega equivalent (appropriate for
    input datasets like an initial condition).

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean variable names

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    Returns
    -------
    ds : xarray.Dataset
        The same dataset with variables renamed as appropriate for the
        ocean model being run
    """
    if model == 'omega':
        dim_map, var_map = _get_var_maps()
        rename = {k: v for k, v in dim_map.items() if k in ds.dims}
        rename_vars = {k: v for k, v in var_map.items() if k in ds}
        rename.update(rename_vars)
        ds = ds.rename(rename)
    return ds


def map_from_native_model_vars(ds, model):
    """
    If the model is Omega, rename dimensions and variables in a dataset
    from their Omega names to the MPAS-Ocean equivalent (appropriate for
    datasets that are output from the model).

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing variable names native to either ocean model

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    Returns
    -------
    ds : xarray.Dataset
        The same dataset with variables named as expected in MPAS-Ocean
    """
    if model == 'omega':
        dim_map, var_map = _get_var_maps()
        rename = {k: v for v, k in dim_map.items() if k in ds.dims}
        rename_vars = {k: v for v, k in var_map.items() if k in ds}
        rename.update(rename_vars)
        ds = ds.rename(rename)
    return ds


def map_var_list_to_native_model(var_list, model):
    """
    If the model is Omega, rename variables from their MPAS-Ocean names to
    the Omega equivalent (appropriate for validation variable lists).

    Parameters
    ----------
    var_list : list of str
        A list of MPAS-Ocean variable names

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    Returns
    -------
    renamed_vars : list of str
        The same list with variables renamed as appropriate for the
        ocean model being run
    """
    if model == 'omega':
        _, var_map = _get_var_maps()
        return [var_map.get(v, v) for v in var_list]
    return var_list


def map_var_list_from_native_model(var_list, model):
    """
    If the model is Omega, rename variables from their Omega names to
    the MPAS-Ocean equivalent.

    Parameters
    ----------
    var_list : list of str
        A list of variable names in native model form

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    Returns
    -------
    renamed_vars : list of str
        The same list with variables renamed back to MPAS-Ocean names
    """
    if model == 'omega':
        _, var_map = _get_var_maps()
        # invert: omega name -> mpaso name
        return [v for v, k in var_map.items() if k in var_list]
    return var_list


def write_model_dataset(ds, filename, config, model):
    """
    Write out the given dataset, mapping dimension and variable names from
    MPAS-Ocean to Omega names if appropriate.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean variable names

    filename : str
        The path for the NetCDF file to write

    config : polaris.config.PolarisConfigParser
        Configuration for the task; used when the model is Omega to
        convert geometric layer thickness to pseudo-thickness before
        writing.

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``
    """
    if model == 'omega':
        mpas_to_omega_vars = {
            'layerThickness': 'PseudoThickness',
            'restingThickness': 'RefPseudoThickness',
        }
        for mpas_var, omega_var in mpas_to_omega_vars.items():
            if mpas_var in ds.keys() and omega_var not in ds.keys():
                pseudothickness, spec_vol = pseudothickness_from_ds(
                    ds, config=config, src_var_name=mpas_var
                )
                if pseudothickness is not None and spec_vol is not None:
                    ds[omega_var] = pseudothickness
                    if mpas_var == 'layerThickness':
                        ds['SpecVol'] = spec_vol

    ds = map_to_native_model_vars(ds, model)
    write_netcdf(ds=ds, fileName=filename)


def write_horiz_mesh_dataset(ds, filename, config, model):
    """
    Write a horizontal mesh dataset, validating that all expected mesh
    variables are present.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean or native model variable names
        including all horizontal mesh variables

    filename : str
        The path for the NetCDF file to write

    config : polaris.config.PolarisConfigParser
        Not used; retained for API compatibility.

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``
    """
    horiz_mesh_vars, _ = _get_variable_lists(model)
    ds = map_to_native_model_vars(ds, model)
    native_vars = map_var_list_to_native_model(horiz_mesh_vars, model)
    _check_vars_present(ds, native_vars, 'write_horiz_mesh_dataset')
    write_netcdf(ds=ds, fileName=filename)


def remove_horiz_mesh_vars(ds, model):
    """
    Remove horizontal mesh variables from a dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean variable names

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    Returns
    -------
    ds : xarray.Dataset
        The same dataset without horizontal mesh variables
    """
    horiz_mesh_vars, _ = _get_variable_lists(model)
    drop = [v for v in horiz_mesh_vars if v in ds]
    if drop:
        ds = ds.drop_vars(drop)
    return ds


def write_vert_coord_dataset(ds, filename, config, model):
    """
    Write a vertical-coordinate dataset for Omega's ``InitialVertCoord``
    stream.  This is a no-op for MPAS-Ocean (vertical coordinate fields
    stay in the initial state file).

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean or native model variable names,
        including the vertical coordinate variables and the
        temperature/salinity/ssh fields needed for pseudo-thickness
        conversion.

    filename : str
        The path for the NetCDF file to write

    config : polaris.config.PolarisConfigParser
        Configuration for the task; used when converting
        ``restingThickness`` to ``RefPseudoThickness``.

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``
    """
    _, vert_coord_vars = _get_variable_lists(model)
    native_vars = map_var_list_to_native_model(vert_coord_vars, model)

    if model != 'omega':
        _check_vars_present(ds, native_vars, 'write_vert_coord_dataset')
        return

    ds_vc = ds.copy()

    if 'restingThickness' in ds_vc and 'RefPseudoThickness' not in ds_vc:
        pseudothickness, _ = pseudothickness_from_ds(
            ds_vc, config=config, src_var_name='restingThickness'
        )
        if pseudothickness is not None:
            if 'Time' in pseudothickness.dims:
                pseudothickness = pseudothickness.isel(Time=0)
            ds_vc['RefPseudoThickness'] = pseudothickness

    ds_vc = map_to_native_model_vars(ds_vc, model)
    _check_vars_present(ds_vc, native_vars, 'write_vert_coord_dataset')
    ds_vc = ds_vc[native_vars]
    write_netcdf(ds=ds_vc, fileName=filename)


def remove_vert_coord_vars(ds, model):
    """
    Remove vertical coordinate variables from a dataset.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean variable names

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    Returns
    -------
    ds : xarray.Dataset
        The same dataset without vertical coordinate variables
    """
    _, vert_coord_vars = _get_variable_lists(model)
    drop = [v for v in vert_coord_vars if v in ds]
    if drop:
        ds = ds.drop_vars(drop)
    return ds


def write_initial_state_dataset(ds, filename, config, model):
    """
    Write an initial-state dataset, omitting horizontal mesh fields and
    (for Omega) vertical coordinate fields.

    For MPAS-Ocean the vertical coordinate variables remain in the initial
    state file.  For Omega they are written separately via
    :py:func:`write_vert_coord_dataset`.

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset containing MPAS-Ocean variable names

    filename : str
        The path for the NetCDF file to write

    config : polaris.config.PolarisConfigParser
        Configuration for the task; forwarded to
        :py:func:`write_model_dataset`.

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``
    """
    ds = remove_horiz_mesh_vars(ds, model)
    if model == 'omega':
        ds = remove_vert_coord_vars(ds, model)
    write_model_dataset(ds, filename, config, model)


def open_model_dataset(
    filename,
    config,
    model,
    mesh_filename=None,
    reconstruct_variables=None,
    coeffs_filename=None,
    **kwargs,
):
    """
    Open the given dataset, mapping variable and dimension names from Omega
    to MPAS-Ocean names if appropriate.

    Parameters
    ----------
    filename : str
        The path for the NetCDF file to open

    config : polaris.config.PolarisConfigParser
        Configuration for the task; used when the model is Omega to
        compute geometric layer thickness from pseudo-thickness.

    model : str
        The ocean model: ``'omega'`` or ``'mpas-ocean'``

    mesh_filename : str, optional
        Path to the mesh NetCDF file.

    reconstruct_variables : list of str, optional
        List of variable names to reconstruct in the dataset.

    coeffs_filename : str, optional
        Path to the coefficients NetCDF file.

    kwargs
        keyword arguments passed to `xarray.open_dataset()`

    Returns
    -------
    ds : xarray.Dataset
        The dataset with variables named as expected in MPAS-Ocean
    """
    ds = xr.open_dataset(filename, **kwargs)
    if (
        model == 'omega'
        and 'layerThickness' not in ds.keys()
        and 'PseudoThickness' in ds.keys()
        and 'SpecVol' in ds.keys()
    ):
        ds['layerThickness'] = geom_thickness_from_ds(ds, config=config)
    ds = map_from_native_model_vars(ds, model)
    ds = _add_reconstructed_variables_to_dataset(
        ds, reconstruct_variables, mesh_filename, coeffs_filename
    )
    return ds


def _add_reconstructed_variables_to_dataset(
    ds, reconstruct_variables, mesh_filename, coeffs_filename
):
    """
    Add reconstructed vector variables to the dataset if requested.

    Parameters
    ----------
    ds : xarray.Dataset
        The dataset to add reconstructed variables to.

    reconstruct_variables : list of str or None
        List of variable names to reconstruct.

    mesh_filename : str
        Path to the mesh NetCDF file.

    coeffs_filename : str
        Path to the coefficients NetCDF file.

    Returns
    -------
    ds : xarray.Dataset
        The dataset with reconstructed variables added.
    """
    if reconstruct_variables is None:
        return ds

    if mesh_filename is None:
        raise ValueError(
            'mesh_filename must be provided to open_model_dataset for '
            'variable reconstruction'
        )
    if coeffs_filename is None:
        raise ValueError(
            'coeffs_filename must be provided to open_model_dataset for '
            'variable reconstruction'
        )

    for variable in reconstruct_variables:
        if variable not in ds:
            raise ValueError(
                f"User requested vector reconstruction for '{variable}' "
                "but it isn't present in the dataset."
            )

        out_var_name = (
            variable.replace('normal', '').lower()
            if 'normal' in variable
            else variable
        )

        if f'{out_var_name}Zonal' in ds and f'{out_var_name}Meridional' in ds:
            continue

        ds_mesh = xr.open_dataset(mesh_filename)
        ds_coeff = xr.open_dataset(coeffs_filename)
        coeffs_reconstruct = ds_coeff.coeffs_reconstruct

        if ds_coeff.sizes['nCells'] != ds_mesh.sizes['nCells']:
            print(
                f'The sizes of coefficient dataset do not match mesh '
                f'dataset; exiting without reconstructing {out_var_name}'
            )
            continue

        reconstruct_variable(
            out_var_name,
            ds[variable],
            ds_mesh,
            coeffs_reconstruct,
            ds,
            quiet=True,
        )

    return ds
