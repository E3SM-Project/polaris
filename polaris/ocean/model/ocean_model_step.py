from polaris.model_step import ModelStep


class OceanModelStep(ModelStep):
    """
    An Omega or MPAS-Ocean step

    Attributes
    ----------
    dynamic_ntasks : bool
        Whether the target and minimum number of MPI tasks (``ntasks`` and
        ``min_tasks``) are computed dynamically from the number of cells
        in the mesh
    """
    def __init__(self, task, name, subdir=None, ntasks=None,
                 min_tasks=None, openmp_threads=None, max_memory=None,
                 cached=False, yaml=None, update_pio=True, make_graph=False,
                 mesh_filename=None, partition_graph=True,
                 graph_filename='graph.info'):
        """
        Make a step for running the model

        Parameters
        ----------
        task : polaris.Task
            The task this step belongs to

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
        """
        super().__init__(
            task=task, name=name, subdir=subdir, ntasks=ntasks,
            min_tasks=min_tasks, openmp_threads=openmp_threads,
            max_memory=max_memory, cached=cached, yaml=yaml,
            update_pio=update_pio, make_graph=make_graph,
            mesh_filename=mesh_filename, partition_graph=partition_graph,
            graph_filename=graph_filename)

        self.dynamic_ntasks = (ntasks is None and min_tasks is None)

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
        elif model == 'mpas-ocean':
            self.make_yaml = False
        else:
            raise ValueError(f'Unexpected ocean model: {model}')

        self.dynamic_ntasks = (self.ntasks is None and self.min_tasks is None)

        if self.dynamic_ntasks:
            self._update_ntasks()

        super().setup()

    def constrain_resources(self, available_cores):
        """
        Update the number of MPI tasks to use based on the estimated mesh size
        """
        if self.dynamic_ntasks:
            self._update_ntasks()
        super().constrain_resources(available_cores)

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        return None

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

    def _update_ntasks(self):
        """
        Update ``ntasks`` and ``min_tasks`` for the step based on the estimated
        mesh size
        """
        config = self.config
        cell_count = self.compute_cell_count()
        if cell_count is None:
            raise ValueError('ntasks and min_tasks were not set explicitly '
                             'but they also cannot be computed because '
                             'compute_cell_count() does not appear to have '
                             'been overridden.')

        goal_cells_per_core = config.getfloat('ocean', 'goal_cells_per_core')
        max_cells_per_core = config.getfloat('ocean', 'max_cells_per_core')

        # machines (e.g. Perlmutter) seem to be happier with ntasks that
        # are multiples of 4
        # ideally, about 200 cells per core
        self.ntasks = max(1, 4 * round(cell_count / (4 * goal_cells_per_core)))
        # In a pinch, about 2000 cells per core
        self.min_tasks = max(1,
                             4 * round(cell_count / (4 * max_cells_per_core)))
