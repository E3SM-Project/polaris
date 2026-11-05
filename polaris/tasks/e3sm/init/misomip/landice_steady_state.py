import shutil

import netCDF4
import numpy as np

from polaris.step import Step

#: The length in m that MISOMIP's MALI mesh spans in x, before its gutter:
#: 20 km past the MISMIP+ calving front, so that the ocean sees ice-free
#: MALI cells beyond the front rather than the end of MALI's mesh
LANDICE_MESH_LENGTH = 660.0e3

#: The dimensions along which MALI's fields lie on the mesh
MESH_DIMENSIONS = {
    'nCells': ('xCell', 'yCell'),
    'nEdges': ('xEdge', 'yEdge'),
    'nVertices': ('xVertex', 'yVertex'),
}


class LandiceSteadyStateStep(Step):
    """
    A step for copying the MISMIP+ steady state, on the domain's mesh, onto
    MISOMIP's longer MALI mesh, whose first cells are the domain's at the
    same positions
    """

    def __init__(self, component, subdir, spin_up_step, init_step, mesh_step):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        spin_up_step : polaris.Step
            The MISMIP+ step whose output is the steady state on the
            domain's mesh

        init_step : polaris.Step
            The MISMIP+ ``init`` step on the longer mesh, whose fields the
            cells beyond the domain's mesh take

        mesh_step : polaris.Step
            The step that makes the longer mesh
        """
        super().__init__(
            component=component, name='landice_steady_state', subdir=subdir
        )
        self.add_input_file(
            filename='domain_steady_state.nc',
            work_dir_target=f'{spin_up_step.path}/steady_state.nc',
        )
        self.add_input_file(
            filename='landice_grid.nc',
            work_dir_target=f'{init_step.path}/landice_grid.nc',
        )
        self.add_input_file(
            filename='planar_mesh.nc',
            work_dir_target=f'{mesh_step.path}/planar_mesh.nc',
        )
        self.add_output_file(filename='steady_state.nc')

    def run(self):
        """
        Run this step
        """
        with netCDF4.Dataset('planar_mesh.nc') as ds_mesh:
            mesh_variables = set(ds_mesh.variables)
        copy_by_position(
            src_filename='domain_steady_state.nc',
            dst_template='landice_grid.nc',
            out_filename='steady_state.nc',
            mesh_variables=mesh_variables,
        )
        removed = remove_masked_ice('steady_state.nc')
        self.logger.info(
            f'Removed the ice in {removed} cells where the calving mask is '
            f'1, as MALI does before its first output'
        )


def copy_by_position(src_filename, dst_template, out_filename, mesh_variables):
    """
    Copy MALI's fields from a file on one mesh to a mesh that has each of
    its cells, edges and vertices at the same positions, and more

    Parameters
    ----------
    src_filename : str
        The file with the fields to copy

    dst_template : str
        A file on the larger mesh, whose mesh and fields the output starts
        from

    out_filename : str
        The output file

    mesh_variables : set of str
        The variables that describe the mesh, which keep the larger mesh's
        values
    """
    shutil.copyfile(dst_template, out_filename)
    with (
        netCDF4.Dataset(src_filename) as ds_src,
        netCDF4.Dataset(out_filename, 'a') as ds_out,
    ):
        indices = {
            dim: get_indices_by_position(ds_src, ds_out, *coords)
            for dim, coords in MESH_DIMENSIONS.items()
        }
        ds_src.set_auto_mask(False)
        ds_out.set_auto_mask(False)
        for name, var_src in ds_src.variables.items():
            if name in mesh_variables:
                continue
            values = var_src[:]
            mesh_dims = [dim for dim in var_src.dimensions if dim in indices]
            if len(mesh_dims) > 1:
                raise ValueError(
                    f'{name} lies along more than one mesh dimension.'
                )
            if name in ds_out.variables:
                out_values = ds_out.variables[name][:]
            else:
                _create_variable(ds_src, ds_out, var_src)
                out_values = None
            if not mesh_dims:
                ds_out.variables[name][:] = values
                continue
            dim = mesh_dims[0]
            axis = var_src.dimensions.index(dim)
            if out_values is None or out_values.shape[axis] == 0:
                # the larger mesh's elements beyond the source's are zero
                shape = list(values.shape)
                shape[axis] = len(ds_out.dimensions[dim])
                out_values = np.zeros(shape, dtype=values.dtype)
            index = [slice(None)] * values.ndim
            index[axis] = indices[dim]
            out_values[tuple(index)] = values
            ds_out.variables[name][:] = out_values


def get_indices_by_position(ds_src, ds_dst, x_name, y_name):
    """
    Get the index in the destination mesh of each cell, edge or vertex of
    the source mesh at the same position

    Parameters
    ----------
    ds_src : netCDF4.Dataset
        The source mesh

    ds_dst : netCDF4.Dataset
        The destination mesh

    x_name : str
        The variable with the x coordinate, such as ``xCell``

    y_name : str
        The variable with the y coordinate, such as ``yCell``

    Returns
    -------
    indices : numpy.ndarray
        The destination index of each source element
    """
    dst_index = {
        position: index
        for index, position in enumerate(
            zip(
                _round(ds_dst.variables[x_name][:]),
                _round(ds_dst.variables[y_name][:]),
                strict=True,
            )
        )
    }
    positions = zip(
        _round(ds_src.variables[x_name][:]),
        _round(ds_src.variables[y_name][:]),
        strict=True,
    )
    indices = []
    for position in positions:
        if position not in dst_index:
            raise ValueError(
                f'No {x_name[1:]} of the destination mesh is at {position} m.'
            )
        indices.append(dst_index[position])
    return np.array(indices)


def remove_masked_ice(filename):
    """
    Remove the ice where MALI's calving mask is 1

    Parameters
    ----------
    filename : str
        A MALI file with ``thickness`` and ``calvingMask``

    Returns
    -------
    removed : int
        The number of cells whose ice was removed
    """
    with netCDF4.Dataset(filename, 'a') as ds:
        thickness = ds.variables['thickness'][:]
        masked = np.logical_and(
            ds.variables['calvingMask'][:] == 1, thickness > 0.0
        )
        thickness[masked] = 0.0
        ds.variables['thickness'][:] = thickness
    return int(masked.sum())


def _round(values):
    """
    Round positions in m to a millimeter, so that equal positions compare
    equal
    """
    return np.round(np.asarray(values), 3).tolist()


def _create_variable(ds_src, ds_out, var_src):
    """
    Create a variable of the source file in the output, with any dimension
    the output lacks
    """
    for dim in var_src.dimensions:
        if dim not in ds_out.dimensions:
            size = ds_src.dimensions[dim]
            ds_out.createDimension(
                dim, None if size.isunlimited() else len(size)
            )
    fill_value = getattr(var_src, '_FillValue', None)
    var_out = ds_out.createVariable(
        var_src.name,
        var_src.dtype,
        var_src.dimensions,
        fill_value=fill_value,
    )
    for attr in var_src.ncattrs():
        if attr != '_FillValue':
            var_out.setncattr(attr, var_src.getncattr(attr))
