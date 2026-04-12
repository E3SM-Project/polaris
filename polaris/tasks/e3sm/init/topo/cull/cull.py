import os

import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call
from mpas_tools.mesh.conversion import cull
from mpas_tools.mesh.creation.sort_mesh import sort_mesh
from mpas_tools.mesh.cull import map_culled_to_base
from pyremap import MpasCellMeshDescriptor

from polaris import Step
from polaris.model_step import make_graph_file

CULL_PREFIXES = ['ocean', 'ocean_no_cavities', 'land']
SCRIP_PREFIXES = ['ocean', 'ocean_no_cavities', 'land']


class CullMeshStep(Step):
    """
    A step for culling out land cells from the ocean/sea-ice mesh and
    ocean/sea-ice cells from the land mesh.

    Attributes
    ----------
    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The base mesh step

    cull_mask_step : polaris.tasks.e3sm.init.topo.cull.CullMaskStep
        The step for creating masks for culling the land and ocean
    """

    def __init__(
        self,
        component,
        base_mesh_step,
        cull_mask_step,
        name,
        subdir,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
            The base mesh step

        cull_mask_step : polaris.tasks.e3sm.init.topo.cull.CullMaskStep
            The step for creating masks for culling the land and ocean

        name : str
            the name of the step

        subdir : str
            the subdirectory for the step
        """
        super().__init__(
            component,
            name=name,
            subdir=subdir,
            cpus_per_task=None,
            min_cpus_per_task=None,
        )
        self.base_mesh_step = base_mesh_step
        self.cull_mask_step = cull_mask_step

        for prefix in CULL_PREFIXES:
            self.add_output_file(filename=f'culled_{prefix}_mesh.nc')
            self.add_output_file(filename=f'{prefix}_map_culled_to_base.nc')
            if prefix in SCRIP_PREFIXES:
                self.add_output_file(filename=f'culled_{prefix}_mesh.scrip.nc')
            if prefix.startswith('ocean'):
                self.add_output_file(filename=f'culled_{prefix}_graph.info')

    def setup(self):
        """
        Set up the step in the work directory, including downloading any
        dependencies.
        """
        super().setup()
        config = self.config
        section = config['cull_mesh']

        base_path = self.base_mesh_step.path
        base_filename = self.base_mesh_step.config.get(
            'spherical_mesh',
            'mpas_mesh_filename',
        )
        target = os.path.join(base_path, base_filename)
        self.add_input_file(filename='base_mesh.nc', work_dir_target=target)

        self.add_input_file(
            filename='cull_masks.nc',
            work_dir_target=os.path.join(
                self.cull_mask_step.path, 'cull_masks.nc'
            ),
        )
        self.cpus_per_task = section.getint('cpus_per_task')
        self.min_cpus_per_task = section.getint('min_cpus_per_task')

    def constrain_resources(self, available_resources):
        """
        Constrain ``cpus_per_task`` and ``ntasks`` based on the number of
        cores available to this step

        Parameters
        ----------
        available_resources : dict
            The total number of cores available to the step
        """
        config = self.config
        section = config['cull_mesh']
        self.cpus_per_task = section.getint('cpus_per_task')
        self.min_cpus_per_task = section.getint('min_cpus_per_task')
        super().constrain_resources(available_resources)

    def run(self):
        """
        Run this step of the test case
        """
        super().run()
        for prefix in CULL_PREFIXES:
            self._cull_mesh(prefix)

    def _cull_mesh(self, prefix):
        """
        Cull and sort the mesh to the region specified by the prefix. For
        ocean regions, also produce a graph file for the culled mesh.
        """
        logger = self.logger

        cull_vars = {
            'ocean': 'oceanCullMask',
            'ocean_no_cavities': 'oceanNoCavitiesCullMask',
            'land': 'landCullMask',
        }

        ds_cull_masks = xr.open_dataset('cull_masks.nc')
        cull_mask = ds_cull_masks[cull_vars[prefix]]
        ds_mask = xr.Dataset()
        ds_mask['regionCellMasks'] = cull_mask.expand_dims(
            dim='nRegions', axis=1
        )

        ds_base_mesh = xr.open_dataset('base_mesh.nc')

        ds_culled_mesh = cull(
            dsIn=ds_base_mesh,
            dsMask=ds_mask,
            logger=logger,
            dir='.',
        )

        # sort the cell, edge and vertex indices for better performances
        ds_culled_mesh = sort_mesh(ds_culled_mesh)

        out_filename = f'culled_{prefix}_mesh.nc'
        write_netcdf(ds_culled_mesh, out_filename)
        if prefix in SCRIP_PREFIXES:
            self._create_scrip_file(mesh_filename=out_filename, prefix=prefix)

        ds_map_culled_to_base = map_culled_to_base(
            ds_base=ds_base_mesh,
            ds_culled=ds_culled_mesh,
            workers=self.cpus_per_task,
        )
        write_netcdf(ds_map_culled_to_base, f'{prefix}_map_culled_to_base.nc')

        if prefix.startswith('ocean'):
            # we need to make the graph file after sorting
            make_graph_file(
                mesh_filename=out_filename,
                graph_filename=f'culled_{prefix}_graph.info',
            )

    def _create_scrip_file(self, mesh_filename, prefix):
        """
        Create a SCRIP file from a culled MPAS mesh.
        """
        logger = self.logger
        logger.info(f'Create SCRIP file for culled {prefix} mesh')

        scrip_filename = mesh_filename.replace('.nc', '.scrip.nc')
        netcdf4_filename = mesh_filename.replace('.nc', '.scrip.netcdf4.nc')
        mesh_name = f'{self.base_mesh_step.mesh_name}_{prefix}'

        descriptor = MpasCellMeshDescriptor(
            filename=mesh_filename,
            mesh_name=mesh_name,
        )
        descriptor.to_scrip(netcdf4_filename)

        # writing directly in NETCDF3_64BIT_DATA proved prohibitively slow
        # so we will use ncks to convert
        args = [
            'ncks',
            '-O',
            '-5',
            netcdf4_filename,
            scrip_filename,
        ]
        check_call(args, logger)

        logger.info('  Done.')
