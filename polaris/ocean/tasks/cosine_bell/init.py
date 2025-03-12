import numpy as np
import xarray as xr
from mpas_tools.transects import lon_lat_to_cartesian
from mpas_tools.vector import Vector

from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord


class Init(OceanIOStep):
    """
    A step for an initial condition for for the cosine bell test case
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

        self.add_output_file(filename='initial_state.nc')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config

        section = config['cosine_bell']
        temperature = section.getfloat('temperature')
        salinity = section.getfloat('salinity')
        lat_center = section.getfloat('lat_center')
        lon_center = section.getfloat('lon_center')
        radius = section.getfloat('radius')
        psi0 = section.getfloat('psi0')
        vel_pd = section.getfloat('vel_pd')

        section = config['vertical_grid']
        bottom_depth = section.getfloat('bottom_depth')

        ds_mesh = xr.open_dataset('mesh.nc')
        angleEdge = ds_mesh.angleEdge
        latCell = ds_mesh.latCell
        latEdge = ds_mesh.latEdge
        lonCell = ds_mesh.lonCell
        sphere_radius = ds_mesh.sphere_radius

        ds = ds_mesh.copy()

        ds['bottomDepth'] = bottom_depth * xr.ones_like(latCell)
        ds['ssh'] = xr.zeros_like(latCell)

        init_vertical_coord(config, ds)

        temperature_array = temperature * xr.ones_like(ds_mesh.latCell)
        temperature_array, _ = xr.broadcast(temperature_array, ds.refZMid)
        ds['temperature'] = temperature_array.expand_dims(dim='Time', axis=0)
        ds['salinity'] = salinity * xr.ones_like(ds.temperature)

        x_center, y_center, z_center = lon_lat_to_cartesian(
            lon_center, lat_center, sphere_radius, degrees=False
        )
        x_cells, y_cells, z_cells = lon_lat_to_cartesian(
            lonCell, latCell, sphere_radius, degrees=False
        )
        xyz_center = Vector(x_center, y_center, z_center)
        xyz_cells = Vector(x_cells, y_cells, z_cells)
        ang_dist_from_center = xyz_cells.angular_distance(xyz_center)
        distance_from_center = ang_dist_from_center * sphere_radius
        bell_value = cosine_bell(psi0, distance_from_center, radius)
        debug_tracers = xr.where(
            distance_from_center < radius, bell_value, 0.0
        )
        debug_tracers_array, _ = xr.broadcast(debug_tracers, ds.refZMid)
        ds['tracer1'] = debug_tracers_array.expand_dims(dim='Time', axis=0)
        ds['tracer2'] = ds.tracer1
        ds['tracer3'] = ds.tracer1

        # Initialize velocity
        s_per_hour = 3600.0
        velocity = (
            2.0
            * np.pi
            * np.cos(angleEdge)
            * sphere_radius
            * np.cos(latEdge)
            / (s_per_hour * vel_pd)
        )
        velocity_array, _ = xr.broadcast(velocity, ds.refZMid)
        ds['normalVelocity'] = velocity_array.expand_dims(dim='Time', axis=0)

        ds['fCell'] = xr.zeros_like(ds_mesh.xCell)
        ds['fEdge'] = xr.zeros_like(ds_mesh.xEdge)
        ds['fVertex'] = xr.zeros_like(ds_mesh.xVertex)

        self.write_model_dataset(ds, 'initial_state.nc')


def cosine_bell(max_value, ri, r):
    """
    Compute values according to cosine bell function

    Parameters
    ----------
    max_value : float
        Maximum value of the cosine bell function

    ri : np.ndarray of type float
        Distance from the center of the cosine bell in meters

    r : float
        Radius of the cosine bell in meters

    Returns
    -------
    f : np.ndarray of type float
        Cosine bell tracer values
    """
    return max_value / 2.0 * (1.0 + np.cos(np.pi * np.divide(ri, r)))
