import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step


class CullTopoStep(Step):
    """
    A step that reindexes remapped topography from the base mesh onto the
    culled ocean mesh cells using the cell index map produced by
    :py:class:`polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep`.

    Attributes
    ----------
    remap_topo_step : polaris.tasks.e3sm.init.topo.remap.remap.RemapTopoStep
        Upstream step that produces ``topography_remapped.nc`` on the base
        mesh.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        Upstream step that produces ``ocean_map_culled_to_base.nc``
        with the 0-indexed ``mapCulledToBaseCell`` array.
    """

    def __init__(self, component, subdir, remap_topo_step, cull_mesh_step):
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
        self.cull_mesh_step = cull_mesh_step
        self.add_output_file('topography_culled.nc')

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
            filename='ocean_map_culled_to_base.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'ocean_map_culled_to_base.nc',
            ),
        )

    def run(self):
        """
        Reindex all fields with an ``nCells`` dimension from the base mesh to
        the culled mesh and write ``topography_culled.nc``.
        """
        super().run()
        ds_topo = xr.open_dataset('topography_remapped.nc')
        ds_map = xr.open_dataset('ocean_map_culled_to_base.nc')

        # mapCulledToBaseCell is 0-indexed
        cell_map = ds_map['mapCulledToBaseCell'].values

        ds_out = xr.Dataset()
        for var in ds_topo.data_vars:
            da = ds_topo[var]
            if 'nCells' in da.dims:
                ncells_axis = da.dims.index('nCells')
                ds_out[var] = xr.DataArray(
                    data=np.take(da.values, cell_map, axis=ncells_axis),
                    dims=da.dims,
                    attrs=da.attrs,
                )
        write_netcdf(ds_out, 'topography_culled.nc')
