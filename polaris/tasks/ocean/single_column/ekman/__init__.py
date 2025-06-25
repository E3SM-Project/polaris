import os

from polaris import Task
from polaris.tasks.ocean.single_column.ekman.analysis import Analysis
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.init import Init
from polaris.tasks.ocean.single_column.viz import Viz


class Ekman(Task):
    """
    The Ekman single-column test case creates the mesh and initial condition,
    then performs a short forward run spinning up an ekman layer on 1 core.
    """

    def __init__(self, component):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'ekman'
        subdir = os.path.join('single_column', name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.ekman', 'ekman.cfg'
        )

        self.add_step(Init(component=component, indir=self.subdir))

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]
        self.add_step(
            Forward(
                component=component,
                indir=self.subdir,
                ntasks=1,
                min_tasks=1,
                openmp_threads=1,
                validate_vars=validate_vars,
                task_name=name,
            )
        )

        self.add_step(Analysis(component=component, indir=self.subdir))

        self.add_step(
            Viz(component=component, indir=self.subdir),
            run_by_default=False,
        )
