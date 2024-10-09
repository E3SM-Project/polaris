import xarray as xr

from polaris.ocean.convergence.analysis import ConvergenceAnalysis
from polaris.ocean.tasks.geostrophic.exact_solution import (
    compute_exact_solution,
)


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the geostrophic test case
    """
    def __init__(self, component, subdir, dependencies, refinement='both'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step

        refinement : str, optional
            Whether to refine in space, time or both space and time
        """
        convergence_vars = [{'name': 'h',
                             'title': 'water-column thickness',
                             'zidx': None},
                            {'name': 'normalVelocity',
                             'title': 'normal velocity',
                             'zidx': 0}]
        super().__init__(component=component, subdir=subdir,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars,
                         refinement=refinement)

    def exact_solution(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        refinement_factor : float
            The factor by which to scale space, time or both

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

        mesh_filename = f'mesh_r{refinement_factor:02g}.nc'

        h, _, _, normalVelocity = compute_exact_solution(
            alpha, vel_period, gh_0, mesh_filename)

        if field_name == 'h':
            return h
        else:
            return normalVelocity

    def get_output_field(self, refinement_factor, field_name, time, zidx=None):
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
            return super().get_output_field(
                refinement_factor=refinement_factor,
                field_name=field_name, time=time, zidx=zidx)
        else:
            ds_init = xr.open_dataset(f'init_r{refinement_factor:02g}.nc')
            bottom_depth = ds_init.bottomDepth
            ssh = super().get_output_field(
                refinement_factor=refinement_factor,
                field_name='ssh', time=time, zidx=None)
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
