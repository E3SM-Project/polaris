import os

from polaris import Task
from polaris.ocean.tasks.single_column.forward import Forward
from polaris.ocean.tasks.single_column.init import Init
from polaris.ocean.tasks.single_column.viz import Viz


class IdealAge(Task):
    """
    The ideal-age single-column test case creates the mesh and initial
    condition, then performs a short forward run evolving the ideal-age tracer
    on 1 core.
    """
    def __init__(self, component, ideal_age=True):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'ideal_age'
        subdir = os.path.join('single_column', name)
        super().__init__(component=component, name=name,
                         subdir=subdir)
        self.add_step(
            Init(component=component, indir=self.subdir, ideal_age=ideal_age))

        validate_vars = ['temperature', 'salinity', 'iAge']
        step = Forward(component=component, indir=self.subdir, ntasks=1,
                       min_tasks=1, openmp_threads=1,
                       validate_vars=validate_vars)

        step.add_yaml_file('polaris.ocean.tasks.single_column.ideal_age',
                           'forward.yaml')

        self.add_step(step)

        self.add_step(
            Viz(component=component, indir=self.subdir, ideal_age=ideal_age))

    def configure(self):
        """
        Add the config file common to single-column tests
        """
        self.config.add_from_package(
            'polaris.ocean.tasks.single_column',
            'single_column.cfg')
