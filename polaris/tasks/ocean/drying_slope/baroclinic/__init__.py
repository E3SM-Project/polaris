from polaris import Task
from polaris.tasks.ocean.drying_slope.forward import Forward
from polaris.tasks.ocean.drying_slope.viz import Viz


class Baroclinic(Task):
    """
    The baroclinic version of the drying slope test case creates the mesh
    and initial condition, then performs a short forward run on 4 cores.

    Attributes
    ----------
    coord_type : str, optional
        The vertical coordinate type

    config : polaris.config.PolarisConfigParser
        A shared config parser
    """

    def __init__(
        self,
        component,
        resolution,
        init,
        subdir,
        coord_type='sigma',
        forcing_type='linear_drying',
        method='ramp',
        drag_type='constant_and_rayleigh',
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
        name = f'baroclinic_{method}'
        if drag_type == 'loglaw':
            name = f'{name}_{drag_type}'
            subdir = f'{subdir}_{drag_type}'
        super().__init__(component=component, name=name, subdir=subdir)
        self.coord_type = coord_type

        self.add_step(init, symlink='init')
        self.add_step(
            Forward(
                component=component,
                init=init,
                indir=subdir,
                subdir=None,
                ntasks=None,
                min_tasks=None,
                openmp_threads=1,
                resolution=resolution,
                forcing_type=forcing_type,
                coord_type=coord_type,
                drag_type=drag_type,
                damping_coeff=1.0e-4,
                baroclinic=True,
                method=method,
            )
        )

        self.add_step(
            Viz(
                component=component,
                indir=subdir,
                subdir=None,
                damping_coeffs=None,
                baroclinic=True,
                forcing_type=forcing_type,
            )
        )

    def configure(self):
        """
        Change config options as needed
        """
        config = self.config
        hmin = config.getfloat(
            'drying_slope_baroclinic', 'min_column_thickness'
        )
        nz = config.getint('vertical_grid', 'vert_levels')
        self.config.set(
            'drying_slope',
            'thin_film_thickness',
            f'{hmin / nz}',
            comment='Thickness of each layer in the thin film region',
        )
