import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.cf import add_cf_conventions

# the fields that are masked by the land and ocean masks during remapping
_MASKED_VARIABLES = [
    'base_elevation',
    'ice_draft',
    'ice_thickness',
    'ocean_frac',
    'ice_frac',
    'grounded_frac',
]

# the standard fields in the topography dataset before culling
TOPO_VARIABLES = [
    'base_elevation',
    'ice_draft',
    'ice_thickness',
    'land_frac',
    'ocean_frac',
    'ice_frac',
    'grounded_frac',
] + [
    f'{prefix}_masked_{var}'
    for prefix in ['land', 'ocean']
    for var in _MASKED_VARIABLES
]


class CullTopoStep(Step):
    """
    A step that reindexes remapped topography from the base mesh onto the
    culled ocean mesh cells using the cell index map produced by
    :py:class:`polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep`, along
    with the land-ice mask from
    :py:class:`polaris.tasks.e3sm.init.topo.cull.mask.CullMaskStep`.

    Attributes
    ----------
    remap_topo_step : polaris.tasks.e3sm.init.topo.remap.remap.RemapTopoStep
        Upstream step that produces ``topography_remapped.nc`` on the base
        mesh.

    cull_mask_step : polaris.tasks.e3sm.init.topo.cull.mask.CullMaskStep
        Upstream step that produces ``cull_masks.nc`` with ``landIceMask``
        on the base mesh.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        Upstream step that produces ``ocean_map_culled_to_base.nc``
        with the 0-indexed ``mapCulledToBaseCell`` array.
    """

    def __init__(
        self,
        component,
        subdir,
        remap_topo_step,
        cull_mask_step,
        cull_mesh_step,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        remap_topo_step : polaris.Step
            The step that produces ``topography_remapped.nc``.

        cull_mask_step : polaris.Step
            The step that produces ``cull_masks.nc``.

        cull_mesh_step : polaris.Step
            The step that produces ``ocean_map_culled_to_base.nc``.
        """
        super().__init__(
            component,
            name='cull_topo',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.remap_topo_step = remap_topo_step
        self.cull_mask_step = cull_mask_step
        self.cull_mesh_step = cull_mesh_step
        self.add_output_file(
            'topography_culled.nc', validate_vars=TOPO_VARIABLES
        )
        self.add_cf_check('topography_culled.nc')

    def setup(self):
        """
        Declare input files from upstream steps.
        """
        super().setup()
        self.add_input_file(
            filename='topography_remapped.nc',
            work_dir_target=os.path.join(
                self.remap_topo_step.path, 'topography_remapped.nc'
            ),
        )
        self.add_input_file(
            filename='cull_masks.nc',
            work_dir_target=os.path.join(
                self.cull_mask_step.path, 'cull_masks.nc'
            ),
        )
        self.add_input_file(
            filename='ocean_map_culled_to_base.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'ocean_map_culled_to_base.nc',
            ),
        )

    def run(self):
        """
        Reindex all fields with an ``nCells`` dimension from the base mesh to
        the culled mesh, add the land-ice mask, and write
        ``topography_culled.nc``.
        """
        super().run()
        ds_topo = xr.open_dataset('topography_remapped.nc')
        ds_masks = xr.open_dataset('cull_masks.nc')
        ds_map = xr.open_dataset('ocean_map_culled_to_base.nc')

        # mapCulledToBaseCell is 0-indexed
        cell_map = ds_map['mapCulledToBaseCell'].values

        ds_out = cull_topography(ds_topo, ds_masks, cell_map)
        write_netcdf(add_cf_conventions(ds_out), 'topography_culled.nc')


def cull_topography(ds_topo, ds_masks, cell_map):
    """
    Reindex topography on the base mesh onto the culled ocean mesh.

    Parameters
    ----------
    ds_topo : xarray.Dataset
        The remapped topography on the base mesh

    ds_masks : xarray.Dataset
        The cull masks on the base mesh, including ``landIceMask``, which is
        1 in cells of the ocean under Antarctic land ice and 0 elsewhere

    cell_map : numpy.ndarray
        The 0-based base-mesh index of each culled cell

    Returns
    -------
    ds_out : xarray.Dataset
        Every field of ``ds_topo`` with an ``nCells`` dimension, and
        ``landIceMask``, on the culled mesh
    """
    ds_out = xr.Dataset()
    for var in ds_topo.data_vars:
        da = ds_topo[var]
        if 'nCells' in da.dims:
            ds_out[var] = _cull_cells(da, cell_map)
    ds_out['landIceMask'] = _cull_cells(ds_masks.landIceMask, cell_map)
    return ds_out


def _cull_cells(da, cell_map):
    """
    Reindex the ``nCells`` dimension of a data array onto the culled cells
    """
    ncells_axis = da.dims.index('nCells')
    return xr.DataArray(
        data=np.take(da.values, cell_map, axis=ncells_axis),
        dims=da.dims,
        attrs=da.attrs,
    )
