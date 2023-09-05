from polaris import Task
from polaris.ocean.tasks.inertial_gravity_wave.analysis import Analysis
from polaris.ocean.tasks.inertial_gravity_wave.forward import Forward
from polaris.ocean.tasks.inertial_gravity_wave.init import Init
from polaris.ocean.tasks.inertial_gravity_wave.viz import Viz
from polaris.validate import compare_variables


class Convergence(Task):
    """
    The convergence test case for inertial gravity waves
    """

    def __init__(self, component):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to
        """
        name = 'convergence'
        subdir = f'inertial_gravity_wave/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        self.resolutions = [200, 100, 50, 25]
        for res in self.resolutions:
            self.add_step(Init(task=self, resolution=res))
            self.add_step(Forward(task=self, resolution=res))

        self.add_step(Analysis(task=self, resolutions=self.resolutions))
        self.add_step(Viz(task=self, resolutions=self.resolutions),
                      run_by_default=False)

    def configure(self):
        """
        Add the config file common to inertial gravity wave tests
        """
        self.config.add_from_package(
            'polaris.ocean.tasks.inertial_gravity_wave',
            'inertial_gravity_wave.cfg')

    def validate(self):
        """
        Compare ``layerThickness`` and ``normalVelocity`` in the ``forward``
        step with a baseline if one was provided.
        """
        super().validate()
        variables = ['layerThickness', 'normalVelocity']
        for res in self.resolutions:
            compare_variables(task=self, variables=variables,
                              filename1=f'{res}km/forward/output.nc')
