import os

import xarray as xr
from mpas_tools.io import write_netcdf
from pyremap import Remapper

from polaris import Step

_WOA23_EXTRAP_FILENAME = 'woa23_decav_0.25_jan_extrap.nc'


class RemapWoa23Step(Step):
    """
    A step for remapping the extrapolated WOA23 hydrography product from the
    native 0.25-degree latitude-longitude grid to MPAS cell centres.

    Attributes
    ----------
    extrapolate_step : polaris.Step
        The upstream step that produces the extrapolated WOA23 product.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
        The upstream cull-mesh step whose outputs describe the target MPAS
        mesh.

    mesh_name : str
        The name of the MPAS mesh, used to label the mapping file.
    """

    def __init__(
        self, component, subdir, extrapolate_step, cull_mesh_step, mesh_name
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        extrapolate_step : polaris.Step
            The step that produces ``woa23_decav_0.25_jan_extrap.nc``.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh files.

        mesh_name : str
            Name label for the MPAS mesh (used in the remapping weight
            filename).
        """
        super().__init__(
            component=component,
            name='remap_woa23',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.extrapolate_step = extrapolate_step
        self.cull_mesh_step = cull_mesh_step
        self.mesh_name = mesh_name
        self.add_output_file('woa23_on_mesh.nc')

    def setup(self):
        """
        Declare input files and compute ntasks from the estimated mesh size.
        """
        super().setup()
        self.add_input_file(
            filename='woa23_extrap.nc',
            work_dir_target=os.path.join(
                self.extrapolate_step.path,
                _WOA23_EXTRAP_FILENAME,
            ),
        )
        self.add_input_file(
            filename='culled_mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )
        self._update_ntasks()

    def constrain_resources(self, available_resources):
        """
        Update ntasks from cell-count estimate before constraining.
        """
        self._update_ntasks()
        super().constrain_resources(available_resources)

    def run(self):
        """
        Remap WOA23 CT and SA from the 0.25-degree lat-lon source grid to
        MPAS cell centres, writing ``woa23_on_mesh.nc``.
        """
        logger = self.logger
        config = self.config
        map_tool = config.get('realistic_global_init', 'map_tool')

        remapper = Remapper(ntasks=self.ntasks, map_tool=map_tool)
        remapper.src_from_lon_lat(
            filename='woa23_extrap.nc',
            mesh_name='woa23_0.25deg',
            lon_var='lon',
            lat_var='lat',
        )
        remapper.dst_from_mpas(
            filename='culled_mesh.nc',
            mesh_name=self.mesh_name,
        )
        remapper.build_map(logger=logger)
        remapper.ncremap(
            in_filename='woa23_extrap.nc',
            out_filename='woa23_on_mesh_raw.nc',
            variable_list=['ct_an', 'sa_an'],
            logger=logger,
        )

        ds_raw = xr.open_dataset('woa23_on_mesh_raw.nc')
        ds_out = self._postprocess_remapped_output(ds_raw)
        write_netcdf(ds_out, 'woa23_on_mesh.nc')

    def _update_ntasks(self):
        """
        Set ntasks and min_tasks from the estimated mesh cell count and the
        ``remap_cells_per_task`` / ``remap_min_cells_per_task`` config
        options.  Falls back to ntasks=1 if the cell count cannot be
        estimated.
        """
        config = self.config
        cell_count = _estimate_cell_count(self.mesh_name)
        if cell_count is None:
            return
        section = config['realistic_global_init']
        cells_per_task = section.getint('remap_cells_per_task')
        min_cells_per_task = section.getint('remap_min_cells_per_task')
        self.ntasks = max(1, round(cell_count / cells_per_task))
        self.min_tasks = max(1, round(cell_count / min_cells_per_task))

    @staticmethod
    def _postprocess_remapped_output(ds):
        """
        Clean up the raw ncremap output: rename ``ncol`` to ``nCells``,
        retain only ``ct_an`` and ``sa_an``, and ensure the ``depth``
        coordinate is preserved with the correct polarity convention
        (positive downward, in metres).

        Parameters
        ----------
        ds : xarray.Dataset
            Raw dataset produced by ncremap, with the horizontal dimension
            named ``ncol``.

        Returns
        -------
        xarray.Dataset
            Dataset with dimension ``nCells``, variables ``ct_an`` and
            ``sa_an``, and coordinate ``depth`` (positive downward).
        """
        if 'ncol' in ds.dims:
            ds = ds.rename({'ncol': 'nCells'})

        keep_vars = [v for v in ['ct_an', 'sa_an'] if v in ds]
        ds_out = ds[keep_vars]

        if 'depth' in ds.coords and 'depth' not in ds_out.coords:
            ds_out = ds_out.assign_coords(depth=ds['depth'])

        for var in keep_vars:
            ds_out[var].attrs = ds[var].attrs

        return ds_out


def _estimate_cell_count(mesh_name):
    """
    Return an approximate MPAS cell count for the given mesh name, or
    ``None`` if the count cannot be determined.

    For simple base meshes (icos / qu / rrs / so) the count is derived
    from the minimum cell resolution via the heuristic
    ``6e8 / min_res_km**2``.  For unified meshes it is read from the
    ``approximate_cell_count`` option in the ``[unified_mesh]`` section
    of the per-mesh config file.

    Parameters
    ----------
    mesh_name : str
        The MPAS mesh name as registered in :py:func:`get_base_mesh_step_names`
        or :py:data:`polaris.mesh.spherical.unified.UNIFIED_MESH_NAMES`.

    Returns
    -------
    int or None
    """
    from polaris.mesh.base import BASE_MESH_DEFINITIONS

    if mesh_name in BASE_MESH_DEFINITIONS:
        min_res = BASE_MESH_DEFINITIONS[mesh_name].min_res  # km
        return 6e8 / min_res**2

    from polaris.mesh.spherical.unified import UNIFIED_MESH_NAMES

    if mesh_name in UNIFIED_MESH_NAMES:
        from polaris.mesh.spherical.unified.configs import (
            get_unified_mesh_config,
        )

        cfg = get_unified_mesh_config(mesh_name)
        return cfg.getint(
            'unified_mesh', 'approximate_cell_count', fallback=None
        )

    return None
