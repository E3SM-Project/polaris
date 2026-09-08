from polaris import Task
from polaris.tasks.ocean.single_column.conservation_summary import (
    ConservationSummary,
)
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.frazil.init import FrazilInit
from polaris.tasks.ocean.single_column.viz import Viz


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

    def __init__(self, component, subdir, case, frazil_type):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        subdir : str
            The directory the task is in

        case : str
            The initial condition/forcing case, either ``'melting'`` or
            ``'freezing'``

        frazil_type : str
            The frazil algorithm used in Omega, either ``'basic'`` or
            ``'teos'``
        """
        name = f'{case}_{frazil_type}'
        super().__init__(component=component, name=name, subdir=subdir)
        self.case = case
        self.frazil_type = frazil_type

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.frazil', 'frazil.cfg'
        )
        if frazil_type == 'basic':
            self.config.add_from_package('polaris.ocean.eos', 'linear.cfg')
        init_step = FrazilInit(
            component=component,
            subdir=f'{subdir}/init',
            case=case,
        )
        self.add_step(init_step)

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        forward_step = Forward(
            component=component,
            init=init_step,
            indir=subdir,
            name='forward',
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
            validate_vars=validate_vars,
            task_name='frazil',
            task_package='polaris.tasks.ocean.single_column.frazil',
            frazil_type=frazil_type,
        )
        self.add_step(forward_step)
        self.add_step(
            ConservationSummary(
                component=component,
                indir=subdir,
                forward_steps={forward_step.name: forward_step.path},
            )
        )
        self.add_step(
            Viz(
                component=component,
                indir=subdir,
                init=init_step,
            ),
            run_by_default=False,
        )
