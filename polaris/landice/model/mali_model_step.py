from polaris.model_step import ModelStep

# the velocity solvers that MALI gets from Albany
ALBANY_VELOCITY_SOLVERS = ['FO']


class MaliModelStep(ModelStep):
    """
    A step for running MALI

    Attributes
    ----------
    velocity_solver : str or None
        MALI's velocity solver (``config_velocity_solver``), or ``None`` to
        use the one in the step's namelist
    """

    def __init__(
        self,
        component,
        name,
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=None,
        velocity_solver=None,
        albany_input_package=None,
        albany_input_filename='albany_input.yaml',
    ):
        """
        Make a step for running MALI

        Parameters
        ----------
        component : polaris.Component
            the component that the step belongs to

        name : str
            The name of the step

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
            are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        ntasks : int, optional
            the target number of tasks the step would ideally use

        min_tasks : int, optional
            the number of tasks the step requires

        openmp_threads : int, optional
            the number of OpenMP threads to use

        velocity_solver : str, optional
            MALI's velocity solver (``config_velocity_solver``), for example
            ``'sia'`` or ``'FO'``.  By default, the step uses the one in its
            namelist.

        albany_input_package : str, optional
            The package with the Albany input file, required if
            ``velocity_solver`` is one that Albany provides

        albany_input_filename : str, optional
            The name of the Albany input file in ``albany_input_package``
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
        )

        self.velocity_solver = velocity_solver

        if self.needs_albany:
            if albany_input_package is None:
                raise ValueError(
                    f'Step {self.name} uses the {velocity_solver} velocity '
                    f'solver, so it needs an Albany input file from '
                    f'albany_input_package'
                )
            # MALI reads the Albany input file from the run directory
            self.add_input_file(
                filename='albany_input.yaml',
                target=albany_input_filename,
                package=albany_input_package,
                copy=True,
            )

    @property
    def needs_albany(self):
        """
        Whether the step uses a velocity solver from Albany

        Returns
        -------
        needs_albany : bool
            Whether MALI must be built with Albany for this step
        """
        return self.velocity_solver in ALBANY_VELOCITY_SOLVERS

    @property
    def uses_gpus(self):
        """
        Whether the step runs on GPUs

        Albany runs on GPUs on any machine whose parallel config has them,
        with one GPU per MPI task.  The rest of MALI does not use GPUs.

        Returns
        -------
        uses_gpus : bool
            Whether the step uses Albany on a machine with GPUs
        """
        if not self.needs_albany:
            return False
        parallel_system = self.component.parallel_system
        if parallel_system is None:
            return False
        gpus_per_node = parallel_system.get_config_int(
            'gpus_per_node', default=0
        )
        return gpus_per_node > 0

    def setup(self):
        """
        Request GPUs if the step uses them, then set up the command-line
        arguments
        """
        self._set_gpus()
        super().setup()

    def constrain_resources(self, available_resources):
        """
        Request GPUs if the step uses them, then constrain the step's
        resources to those available

        Parameters
        ----------
        available_resources : dict
            A dictionary containing available resources (cores, tasks, nodes
            and cores_per_node)
        """
        self._set_gpus()
        super().constrain_resources(available_resources)

    def dynamic_model_config(self, at_setup):
        """
        Set the velocity solver, if one was given

        These options are added last, so they take precedence over namelist
        files that the step adds

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        if self.velocity_solver is not None:
            self.add_model_config_options(
                options={'config_velocity_solver': self.velocity_solver}
            )

    def _set_gpus(self):
        """
        Set ``gpus`` and ``min_gpus``: one GPU per task if the step uses GPUs

        The GPUs are a total for the step: a per-task count does not confine
        a step to those GPUs when steps run at the same time.
        """
        if self.uses_gpus:
            self.gpus = self.ntasks
            self.min_gpus = self.min_tasks
        else:
            self.gpus = 0
            self.min_gpus = 0
