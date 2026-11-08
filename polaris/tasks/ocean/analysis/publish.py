from polaris.analysis.publish_step import PublishStep


class Publish(PublishStep):
    """
    The step that publishes the ocean analysis's products, with its options
    in ``[ocean_analysis]``
    """

    def __init__(self, component, subdir, product_steps):
        """
        Create the publish step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        product_steps : list of polaris.Step
            The steps that make products, each of which becomes a dependency
        """
        super().__init__(
            component=component,
            subdir=subdir,
            product_steps=product_steps,
            section='ocean_analysis',
        )
