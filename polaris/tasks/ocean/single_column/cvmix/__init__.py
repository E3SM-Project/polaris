import os

from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.viz import Viz


class CVMix(Task):
    """
    The CVMix single-column test case creates the mesh and initial condition,
    then performs a short forward run testing vertical mixing on 1 core.
    """

    def __init__(self, component, config, init, indir, enable_vadv=True):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'cvmix'
        if not enable_vadv:
            subdir = os.path.join(indir, f'{name}_no_vadv')
        else:
            subdir = os.path.join(indir, name)
        super().__init__(component=component, name=name, subdir=subdir)
        config_filename = 'cvmix.cfg'
        self.set_shared_config(config, link=config_filename)
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.cvmix', config_filename
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
                indir=subdir,
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name=name,
                # enable_vadv=enable_vadv,
            )
        )

        self.add_step(
            Viz(component=component, indir=subdir),
            run_by_default=False,
        )
