import os

import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.logging import LoggingContext
from mpas_tools.mesh.conversion import cull
from mpas_tools.mesh.creation.sort_mesh import sort_mesh
from mpas_tools.viz.paraview_extractor import extract_vtk

from polaris import Step
from polaris.model_step import make_graph_file


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

    def __init__(self, component, subdir, base_mesh, topo_remap):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component this step belongs to

        subdir : str
            the subdirectory for the step

        base_mesh : polaris.Step
            The base mesh step containing input files to this step

        topo_remap : polaris.Step
            The topography remapping step containing input files to this step
        """  # noqa: E501
        super().__init__(component=component, name='cull_mesh', subdir=subdir)
        self.base_mesh = base_mesh
        self.topo_remap = topo_remap

        base_path = base_mesh.path
        target = os.path.join(base_path, 'base_mesh.nc')
        self.add_input_file(filename='base_mesh.nc', work_dir_target=target)

        topo_path = topo_remap.path
        target = os.path.join(topo_path, 'topography_remapped.nc')
        self.add_input_file(filename='topography.nc',
                            work_dir_target=target)

        for file in ['culled_mesh.nc', 'culled_graph.info']:
            self.add_output_file(filename=file)

    def run(self):
        """
        Run this step
        """
        logger = self.logger

        # only use progress bars if we're not writing to a log file
        use_progress_bar = self.log_filename is None

        with LoggingContext(name=__name__, logger=logger) as logger:
            _land_mask_from_topo(topo_filename='topography.nc',
                                 mask_filename='land_mask.nc')

            dsBaseMesh = xr.open_dataset('base_mesh.nc')
            dsLandMask = xr.open_dataset('land_mask.nc')

            # cull the mesh based on the land mask
            dsCulledMesh = cull(dsBaseMesh, dsMask=dsLandMask, logger=logger,
                                dir='.')

            # sort the cell, edge and vertex indices for better performances
            dsCulledMesh = sort_mesh(dsCulledMesh)

            out_filename = 'culled_mesh.nc'
            write_netcdf(dsCulledMesh, out_filename)

            # we need to make the graph file after sorting
            make_graph_file(mesh_filename='culled_mesh.nc',
                            graph_filename='culled_graph.info')

            extract_vtk(ignore_time=True, dimension_list=['maxEdges='],
                        variable_list=['allOnCells'],
                        filename_pattern='culled_mesh.nc',
                        out_dir='culled_mesh_vtk',
                        use_progress_bar=use_progress_bar)


def _land_mask_from_topo(topo_filename, mask_filename):
    ds_topo = xr.open_dataset(topo_filename)

    ocean_frac = ds_topo.oceanFraction

    # we want the mask to be 1 where there's not ocean
    cull_mask = xr.where(ocean_frac < 0.5, 1, 0)

    cull_mask = cull_mask.expand_dims(dim='nRegions', axis=1)

    ds_mask = xr.Dataset()
    ds_mask['regionCellMasks'] = cull_mask
    write_netcdf(ds_mask, mask_filename)
