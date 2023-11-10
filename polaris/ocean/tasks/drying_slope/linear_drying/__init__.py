from polaris import Task
from polaris.ocean.tasks.drying_slope.forward import Forward
from polaris.ocean.tasks.drying_slope.init import Init
from polaris.ocean.tasks.drying_slope.viz import Viz


class LinearDrying(Task):
    """
    The linear drying version of the drying slope test case creates the mesh
    and initial condition, then performs a short forward run on 4 cores.
    """

    def __init__(self, component, resolution, indir, coord_type='sigma',
                 drag_type='constant_and_rayleigh',
                 time_integrator='split_explicit'):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        resolution : float
            The resolution of the test case in km

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.ocean.tasks.drying_slope.init.Init
            A shared step for creating the initial state
        """
        self.coord_type = coord_type
        super().__init__(component=component, name='linear_drying',
                         indir=indir)

        self.add_step(
            Init(component=component, indir=self.subdir, resolution=resolution,
                 baroclinic=True, drag_type=drag_type))

        self.add_step(
            Forward(component=component, indir=self.subdir, ntasks=None,
                    min_tasks=None, openmp_threads=1, resolution=resolution,
                    forcing_type='linear_drying', coord_type=coord_type,
                    time_integrator=time_integrator, drag_type=drag_type,
                    damping_coeff=1.0e-4, baroclinic=True))

        self.add_step(
            Viz(component=component, indir=self.subdir, damping_coeffs=None,
                baroclinic=True, forcing_type='linear'))

    def configure(self):
        """
        Change config options as needed
        """
        right_bottom_depth = 2.5
        lx = 6.
        ly_analysis = 50.
        y_buffer = 5.
        ly = ly_analysis + y_buffer

        hmin = 0.5  # water-column thickness in thin film region
        nz = self.config.getint('vertical_grid', 'vert_levels')
        self.config.set(
            'drying_slope', 'thin_film_thickness', f'{hmin / nz}',
            comment='Thickness of each layer in the thin film region')

        self.config.set('drying_slope', 'right_bottom_depth',
                        f'{right_bottom_depth}')
        self.config.set(
            'drying_slope', 'right_tidal_height', '0.',
            comment='Initial tidal height at the right side of the domain')
        self.config.set('vertical_grid', 'bottom_depth',
                        str(right_bottom_depth))
        self.config.set(
            'drying_slope', 'ly_analysis', f'{ly_analysis}',
            comment='Length over which wetting and drying actually occur')
        self.config.set(
            'drying_slope', 'ly', f'{ly}',
            comment='Domain length in the along-slope direction')
        self.config.set(
            'drying_slope', 'lx', f'{lx}',
            comment='Domain width in the across-slope direction')

        self.config.set('vertical_grid', 'coord_type', self.coord_type)
