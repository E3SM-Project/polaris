import os

from polaris.ocean.model import OceanIOStep
from polaris.validate import compare_variables


class Validate(OceanIOStep):
    """
    A step for comparing outputs between steps in a cosine bell run

    Attributes
    ----------
    step_subdirs : list of str
        The number of processors used in each run
    """

    def __init__(self, component, step_subdirs, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        step_subdirs : list of str
            Subdirectories for the steps with outputs to compare

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.step_subdirs = step_subdirs

        for subdir in step_subdirs:
            self.add_input_file(
                filename=f'output_{subdir}.nc', target=f'../{subdir}/output.nc'
            )

    def run(self):
        """
        Compare ``tracer1``, ``layerThickness`` and ``normalVelocity`` in the
        outputs of two previous steps with each other
        """
        super().run()
        step_subdirs = self.step_subdirs
        logger = self.logger
        variables = ['tracer1', 'layerThickness', 'normalVelocity']

        filename1 = self.inputs[0]
        filename2 = self.inputs[1]

        all_pass = True
        for filename in [filename1, filename2]:
            if not os.path.exists(filename):
                logger.error(f'File {filename} does not exist.')
                all_pass = False

        if all_pass:
            ds1 = self.open_model_dataset(filename1)
            ds2 = self.open_model_dataset(filename2)

            all_pass = compare_variables(
                component=self.component,
                variables=variables,
                filename1=filename1,
                filename2=filename2,
                logger=logger,
                ds1=ds1,
                ds2=ds2,
            )
        if not all_pass:
            raise ValueError(
                f'Validation failed comparing outputs between '
                f'{step_subdirs[0]} and {step_subdirs[1]}.'
            )
