import numpy as np
import xarray as xr
from mpas_tools.transects import lon_lat_to_cartesian
from mpas_tools.vector import Vector

from polaris.ocean.convergence.spherical import SphericalConvergenceAnalysis
from polaris.ocean.tasks.cosine_bell.init import cosine_bell


class Analysis(SphericalConvergenceAnalysis):
    """
    A step for analyzing the output from the cosine bell test case
    """
    def __init__(self, component, resolutions, icosahedral, subdir,
                 dependencies):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        convergence_vars = [{'name': 'tracer1',
                             'title': 'tracer1',
                             'zidx': 0}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         icosahedral=icosahedral,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars)

    def exact_solution(self, mesh_name, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        mesh_name : str
            The mesh name which is the prefix for the initial condition file

        field_name : str
            The name of the variable of which we evaluate convergence
            For the default method, we use the same convergence rate for all
            fields

        time : float
            The time at which to evaluate the exact solution in seconds.
            For the default method, we always use the initial state.

        zidx : int, optional
            The z-index for the vertical level at which to evaluate the exact
            solution

        Returns
        -------
        solution: xarray.DataArray
            The exact solution with dimension nCells
        """

        if field_name != 'tracer1':
            print(f'Variable {field_name} not available as an analytic '
                  'solution for the cosine_bell test case')

        config = self.config
        lat_center = config.getfloat('cosine_bell', 'lat_center')
        lon_center = config.getfloat('cosine_bell', 'lon_center')
        radius = config.getfloat('cosine_bell', 'radius')
        psi0 = config.getfloat('cosine_bell', 'psi0')
        vel_pd = config.getfloat('cosine_bell', 'vel_pd')

        ds_mesh = xr.open_dataset(f'{mesh_name}_mesh.nc')
        sphere_radius = ds_mesh.sphere_radius

        ds_init = xr.open_dataset(f'{mesh_name}_init.nc')
        latCell = ds_init.latCell.values
        lonCell = ds_init.lonCell.values

        # distance that the cosine bell center traveled in radians
        # based on equatorial velocity
        distance = 2.0 * np.pi * time / (86400.0 * vel_pd)

        # new location of blob center
        lon_new = lon_center + distance
        if lon_new > 2.0 * np.pi:
            lon_new -= 2.0 * np.pi

        x_center, y_center, z_center = lon_lat_to_cartesian(
            lon_new, lat_center, sphere_radius, degrees=False)
        x_cells, y_cells, z_cells = lon_lat_to_cartesian(
            lonCell, latCell, sphere_radius, degrees=False)
        xyz_center = Vector(x_center, y_center, z_center)
        xyz_cells = Vector(x_cells, y_cells, z_cells)
        ang_dist_from_center = xyz_cells.angular_distance(xyz_center)
        distance_from_center = ang_dist_from_center * sphere_radius

        bell_value = cosine_bell(psi0, distance_from_center, radius)
        tracer1 = np.where(distance_from_center < radius,
                           bell_value,
                           0.0)
        return xr.DataArray(data=tracer1, dims=('nCells',))
