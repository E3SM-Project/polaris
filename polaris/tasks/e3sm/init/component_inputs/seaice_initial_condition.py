import os
from typing import TYPE_CHECKING

from polaris.coriolis import add_spherical_coriolis
from polaris.lazy import lazy_attr, lazy_module
from polaris.step import Step

if TYPE_CHECKING:
    import xarray as xr
    from mpas_tools.io import write_netcdf
else:
    xr = lazy_module('xarray')
    write_netcdf = lazy_attr('mpas_tools.io', 'write_netcdf')


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

    def run(self):
        """
        Add the Coriolis parameter to the culled mesh.
        """
        super().run()

        with xr.open_dataset('culled_ocean_mesh.nc') as ds_in:
            ds_out = ds_in.load()

        # 2 * Omega * sin(lat).  The spherical helper is called directly
        # rather than through add_coriolis_to_dataset, which would read
        # [coriolis] type from a config section a sea-ice step has no business
        # reading -- and whose default, 'zero', would be silently wrong here.
        ds_out = add_spherical_coriolis(ds_out)

        write_netcdf(ds_out, 'seaice_initial_condition.nc')
