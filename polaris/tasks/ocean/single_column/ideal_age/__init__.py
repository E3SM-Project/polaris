import os

from polaris import Task as Task
from polaris.tasks.ocean.single_column.forward import Forward as Forward
from polaris.tasks.ocean.single_column.viz import Viz as Viz


class IdealAge(Task):
    """
    The ideal-age single-column test case creates the mesh and initial
    condition, then performs a short forward run evolving the ideal-age tracer
    on 1 core.
    """

    def __init__(self, component, config, init, indir, ideal_age=True):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'ideal_age'
        subdir = os.path.join(indir, name)
        super().__init__(component=component, name=name, subdir=subdir)
        config_filename = 'ideal_age.cfg'
        self.set_shared_config(config, link=config_filename)
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.ideal_age', config_filename
        )
        self.add_step(init, symlink='init')

        validate_vars = ['temperature', 'salinity', 'iAge']
        step = Forward(
            component=component,
            indir=self.subdir,
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
            validate_vars=validate_vars,
            task_name=name,
        )

        self.add_step(step)

        self.add_step(
            Viz(
                component=component,
                indir=self.subdir,
                ideal_age=ideal_age,
            ),
            run_by_default=False,
        )
