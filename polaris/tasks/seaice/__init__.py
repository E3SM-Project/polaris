from polaris import Component


class SeaIce(Component):
    """
    The collection of all tasks for the MPAS-Seaice core
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Seaice test cases
        """
        super().__init__(name='seaice')

    def configure(self, config, steps):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            the config options for this component, to modify

        steps : list of polaris.Step
            The steps this component owns among those being set up.  These may
            belong to tasks in another component.
        """
        model = config.get('seaice', 'model')

        configs = {'mpas-seaice': 'mpas_seaice.cfg'}

        if model not in configs:
            raise ValueError(f'Unknown sea-ice model {model}')

        config.add_from_package('polaris.seaice', configs[model])


# create a single module-level instance available to other components
seaice = SeaIce()
