import os

from polaris.analysis.publish_step import PublishStep


class MisomipPublish(PublishStep):
    """
    The step that publishes one MISOMIP analysis task's products, under
    ``<output_path>/<relative_path>``

    Attributes
    ----------
    relative_path : str
        Where the task's gallery goes within the output path, such as
        ``misomip-o4km-li1km/ocean0``

    missing : str
        The error when the task has nothing to publish, which names the
        config options it needs
    """

    def __init__(
        self, component, subdir, product_steps, relative_path, missing
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        product_steps : list of polaris.analysis.product_step.ProductStep
            The steps whose products are published

        relative_path : str
            Where the task's gallery goes within the output path

        missing : str
            The error when the task has nothing to publish
        """
        super().__init__(
            component=component,
            subdir=subdir,
            product_steps=product_steps,
            section='misomip_analysis',
        )
        self.relative_path = relative_path
        self.missing = missing

    def setup(self):
        """
        Make it an error to set up a task with nothing to publish
        """
        super().setup()
        if not self.fragment_filenames:
            raise ValueError(self.missing)

    def output_path(self):
        """
        Get the directory this task's gallery is published into

        Returns
        -------
        output_path : str
            The task's directory under ``[misomip_analysis] output_path``
        """
        return os.path.join(super().output_path(), self.relative_path)
