from polaris import Component
from polaris.ocean.tests.baroclinic_channel import BaroclinicChannel
from polaris.ocean.tests.global_convergence import GlobalConvergence
from polaris.ocean.tests.inertial_gravity_wave import InertialGravityWave
from polaris.ocean.tests.single_column import SingleColumn


class Ocean(Component):
    """
    The collection of all test case for the MPAS-Ocean core
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='ocean')

        # please keep these in alphabetical order
        self.add_test_group(BaroclinicChannel(component=self))
        self.add_test_group(GlobalConvergence(component=self))
        self.add_test_group(InertialGravityWave(component=self))
        self.add_test_group(SingleColumn(component=self))

    def configure(self, config):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify
        """
        section = config['ocean']
        model = section.get('model')
        configs = {'mpas-ocean': 'mpas_ocean.cfg',
                   'omega': 'omega.cfg'}
        if model not in configs:
            raise ValueError(f'Unknown ocean model {model} in config options')

        config.add_from_package('polaris.ocean', configs[model])
