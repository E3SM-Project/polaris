import os

from mpas_tools.io import open_dataset
from mpas_tools.logging import check_call
from pyremap import MpasCellMeshDescriptor

from polaris import Step

#: the SCRIP file for the MPAS mesh that the prepare step makes
TARGET_SCRIP_FILENAME = 'target.scrip.nc'


class PrepareRemapTopoStep(Step):
    """
    A step for deciding how to smooth topography remapped to a global MPAS
    base mesh and making the SCRIP file for the mesh, expanded to smooth.

    Attributes
    ----------
    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The base mesh step containing input files to this step

    smoothing : bool
        Whether smoothing will be applied as part of the remapping

    unsmoothed_topo : polaris.tasks.e3sm.init.topo.RemapTopoStep or None
        A step with unsmoothed topography

    expand_distance : float or xarray.DataArray
        The distance to expand the topography mask

    expand_factor : float or xarray.DataArray
        The factor to expand the topography mask

    do_remapping : bool
        Whether to remap the topography.  If False, smoothing was asked for
        but none is applied, so the unsmoothed topography is used as it is
        and no SCRIP file is made.
    """

    def __init__(
        self,
        component,
        base_mesh_step,
        name,
        subdir,
        smoothing=False,
        unsmoothed_topo=None,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
            The base mesh step containing input files to this step

        name : str
            the name of the step

        subdir : str
            the subdirectory for the step

        smoothing : bool, optional
            Whether smoothing will be applied as part of the remapping

        unsmoothed_topo : polaris.tasks.e3sm.init.topo.RemapTopoStep, optional
            A step with unsmoothed topography
        """
        super().__init__(
            component, name=name, subdir=subdir, ntasks=1, min_tasks=1
        )
        self.base_mesh_step = base_mesh_step
        self.smoothing = smoothing
        self.unsmoothed_topo = unsmoothed_topo
        self.expand_distance = 0.0
        self.expand_factor = 1.0
        self.do_remapping = True

    def setup(self):
        """
        Set up the step in the work directory, including linking input files
        """
        super().setup()
        base_path = self.base_mesh_step.path
        base_filename = self.base_mesh_step.config.get(
            'spherical_mesh',
            'mpas_mesh_filename',
        )
        target = os.path.join(base_path, base_filename)
        self.add_input_file(filename='base_mesh.nc', work_dir_target=target)

        if self._uses_unsmoothed_topo():
            self.add_input_file(
                filename='topography_unsmoothed.nc',
                work_dir_target=os.path.join(
                    self.unsmoothed_topo.path, 'topography_remapped.nc'
                ),
            )

    def define_smoothing(self, ds_unsmoothed):
        """
        Define smoothing ``expand_distance`` and ``expand_factor`` fields.
        Derived classes should override this method to create spatially
        varying smoothing fields.  An ``expand_distance`` of 0.0 and an
        ``expand_factor`` of 1.0 will not smooth the topography

        The default implementation returns constant values from the config
        file.

        Parameters
        ----------
        ds_unsmoothed : xarray.Dataset
            The unsmoothed topography

        Returns
        -------
        expand_distance : xarray.DataArray or float
            The distance to expand the topography mask, same shape as
            fields in ``ds_unsmoothed`` if not constant

        expand_factor : xarray.DataArray or float
            The factor to expand the topography mask, same shape as
            fields in ``ds_unsmoothed`` if not constant
        """
        config = self.config
        section = config['remap_topography']
        expand_distance = section.getfloat('expand_distance')
        expand_factor = section.getfloat('expand_factor')

        return expand_distance, expand_factor

    def run(self):
        """
        Run this step of the test case
        """
        if self._uses_unsmoothed_topo():
            ds_unsmoothed = open_dataset('topography_unsmoothed.nc')
            self.expand_distance, self.expand_factor = self.define_smoothing(
                ds_unsmoothed
            )

            if self.expand_distance == 0.0 and self.expand_factor == 1.0:
                # no smoothing was actually requested, so the unsmoothed
                # topography will do as it is
                self.do_remapping = False
                return

        self._create_target_scrip_file()

    def _uses_unsmoothed_topo(self):
        """
        Whether this step smooths topography that was remapped without
        smoothing
        """
        return self.smoothing and self.unsmoothed_topo is not None

    def _create_target_scrip_file(self):
        """
        Create target SCRIP file from MPAS mesh file.
        """
        logger = self.logger
        logger.info('Create source SCRIP file')
        netcdf4_filename = 'target.scrip.netcdf4.nc'

        mesh_name = self.base_mesh_step.mesh_name

        descriptor = MpasCellMeshDescriptor(
            filename='base_mesh.nc',
            mesh_name=mesh_name,
        )
        descriptor.to_scrip(
            netcdf4_filename,
            expand_dist=self.expand_distance,
            expand_factor=self.expand_factor,
        )

        # writing directly in NETCDF3_64BIT_DATA proved prohibitively slow
        # so we will use ncks to convert
        args = [
            'ncks',
            '-O',
            '-5',
            netcdf4_filename,
            TARGET_SCRIP_FILENAME,
        ]
        check_call(args, logger)

        logger.info('  Done.')
