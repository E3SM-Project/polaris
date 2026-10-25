from polaris import Step
from polaris.validate import compare_variables

# the norms for requiring that the thickness and velocity are bit-for-bit
EXACT_NORMS = {
    'thickness': dict(l1_norm=0.0, l2_norm=0.0, linf_norm=0.0),
    'normalVelocity': dict(l1_norm=0.0, l2_norm=0.0, linf_norm=0.0),
}

# results with the first-order solver differ slightly between decompositions,
# and between identical runs on GPUs, so these are the norms Compass allows
# between decompositions
FO_NORMS = {
    'thickness': dict(l1_norm=1.0e-9, l2_norm=1.0e-11, linf_norm=1.0e-11),
    'normalVelocity': dict(
        l1_norm=1.0e-15, l2_norm=1.0e-16, linf_norm=1.0e-18
    ),
}


class Validate(Step):
    """
    A step for comparing the outputs of two dome runs

    Attributes
    ----------
    step_subdirs : list of str
        The subdirectories of the two steps whose outputs are compared

    norms : dict
        The maximum allowed norms of the difference for each variable, with
        the variable names as keys and dictionaries with ``l1_norm``,
        ``l2_norm`` and ``linf_norm`` as values

    gpu_norms : dict or None
        The norms to use instead of ``norms`` when MALI runs on GPUs
    """

    def __init__(self, component, step_subdirs, indir, norms, gpu_norms=None):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        step_subdirs : list of str
            The subdirectories of the two steps whose outputs are compared

        indir : str
            the directory the step is in, to which ``name`` will be appended

        norms : dict
            The maximum allowed norms of the difference for each variable,
            with the variable names as keys and dictionaries with
            ``l1_norm``, ``l2_norm`` and ``linf_norm`` as values

        gpu_norms : dict, optional
            The norms to use instead of ``norms`` when MALI runs on GPUs,
            where first-order solves are not reproducible from one run to
            the next
        """
        super().__init__(component=component, name='validate', indir=indir)

        self.step_subdirs = step_subdirs
        self.norms = norms
        self.gpu_norms = gpu_norms

        for subdir in step_subdirs:
            self.add_input_file(
                filename=f'output_{subdir}.nc', target=f'../{subdir}/output.nc'
            )

    def run(self):
        """
        Compare the variables in the outputs of the two steps
        """
        super().run()
        all_pass = True
        for variable, norms in self._get_norms().items():
            quiet = all(norm == 0.0 for norm in norms.values())
            if not compare_variables(
                component=self.component,
                variables=[variable],
                filename1=self.inputs[0],
                filename2=self.inputs[1],
                logger=self.logger,
                config=self.config,
                quiet=quiet,
                **norms,
            ):
                all_pass = False

        if not all_pass:
            raise ValueError(
                f'Validation failed comparing outputs between '
                f'{self.step_subdirs[0]} and {self.step_subdirs[1]}.'
            )

    def _get_norms(self):
        """
        Get the norms for the machine and compiler that MALI runs with
        """
        parallel_system = self.component.parallel_system
        on_gpus = parallel_system is not None and bool(
            parallel_system.gpus_per_node
        )
        if self.gpu_norms is not None and on_gpus:
            return self.gpu_norms
        return self.norms
