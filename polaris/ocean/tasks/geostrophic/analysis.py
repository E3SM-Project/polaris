import xarray as xr

from polaris.ocean.convergence import ConvergenceAnalysis
from polaris.ocean.tasks.geostrophic.exact_solution import (
    compute_exact_solution,
)


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the geostrophic test case
    """
    def __init__(self, component, resolutions, subdir, dependencies):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        convergence_vars = [{'name': 'h',
                             'title': 'water-column thickness',
                             'zidx': None},
                            {'name': 'normalVelocity',
                             'title': 'normal velocity',
                             'zidx': 0}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
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

        if field_name not in ['h', 'normalVelocity']:
            print(f'Variable {field_name} not available as an analytic '
                  'solution for the geostrophic test case')

        config = self.config

        section = config['geostrophic']
        alpha = section.getfloat('alpha')
        vel_period = section.getfloat('vel_period')
        gh_0 = section.getfloat('gh_0')

        mesh_filename = f'{mesh_name}_mesh.nc'

        h, _, _, normalVelocity = compute_exact_solution(
            alpha, vel_period, gh_0, mesh_filename)

        if field_name == 'h':
            return h
        else:
            return normalVelocity

    def get_output_field(self, mesh_name, field_name, time, zidx=None):
        """
        Get the model output field at the given time and z index

        Parameters
        ----------
        mesh_name : str
            The mesh name which is the prefix for the output file

        field_name : str
            The name of the variable of which we evaluate convergence

        time : float
            The time at which to evaluate the exact solution in seconds

        zidx : int, optional
            The z-index for the vertical level to take the field from

        Returns
        -------
        field_mpas : xarray.DataArray
            model output field
        """

        if field_name not in ['h', 'normalVelocity']:
            print(f'Variable {field_name} not available for analysis in the '
                  f'geostrophic test case')

        if field_name == 'normalVelocity':
            return super().get_output_field(mesh_name=mesh_name,
                                            field_name=field_name,
                                            time=time, zidx=zidx)
        else:
            ds_init = xr.open_dataset(f'{mesh_name}_init.nc')
            bottom_depth = ds_init.bottomDepth
            ssh = super().get_output_field(mesh_name=mesh_name,
                                           field_name='ssh',
                                           time=time, zidx=None)
            h = ssh + bottom_depth
            return h

    def convergence_parameters(self, field_name=None):
        """
        Get convergence parameters

        Parameters
        ----------
        field_name : str
            The name of the variable of which we evaluate convergence
            For cosine_bell, we use the same convergence rate for all fields
        Returns
        -------
        conv_thresh: float
            The minimum convergence rate

        conv_thresh: float
            The maximum convergence rate
        """
        config = self.config
        conv_thresh = config.getfloat('geostrophic',
                                      f'convergence_thresh_{field_name}')
        error_type = config.get('convergence', 'error_type')

        return conv_thresh, error_type
