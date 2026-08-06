import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.tasks.e3sm.init.component_inputs.models import check_seaice_model


class SeaiceMeshStep(Step):
    """
    A step for staging the MPAS-Seaice mesh file.

    The source is the cull step's ``culled_ocean_mesh.nc``, which is exactly
    the horizontal MPAS mesh and nothing else.  Compass took the same fields
    out of an ocean initial state and had to name each one to avoid dragging
    the ocean's variables along; reading the culled mesh directly means there
    is nothing to exclude.

    Sea ice and the ocean share a mesh, so this reads the same file the ocean
    is built on -- but it reads the *mesh*, not anything the ocean computed
    from it.  That distinction is the point of
    :py:class:`~polaris.tasks.e3sm.init.component_inputs.seaice_initial_condition.SeaiceInitialConditionStep`.

    Attributes
    ----------
    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
        The step that culled the ocean mesh.
    """

    def __init__(self, component, subdir, cull_mesh_step, name='seaice_mesh'):
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
        self.add_output_file(filename='seaice_mesh.nc')

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_seaice_model(self.config)

    def run(self):
        """
        Stage the culled mesh as the sea-ice mesh.
        """
        super().run()
        check_seaice_model(self.config)

        with xr.open_dataset('culled_ocean_mesh.nc') as ds_in:
            ds_out = ds_in.load()

        write_netcdf(ds_out, 'seaice_mesh.nc')
