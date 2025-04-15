import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.geostrophic.exact_solution import (
    compute_exact_solution,
)


class Init(Step):
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

        omega = 2 * np.pi / constants['SHR_CONST_SDAY']

        section = config['vertical_grid']
        bottom_depth = section.getfloat('bottom_depth')

        ds_mesh = xr.open_dataset('mesh.nc')
        latCell = ds_mesh.latCell
        lonCell = ds_mesh.lonCell
        latEdge = ds_mesh.latEdge
        lonEdge = ds_mesh.lonEdge
        latVertex = ds_mesh.latVertex
        lonVertex = ds_mesh.lonVertex

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

        ds['fCell'] = _coriolis(lonCell, latCell, alpha, omega)
        ds['fEdge'] = _coriolis(lonEdge, latEdge, alpha, omega)
        ds['fVertex'] = _coriolis(lonVertex, latVertex, alpha, omega)

        # for visualization
        ds['velocityZonal'] = u_cell.broadcast_like(ds.temperature)
        ds['velocityMeridional'] = v_cell.broadcast_like(ds.temperature)

        write_netcdf(ds, 'initial_state.nc')


def _coriolis(lon, lat, alpha, omega):
    f = (
        2
        * omega
        * (
            -np.cos(lon) * np.cos(lat) * np.sin(alpha)
            + np.sin(lat) * np.cos(alpha)
        )
    )
    return f
