import os

from polaris.analysis.publish_step import PublishStep


class MisomipPublish(PublishStep):
    """
    The step that publishes one experiment's products, under
    ``<output_path>/<mesh_name>/<experiment>``

    Attributes
    ----------
    mesh_name : str
        The pair of meshes

    experiment : str
        The experiment

    runs_option : str
        The config options that name the experiment's runs, for the error
        when there are none
    """

    def __init__(
        self,
        component,
        subdir,
        product_steps,
        mesh_name,
        experiment,
        runs_option,
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

        mesh_name : str
            The pair of meshes

        experiment : str
            The experiment

        runs_option : str
            The config options that name the experiment's runs
        """
        super().__init__(
            component=component,
            subdir=subdir,
            product_steps=product_steps,
            section='misomip_analysis',
        )
        self.mesh_name = mesh_name
        self.experiment = experiment
        self.runs_option = runs_option

    def setup(self):
        """
        Make it an error to set up an experiment with no runs to analyze
        """
        super().setup()
        if not self.fragment_filenames:
            raise ValueError(
                f'No runs of {self.experiment} on {self.mesh_name} are '
                f'configured.  Set {self.runs_option}.'
            )

    def output_path(self):
        """
        Get the directory this experiment's gallery is published into

        Returns
        -------
        output_path : str
            The experiment's directory under ``[misomip_analysis]
            output_path``
        """
        return os.path.join(
            super().output_path(), self.mesh_name, self.experiment
        )
