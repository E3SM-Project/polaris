from polaris.model_step import ModelStep


class OceanModelStep(ModelStep):
    """
    An Omega or MPAS-Ocean step

    Attributes
    ----------
    cell_count : int or None
        The approximate number of cells in the mesh, used to constrain
        resources
    """
    def __init__(self, test_case, name, subdir=None, ntasks=None,
                 min_tasks=None, openmp_threads=None, max_memory=None,
                 cached=False, yaml=None, update_pio=True, make_graph=False,
                 mesh_filename=None, partition_graph=True,
                 graph_filename='graph.info', cell_count=None):
        """
        Make a step for running the model

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        name : str
            The name of the step

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the target number of tasks the step would ideally use.  If too
            few cores are available on the system to accommodate the number of
            tasks and the number of cores per task, the step will run on
            fewer tasks as long as as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has too
            few cores to accommodate the number of tasks and cores per task,
            the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads to use

        max_memory : int, optional
            the amount of memory that the step is allowed to use in MB.
            This is currently just a placeholder for later use with task
            parallelism

        cached : bool, optional
            Whether to get all of the outputs for the step from the database of
            cached outputs for this component

        update_pio : bool, optional
            Whether to modify the namelist so the number of PIO tasks and the
            stride between them is consistent with the number of nodes and
            cores (one PIO task per node).

        make_graph : bool, optional
            Whether to make a graph file from the given MPAS mesh file.  If
            ``True``, ``mesh_filename`` must be given.

        mesh_filename : str, optional
            The name of an MPAS mesh file to use to make the graph file

        partition_graph : bool, optional
            Whether to partition the domain for the requested number of cores.
            If so, the partitioning executable is taken from the ``partition``
            option of the ``[executables]`` config section.

        graph_filename : str, optional
            The name of the graph file to partition

        cell_count : int, optional
            The approximate number of cells in the mesh, used to constrain
            resources
        """
        super().__init__(
            test_case=test_case, name=name, subdir=subdir, ntasks=ntasks,
            min_tasks=min_tasks, openmp_threads=openmp_threads,
            max_memory=max_memory, cached=cached, yaml=yaml,
            update_pio=update_pio, make_graph=make_graph,
            mesh_filename=mesh_filename, partition_graph=partition_graph,
            graph_filename=graph_filename)

        self.cell_count = cell_count

    def setup(self):
        """
        Determine if we will make yaml files or namelists and streams files,
        then, determine the number of MPI tasks to use based on the estimated
        mesh size
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega':
            self.make_yaml = True
            self.make_namelist = False
            self.make_streams = False
        elif model == 'mpas-ocean':
            self.make_yaml = False
            self.make_namelist = True
            self.make_streams = True
        else:
            raise ValueError(f'Unexpected ocean model: {model}')

        if self.cell_count is not None:
            self.update_ntasks(self.cell_count)

        super().setup()

    def constrain_resources(self, available_cores):
        """
        Update the number of MPI tasks to use based on the estimated mesh size
        """
        if self.cell_count is not None:
            self.update_ntasks(self.cell_count)
        super().constrain_resources(available_cores)

    def map_yaml_to_namelist(self, options):
        """
        A mapping from yaml model config options to namelist options.  This
        method should be overridden for situations in which yaml config
        options have diverged in name or structure from their namelist
        counterparts (e.g. when translating from Omega yaml to MPAS-Ocean
        namelists)

        Parameters
        ----------
        options : dict
            A nested dictionary of yaml sections, options and value to use as
            replacements for existing values

        Returns
        -------
        options : dict
            A nested dictionary of namelist sections, options and value to use
            as replacements for existing values
        """
        # for now, just call the super class version but this will also handle
        # renaming in the future
        return super().map_yaml_to_namelist(options)

    def add_namelist_file(self, package, namelist):
        """
        Add a file with updates to namelist options to the step to be parsed
        when generating a complete namelist file if and when the step gets set
        up.

        Parameters
        ----------
        package : Package
            The package name or module object that contains ``namelist``

        namelist : str
            The name of the namelist replacements file to read from
        """
        raise ValueError('Input namelist files are not supported in '
                         'OceanModelStep')

    def add_streams_file(self, package, streams, template_replacements=None):
        """
        Add a streams file to the step to be parsed when generating a complete
        streams file if and when the step gets set up.

        Parameters
        ----------
        package : Package
            The package name or module object that contains the streams file

        streams : str
            The name of the streams file to read from

        template_replacements : dict, optional
            A dictionary of replacements, in which case ``streams`` must be a
            Jinja2 template to be rendered with these replacements
        """
        raise ValueError('Input streams files are not supported in '
                         'OceanModelStep')

    def update_model_config_at_runtime(self, options):
        """
        Update an existing namelist or yaml file with additional options.  This
        would typically be used for model config options that are only known at
        runtime, not during setup, typically those related to the number of
        nodes and cores.

        Parameters
        ----------
        options : dict
            A dictionary of options and value to replace namelist options with
            new values
        """

        config = self.config

        model = config.get('ocean', 'model')
        if model == 'omega':
            self.update_yaml_at_runtime(options)
        elif model == 'mpas-ocean':
            self.update_namelist_at_runtime(
                self.map_yaml_to_namelist(options))
        else:
            raise ValueError(f'Unexpected ocean model: {model}')

    def update_ntasks(self, cell_count):
        """
        Update ``ntasks`` and ``min_tasks`` for the step based on the estimated
        mesh size
        """
        config = self.config

        goal_cells_per_core = config.getfloat('ocean', 'goal_cells_per_core')
        max_cells_per_core = config.getfloat('ocean', 'max_cells_per_core')

        # ideally, about 200 cells per core
        self.ntasks = max(1, round(cell_count / goal_cells_per_core + 0.5))
        # In a pinch, about 2000 cells per core
        self.min_tasks = max(1, round(cell_count / max_cells_per_core + 0.5))
