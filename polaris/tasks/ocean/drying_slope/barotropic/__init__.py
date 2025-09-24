from polaris import Task
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.drying_slope.forward import Forward
from polaris.tasks.ocean.drying_slope.viz import Viz


class Barotropic(Task):
    """
    The default drying_slope test case with a sinusoidal forcing function

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km

    coord_type : str
        The type of vertical coordinate (``sigma``, ``single_layer``, etc.)

    damping_coeff : float
        The damping coefficient for the rayleigh drag option
    """

    def __init__(
        self,
        component,
        resolution,
        init,
        subdir,
        coord_type='sigma',
        drag_type='constant_and_rayleigh',
        forcing_type='tidal_cycle',
        method='ramp',
    ):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        init : polaris.tasks.ocean.drying_slope.init.Init
            A shared step for creating the initial state

        subdir : str
            The subdirectory to put the task group in

        coord_type : str, optional
            The vertical coordinate type

        forcing_type : str, optional
            The forcing type to apply at the "tidal" boundary as a namelist
            option

        method : str, optional
            The type of wetting and drying algorithm to use

        drag_type : str, optional
            The bottom drag type to apply as a namelist option
        """
        mesh_name = resolution_to_string(resolution)
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
                        component=component,
                        init=init,
                        subdir=f'{subdir}/{step_name}',
                        ntasks=None,
                        min_tasks=None,
                        openmp_threads=1,
                        name=f'{step_name}_{mesh_name}',
                        resolution=resolution,
                        forcing_type=forcing_type,
                        coord_type=coord_type,
                        drag_type=drag_type,
                        damping_coeff=damping_coeff,
                        baroclinic=False,
                        method=method,
                        graph_target=f'{init.path}/culled_graph.info',
                    )
                    symlink = None
                self.add_step(forward_step, symlink=symlink)
        else:
            self.damping_coeffs = []
            forward_step = Forward(
                component=component,
                init=init,
                indir=subdir,
                ntasks=None,
                min_tasks=None,
                openmp_threads=1,
                resolution=resolution,
                forcing_type=forcing_type,
                coord_type=coord_type,
                drag_type=drag_type,
                damping_coeff=1.0e-4,
                baroclinic=False,
                method=method,
            )
            self.add_step(forward_step)
        self.add_step(
            Viz(
                component=component,
                indir=subdir,
                damping_coeffs=self.damping_coeffs,
                baroclinic=False,
                forcing_type=forcing_type,
            )
        )

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
