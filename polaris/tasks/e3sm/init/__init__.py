from polaris.component import Component


class E3smInit(Component):
    """
    The e3sm/init component, which makes topography and other inputs for E3SM
    components that tasks from other components use as well
    """

    def __init__(self):
        """
        Create the component
        """
        super().__init__(name='e3sm/init')

    def configure(self, config, steps):
        """
        Point the steps that remap topography at the combined topography for
        the Antarctic dataset in ``[remap_topography] antarctic_dataset``.

        Tasks are built with the default dataset before a user's config file
        is read, so this is where a user's choice takes effect, before any
        task is configured or step set up.

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            The config options for this component, including those from the
            user's config file

        steps : list of polaris.Step
            The steps this component owns among those being set up
        """
        # imported here because the remap steps import e3sm_init
        from polaris.tasks.e3sm.init.topo.antarctic_dataset import (
            get_antarctic_dataset,
            select_antarctic_dataset,
        )

        select_antarctic_dataset(
            component=self,
            steps=steps,
            antarctic_dataset=get_antarctic_dataset(config),
        )


# create a single module-level instance available to other components
e3sm_init = E3smInit()
