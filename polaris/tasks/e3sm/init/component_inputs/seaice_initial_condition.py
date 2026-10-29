import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.coriolis import add_spherical_coriolis
from polaris.step import Step
from polaris.tasks.e3sm.init.component_inputs.models import check_seaice_model


class SeaiceInitialConditionStep(Step):
    """
    A step for staging the MPAS-Seaice initial condition.

    The mesh and the Coriolis parameter, and nothing else: a sea-ice run
    starts from an ice-free ocean, so there is no state to carry over.

    Compass copied ``fCell``, ``fEdge`` and ``fVertex`` out of an ocean
    restart, which made the sea-ice files depend on a chain of ocean steps
    that had nothing to do with them.  They are functions of latitude alone,
    so they are computed here instead.  That is what lets the sea-ice task
    run without the ocean, which
    ``tests/e3sm/init/component_inputs/test_seaice.py`` checks directly.

    Attributes
    ----------
    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
        The step that culled the ocean mesh.
    """

    def __init__(
        self,
        component,
        subdir,
        cull_mesh_step,
        name='seaice_initial_condition',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
            The step that wrote ``culled_ocean_mesh.nc``.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.cull_mesh_step = cull_mesh_step

        self.add_input_file(
            filename='culled_ocean_mesh.nc',
            work_dir_target=os.path.join(
                cull_mesh_step.path, 'culled_ocean_mesh.nc'
            ),
        )
        self.add_output_file(filename='seaice_initial_condition.nc')

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_seaice_model(self.config)

    def run(self):
        """
        Add the Coriolis parameter to the culled mesh.
        """
        super().run()
        check_seaice_model(self.config)

        with xr.open_dataset('culled_ocean_mesh.nc') as ds_in:
            ds_out = ds_in.load()

        # 2 * Omega * sin(lat).  The spherical helper is called directly
        # rather than through add_coriolis_to_dataset, which would read
        # [coriolis] type from a config section a sea-ice step has no business
        # reading -- and whose default, 'zero', would be silently wrong here.
        ds_out = add_spherical_coriolis(ds_out)

        write_netcdf(ds_out, 'seaice_initial_condition.nc')
