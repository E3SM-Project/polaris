import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):
    """
    A step for an initial condition for for the external gravity wave test case
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
            work_dir_target=f'{base_mesh.path}/base_mesh.nc')

        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{base_mesh.path}/graph.info')

        self.add_output_file(filename='initial_state.nc')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config

        section = config['gaussian_bump']
        temperature = section.getfloat('temperature')
        salinity = section.getfloat('salinity')
        lat_center = section.getfloat('lat_center')
        lon_center = section.getfloat('lon_center')

        section = config['vertical_grid']
        bottom_depth = section.getfloat('bottom_depth')

        ds_mesh = xr.open_dataset('mesh.nc')
        latCell = ds_mesh.latCell
        latEdge = ds_mesh.latEdge
        lonCell = ds_mesh.lonCell

        ds = ds_mesh.copy()

        ds['bottomDepth'] = bottom_depth * xr.ones_like(latCell)
        ds['ssh'] = xr.zeros_like(latCell)

        init_vertical_coord(config, ds)

        temperature_array = temperature * xr.ones_like(ds_mesh.latCell)
        temperature_array, _ = xr.broadcast(temperature_array, ds.refZMid)
        ds['temperature'] = temperature_array.expand_dims(dim='Time', axis=0)
        ds['salinity'] = salinity * xr.ones_like(ds.temperature)

        # Initialize layer thickness
        gaussian_bump_value = gaussian_bump(lat_center, lon_center,
                                            latCell, lonCell)
        thickness_array, _ = xr.broadcast(gaussian_bump_value + bottom_depth,
                                          ds.refZMid)
        ds['layerThickness'] = thickness_array.expand_dims(dim='Time', axis=0)

        # Initialize velocity
        velocity = xr.zeros_like(latEdge)
        velocity_array, _ = xr.broadcast(velocity, ds.refZMid)
        ds['normalVelocity'] = velocity_array.expand_dims(dim='Time', axis=0)

        ds['fCell'] = xr.zeros_like(ds_mesh.xCell)
        ds['fEdge'] = xr.zeros_like(ds_mesh.xEdge)
        ds['fVertex'] = xr.zeros_like(ds_mesh.xVertex)

        write_netcdf(ds, 'initial_state.nc')


def gaussian_bump(lat_center, lon_center, latCell, lonCell):
    """
    Compute values according to gaussian bump function

    Parameters
    ----------
    lat_center : float
        Latitude of the center of the gaussian bump

    lon_center : float
        Longitude of the center of the gaussian bump

    latCell : np.ndarray of type float
        Latitude of mesh cells

    lonCell : np.ndarray of type float
        Longitude of mesh cells

    Returns
    -------
    f : np.ndarray of type float
        Gaussian bump values for ssh
    """
    bump_value = np.exp(-100 * ((latCell - lat_center)**2 +
                                (lonCell - lon_center)**2))

    return bump_value
