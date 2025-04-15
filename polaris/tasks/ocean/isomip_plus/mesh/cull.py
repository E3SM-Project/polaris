import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.logging import LoggingContext
from mpas_tools.mesh.conversion import cull
from mpas_tools.mesh.creation.sort_mesh import sort_mesh

from polaris import Step
from polaris.model_step import make_graph_file
from polaris.tasks.ocean.isomip_plus.mesh.xy import add_isomip_plus_xy


class CullMesh(Step):
    """
    A step for culling an MPAS mesh

    Attributes
    ----------
    base_mesh : polaris.Step
        The base mesh step containing input files to this step

    topo_remap : polaris.Step
        The topography remapping step containing input files to this step
    """

    def __init__(self, component, subdir, config, base_mesh, topo_remap):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component this step belongs to

        subdir : str
            the subdirectory for the step

        config : polaris.config.PolarisConfigParser
            A shared config parser

        base_mesh : polaris.Step
            The base mesh step containing input files to this step

        topo_remap : polaris.Step
            The topography remapping step containing input files to this step
        """  # noqa: E501
        super().__init__(component=component, name='cull_mesh', subdir=subdir)
        self.base_mesh = base_mesh
        self.topo_remap = topo_remap
        self.set_shared_config(config, link='isomip_plus_topo.cfg')

        base_path = base_mesh.path
        target = os.path.join(base_path, 'base_mesh.nc')
        self.add_input_file(filename='base_mesh.nc', work_dir_target=target)

        topo_path = topo_remap.path
        target = os.path.join(topo_path, 'topography_remapped.nc')
        self.add_input_file(filename='topography.nc', work_dir_target=target)

        for file in ['culled_mesh.nc', 'culled_graph.info']:
            self.add_output_file(filename=file)

    def run(self):
        """
        Run this step
        """
        logger = self.logger
        section = self.config['isomip_plus_topo']
        min_ocean_fraction = section.getfloat('min_ocean_fraction')

        with LoggingContext(name=__name__, logger=logger) as logger:
            _land_mask_from_topo(
                topo_filename='topography.nc',
                mask_filename='land_mask.nc',
                min_ocean_fraction=min_ocean_fraction,
            )

            ds_base = xr.open_dataset('base_mesh.nc')
            ds_land_mask = xr.open_dataset('land_mask.nc')

            # cull the mesh based on the land mask
            ds_culled = cull(
                ds_base, dsMask=ds_land_mask, logger=logger, dir='.'
            )

            # sort the cell, edge and vertex indices for better performances
            ds_culled = sort_mesh(ds_culled)

            add_isomip_plus_xy(ds_culled)

            out_filename = 'culled_mesh.nc'
            write_netcdf(ds_culled, out_filename)

            # we need to make the graph file after sorting
            make_graph_file(
                mesh_filename='culled_mesh.nc',
                graph_filename='culled_graph.info',
            )


def _land_mask_from_topo(topo_filename, mask_filename, min_ocean_fraction):
    ds_topo = xr.open_dataset(topo_filename)

    ocean_frac = ds_topo.oceanFraction

    # we want the mask to be 1 where there's not ocean
    mask = np.logical_or(ocean_frac < min_ocean_fraction, ocean_frac.isnull())
    cull_mask = xr.where(mask, 1, 0)

    cull_mask = cull_mask.expand_dims(dim='nRegions', axis=1)

    ds_mask = xr.Dataset()
    ds_mask['regionCellMasks'] = cull_mask
    write_netcdf(ds_mask, mask_filename)
