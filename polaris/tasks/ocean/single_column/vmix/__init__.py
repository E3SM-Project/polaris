from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.viz import Viz
from polaris.tasks.ocean.single_column.vmix.analysis import Analysis


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
        self.add_step(
            Forward(
                component=component,
                indir=f'{indir}/{name}',
                name='forward_kpp',
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name='vmix',
                enable_vadv=False,
            ),
        )
        self.add_step(
            Forward(
                component=component,
                indir=f'{indir}/{name}',
                name='forward_pp',
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name='vmix',
                enable_vadv=False,
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
                    'kpp': '../forward_kpp_no_vadv',
                    'pp': '../forward_pp_no_vadv',
                },
                variables={
                    'temperature': 'degC',
                    'salinity': 'PSU',
                    'velocity': 'm s$^{-1}$',
                    'RiTopOfCell': '',
                    'BruntVaisalaFreqTop': '$s^{-2}$',
                },
            )
        )

        self.add_step(
            Analysis(
                component=component,
                indir=f'{indir}/{name}',
                comparisons={
                    'kpp': '../forward_kpp_no_vadv',
                    'pp': '../forward_pp_no_vadv',
                },
            )
        )
