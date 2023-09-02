import os

from polaris import Task
from polaris.seaice.tasks.single_column.forward import Forward
from polaris.seaice.tasks.single_column.standard_physics.viz import Viz
from polaris.validate import compare_variables


class StandardPhysics(Task):
    """
    The single-column standard physics test case creates the mesh and initial
    condition, then performs a short forward run.
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.seaice.Seaice
            the component that that the task belongs to
        """
        name = 'standard_physics'
        subdir = os.path.join('single_column', name)
        super().__init__(component=component, name=name, subdir=subdir)
        step = Forward(task=self)
        step.add_namelist_file(
            package='polaris.seaice.tasks.single_column.standard_physics',
            namelist='namelist.seaice')
        step.add_output_file(filename='output/output.2000.nc')
        self.add_step(step)
        self.add_step(Viz(task=self))

    def validate(self):
        """
        Compare six output variables in the ``forward`` step
        with a baseline if one was provided.
        """
        super().validate()

        variables = ['iceAreaCell', 'iceVolumeCell', 'snowVolumeCell',
                     'surfaceTemperatureCell', 'shortwaveDown', 'longwaveDown']
        compare_variables(task=self, variables=variables,
                          filename1='forward/output/output.2000.nc')
