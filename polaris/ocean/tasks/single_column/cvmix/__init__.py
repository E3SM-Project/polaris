import os

from polaris import Task
from polaris.ocean.tasks.single_column.forward import Forward
from polaris.ocean.tasks.single_column.init import Init
from polaris.ocean.tasks.single_column.viz import Viz
from polaris.validate import compare_variables


class CVMix(Task):
    """
    The CVMix single-column test case creates the mesh and initial condition,
    then performs a short forward run testing vertical mixing on 1 core.
    """
    def __init__(self, component, resolution):
        """
        Create the test case
        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'cvmix'
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join('single_column', res_str, name)
        super().__init__(component=component, name=name,
                         subdir=subdir)
        self.add_step(
            Init(task=self, resolution=resolution))

        self.add_step(
            Forward(task=self, ntasks=1, min_tasks=1,
                    openmp_threads=1))

        self.add_step(
            Viz(task=self))

    def configure(self):
        """
        Add the config file common to single-column tests
        """
        self.config.add_from_package(
            'polaris.ocean.tasks.single_column',
            'single_column.cfg')

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, ``layerThickness`` and
        ``normalVelocity`` in the ``forward`` step with a baseline if one was
        provided.
        """
        super().validate()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        compare_variables(task=self, variables=variables,
                          filename1='forward/output.nc')
