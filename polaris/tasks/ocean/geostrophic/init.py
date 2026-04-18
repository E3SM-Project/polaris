import xarray as xr

from polaris.ocean.coriolis import add_rotated_sphere_coriolis
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.geostrophic.exact_solution import (
    compute_exact_solution,
)


class Init(OceanIOStep):
    """
    A step for an initial condition for for the geostrophic test case
    """

    def __init__(self, component, name, subdir, base_mesh):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        base_mesh : polaris.Step
            The base mesh step
        """
        super().__init__(component=component, name=name, subdir=subdir)

        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc',
        )

        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{base_mesh.path}/graph.info',
        )

        self.add_output_file(filename='base_mesh.nc')
        self.add_output_file(
            filename='initial_state.nc',
            validate_vars=[
                'temperature',
                'salinity',
                'layerThickness',
                'normalVelocity',
            ],
        )

    def run(self):
        """
        Run this step of the testcase
        """
        config = self.config

        section = config['geostrophic']
        temperature = section.getfloat('temperature')
        salinity = section.getfloat('salinity')
        alpha = section.getfloat('alpha')
        vel_period = section.getfloat('vel_period')
        gh_0 = section.getfloat('gh_0')

        mesh_filename = 'mesh.nc'

        h, u_cell, v_cell, normalVelocity = compute_exact_solution(
            alpha, vel_period, gh_0, mesh_filename
        )

        section = config['vertical_grid']
        bottom_depth = section.getfloat('bottom_depth')

        ds_mesh = xr.open_dataset('mesh.nc')
        latCell = ds_mesh.latCell

        add_rotated_sphere_coriolis(ds_mesh, alpha=alpha)
        self.write_model_dataset(ds_mesh, 'base_mesh.nc')

        ds = ds_mesh.copy()

        ds['bottomDepth'] = bottom_depth * xr.ones_like(latCell)
        ds['ssh'] = -ds.bottomDepth + h

        init_vertical_coord(config, ds)

        temperature_array = temperature * xr.ones_like(ds_mesh.latCell)
        temperature_array, _ = xr.broadcast(temperature_array, ds.refZMid)
        salinity_array = salinity * xr.ones_like(temperature_array)

        normalVelocity, _ = xr.broadcast(normalVelocity, ds.refZMid)

        ds['temperature'] = temperature_array.expand_dims(dim='Time', axis=0)
        ds['salinity'] = salinity_array.expand_dims(dim='Time', axis=0)
        ds['normalVelocity'] = normalVelocity.expand_dims(dim='Time', axis=0)

        # for visualization
        ds['velocityZonal'] = u_cell.broadcast_like(ds.temperature)
        ds['velocityMeridional'] = v_cell.broadcast_like(ds.temperature)

        self.write_initial_state_dataset(ds, 'initial_state.nc')
