from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward


class Frazil(Task):
    """
    A single-column frazil test case that creates the mesh and initial
    condition for a given melting/freezing case, then performs a forward
    run with a given frazil algorithm (``'basic'`` or ``'teos'``).

    Attributes
    ----------
    case : str
        The initial condition/forcing case, either ``'melting'`` or
        ``'freezing'``

    frazil_type : str
        The frazil algorithm used in Omega, either ``'basic'`` or ``'teos'``
    """

    def __init__(self, component, config, init, indir, case, frazil_type):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            The config options for this task

        init : polaris.tasks.ocean.single_column.frazil.init.FrazilInit
            The shared step for creating the mesh and initial condition

        indir : str
            The directory the task is in

        case : str
            The initial condition/forcing case, either ``'melting'`` or
            ``'freezing'``

        frazil_type : str
            The frazil algorithm used in Omega, either ``'basic'`` or
            ``'teos'``
        """
        name = f'frazil_{case}_{frazil_type}'
        super().__init__(component=component, name=name, indir=indir)
        self.case = case
        self.frazil_type = frazil_type

        config_filename = f'{name}.cfg'
        self.set_shared_config(config, link=config_filename)

        self.add_step(init, symlink='init')

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        self.add_step(
            Forward(
                component=component,
                init=init,
                indir=f'{indir}/{name}',
                name='forward',
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name='frazil',
                task_package='polaris.tasks.ocean.single_column.frazil',
                frazil_type=frazil_type,
            ),
        )
