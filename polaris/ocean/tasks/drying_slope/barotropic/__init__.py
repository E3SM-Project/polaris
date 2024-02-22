from numpy import ceil

from polaris import Task
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.drying_slope.forward import Forward
from polaris.ocean.tasks.drying_slope.init import Init
from polaris.ocean.tasks.drying_slope.viz import Viz


class Barotropic(Task):
    """
    The default drying_slope test case

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km

    coord_type : str
        The type of vertical coordinate (``sigma``, ``single_layer``, etc.)
    """

    def __init__(self, component, resolution, init, subdir,
                 coord_type='sigma',
                 drag_type='constant_and_rayleigh', forcing_type='tidal_cycle',
                 time_integrator='RK4', method='ramp'):
        """
        Create the test case

        Parameters
        ----------
        test_group : compass.ocean.tests.drying_slope.DryingSlope
            The test group that this test case belongs to

        resolution : float
            The resolution of the test case in km

        subdir : str
            TODO

        coord_type : str
            The type of vertical coordinate (``sigma``, ``single_layer``)

        method : str
            The type of wetting-and-drying algorithm
        """
        mesh_name = resolution_to_subdir(resolution)
        name = f'barotropic_{method}_{mesh_name}'
        if drag_type == 'loglaw':
            name = f'{name}_{drag_type}'
            subdir = f'{subdir}_{drag_type}'
        super().__init__(component=component, name=name, subdir=subdir)
        self.resolution = resolution
        self.coord_type = coord_type
        self.add_step(init, symlink='init')
        if drag_type == 'constant_and_rayleigh':
            self.damping_coeffs = [0.0025, 0.01]
            for damping_coeff in self.damping_coeffs:
                step_name = f'forward_{damping_coeff:03g}'
                forward_dir = f'{subdir}/{step_name}'
                if forward_dir in component.steps:
                    forward_step = component.steps[forward_dir]
                    symlink = step_name
                else:
                    forward_step = Forward(
                        component=component, init=init,
                        subdir=f'{subdir}/{step_name}',
                        ntasks=None,
                        min_tasks=None, openmp_threads=1,
                        name=f'{step_name}_{mesh_name}',
                        resolution=resolution,
                        forcing_type=forcing_type, coord_type=coord_type,
                        time_integrator=time_integrator, drag_type=drag_type,
                        damping_coeff=damping_coeff, baroclinic=False,
                        method=method)
                    symlink = None
                self.add_step(forward_step, symlink=symlink)
        else:
            self.damping_coeffs = []
            forward_step = Forward(
                component=component, init=init, indir=subdir, ntasks=None,
                min_tasks=None, openmp_threads=1, resolution=resolution,
                forcing_type=forcing_type, coord_type=coord_type,
                time_integrator=time_integrator, drag_type=drag_type,
                damping_coeff=1.0e-4, baroclinic=False,
                method=method)
            self.add_step(forward_step)
        self.add_step(
            Viz(component=component, indir=subdir,
                damping_coeffs=self.damping_coeffs,
                baroclinic=False, forcing_type=forcing_type))

    # def validate(self):
    #     """
    #     Validate variables against a baseline
    #     """
    #     damping_coeffs = self.damping_coeffs
    #     variables = ['layerThickness', 'normalVelocity']
    #     if damping_coeffs is not None:
    #         for damping_coeff in damping_coeffs:
    #             compare_variables(test_case=self, variables=variables,
    #                               filename1=f'forward_{damping_coeff}/'
    #                                         'output.nc')
    #     else:
    #         compare_variables(test_case=self, variables=variables,
    #                           filename1='forward/output.nc')
