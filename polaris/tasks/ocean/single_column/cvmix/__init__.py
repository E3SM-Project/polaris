import os

from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.init import Init
from polaris.tasks.ocean.single_column.viz import Viz


class CVMix(Task):
    """
    The CVMix single-column test case creates the mesh and initial condition,
    then performs a short forward run testing vertical mixing on 1 core.
    """

    def __init__(self, component):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'cvmix'
        subdir = os.path.join('single_column', name)
        super().__init__(component=component, name=name, subdir=subdir)
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
            )
        )

        self.add_step(Viz(component=component, indir=self.subdir))

        self.config.add_from_package(
            'polaris.tasks.ocean.single_column', 'single_column.cfg'
        )
