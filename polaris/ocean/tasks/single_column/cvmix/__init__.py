import os

from polaris import Task
from polaris.ocean.tasks.single_column.forward import Forward
from polaris.ocean.tasks.single_column.init import Init
from polaris.ocean.tasks.single_column.viz import Viz
from polaris.validate import compare_variables


class CVMix(Task):
    """
    The default test case for the single column test group simply creates
    the mesh and initial condition, then performs a short forward run on 4
    cores.
    """
    def __init__(self, test_group, resolution):
        """
        Create the test case
        Parameters
        ----------
        test_group : polaris.ocean.tasks.single_column.SingleColumn
            The test group that this test case belongs to
        """
        name = 'cvmix'
        self.resolution = resolution
        if resolution >= 1.:
            res_str = f'{resolution:g}km'
        else:
            res_str = f'{resolution * 1000.:g}m'
        subdir = os.path.join(res_str, name)
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)
        self.add_step(
            Init(task=self, resolution=resolution))

        self.add_step(
            Forward(task=self, ntasks=1, min_tasks=1,
                    openmp_threads=1))

        self.add_step(
            Viz(task=self))

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
