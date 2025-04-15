import os as os

from polaris import Task as Task
from polaris.tasks.seaice.single_column.forward import Forward as Forward
from polaris.tasks.seaice.single_column.standard_physics.viz import Viz as Viz


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
        step = Forward(component=component, indir=self.subdir)
        step.add_namelist_file(
            package='polaris.tasks.seaice.single_column.standard_physics',
            namelist='namelist.seaice',
        )
        variables = [
            'iceAreaCell',
            'iceVolumeCell',
            'snowVolumeCell',
            'surfaceTemperatureCell',
            'shortwaveDown',
            'longwaveDown',
        ]
        step.add_output_file(
            filename='output/output.2000.nc', validate_vars=variables
        )
        self.add_step(step)
        self.add_step(Viz(component=component, indir=self.subdir))
