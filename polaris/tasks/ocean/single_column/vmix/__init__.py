from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.viz import Viz


class VMix(Task):
    """
    The VMix single-column test case creates the mesh and initial condition,
    then performs a short forward run testing vertical mixing on 1 core.
    """

    def __init__(self, component, config, init, indir, name='vmix'):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        super().__init__(component=component, name=name, indir=indir)
        config_filename = 'vmix.cfg'
        self.set_shared_config(config, link=config_filename)
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.vmix', config_filename
        )
        self.add_step(init, symlink='init')

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        for enable_vadv in [True, False]:
            self.add_step(
                Forward(
                    component=component,
                    indir=f'{indir}/{name}',
                    ntasks=1,
                    min_tasks=1,
                    openmp_threads=1,
                    validate_vars=validate_vars,
                    task_name='vmix',
                    enable_vadv=enable_vadv,
                )
            )
        self.add_step(
            Forward(
                component=component,
                indir=f'{indir}/{name}',
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name='vmix',
                constant_diff=True,
                enable_vadv=False,
            )
        )

        self.add_step(
            Viz(
                component=component,
                indir=f'{indir}/{name}',
                comparisons={
                    'control': '../forward',
                    'no_vadv': '../forward_no_vadv',
                    'constant': '../forward_no_vadv_constant',
                },
            ),
            run_by_default=False,
        )
