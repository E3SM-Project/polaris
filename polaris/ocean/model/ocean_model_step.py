import importlib.resources as imp_res
from typing import Dict, List, Union

from ruamel.yaml import YAML

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

    map : dict
        A nested dictionary that maps from MPAS-Ocean to Omega model config
        options

    graph_target : str
        The name of the graph partition file to link to (relative to the base
        working directory)
    """
    def __init__(self, component, name, subdir=None, indir=None, ntasks=None,
                 min_tasks=None, openmp_threads=None, max_memory=None,
                 cached=False, yaml=None, update_pio=True, make_graph=False,
                 mesh_filename=None, partition_graph=True, graph_target=None):
        """
        Make a step for running the model

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

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

        graph_target : str, optional
            The graph file name (relative to the base work directory).
            If none, it will be created.
        """
        if graph_target is None:
            self.make_graph = True

        super().__init__(
            component=component, name=name, subdir=subdir, indir=indir,
            ntasks=ntasks, min_tasks=min_tasks, openmp_threads=openmp_threads,
            max_memory=max_memory, cached=cached, yaml=yaml,
            update_pio=update_pio, make_graph=make_graph,
            mesh_filename=mesh_filename, partition_graph=partition_graph,
            graph_filename='graph.info')

        self.dynamic_ntasks = (ntasks is None and min_tasks is None)

        self.map: Union[None, List[Dict[str, Dict[str, str]]]] = None
        self.graph_target = graph_target

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
            self.config_models = ['ocean', 'Omega']
            self.yaml = 'omega.yml'
            self.streams_section = 'IOStreams'
            self._read_map()
            self.partition_graph = False
        elif model == 'mpas-ocean':
            self.config_models = ['ocean', 'mpas-ocean']
            self.make_yaml = False
            self.add_input_file(
                filename='graph.info',
                work_dir_target=self.graph_target)
            self.streams_section = 'streams'
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

    def map_yaml_options(self, options, config_model):
        """
        A mapping between model config options from MPAS-Ocean to Omega

        Parameters
        ----------
        options : dict
            A dictionary of yaml options and value to use as replacements for
            existing values

        config_model : str or None
            If config options are available for multiple models, the model that
            the config options are from

        Returns
        -------
        options : dict
            A revised dictionary of yaml options and value to use as
            replacements for existing values
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega' and config_model == 'ocean':
            options = self._map_mpaso_to_omega_options(options)
        return options

    def map_yaml_configs(self, configs, config_model):
        """
        A mapping between model sections and config options from MPAS-Ocean to
        Omega

        Parameters
        ----------
        configs : dict
            A nested dictionary of yaml sections, options and value to use as
            replacements for existing values

        config_model : str or None
            If config options are available for multiple models, the model that
            the config options are from

        Returns
        -------
        configs : dict
            A revised nested dictionary of yaml sections, options and value to
            use as replacements for existing values
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega' and config_model == 'ocean':
            configs = self._map_mpaso_to_omega_configs(configs)
        return configs

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

    def _read_map(self):
        """
        Read the map from MPAS-Ocean to Omega config options
        """
        package = 'polaris.ocean.model'
        filename = 'mpaso_to_omega.yaml'
        text = imp_res.files(package).joinpath(filename).read_text()

        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        self.map = nested_dict['map']

    def _map_mpaso_to_omega_options(self, options):
        """
        Map MPAS-Ocean namelist options to Omega config options
        """

        out_options: Dict[str, str] = {}
        not_found = []
        for mpaso_option, mpaso_value in options.items():
            try:
                omega_option, omega_value = self._map_mpaso_to_omega_option(
                    option=mpaso_option, value=mpaso_value)
                out_options[omega_option] = omega_value
            except ValueError:
                not_found.append(mpaso_option)

        self._warn_not_found(not_found)

        return out_options

    def _map_mpaso_to_omega_option(self, option, value):
        """
        Map MPAS-Ocean namelist option to Omega equivalent
        """
        out_option = option
        found = False

        assert self.map is not None
        # traverse the map
        for entry in self.map:
            options_dict = entry['options']
            for mpaso_option, omega_option in options_dict.items():
                if option == mpaso_option:
                    found = True
                    out_option = omega_option
                    break

            if found:
                break

        if not found:
            raise ValueError(f'No mapping found for {option}')

        out_option, out_value = self._map_handle_not(out_option, value)

        return out_option, out_value

    def _map_mpaso_to_omega_configs(self, configs):
        """
        Map MPAS-Ocean namelist options to Omega config options
        """
        out_configs: Dict[str, Dict[str, str]] = {}
        not_found = []
        for section, options in configs.items():
            for option, mpaso_value in options.items():
                try:
                    omega_section, omega_option, omega_value = \
                        self._map_mpaso_to_omega_section_option(
                            section=section, option=option, value=mpaso_value)
                    if omega_section not in out_configs:
                        out_configs[omega_section] = {}
                    out_configs[omega_section][omega_option] = omega_value
                except ValueError:
                    not_found.append(f'{section}/{option}')

        self._warn_not_found(not_found)

        return out_configs

    def _map_mpaso_to_omega_section_option(self, section, option, value):
        """
        Map MPAS-Ocean namelist section and option to Omega equivalent
        """
        out_section = section
        out_option = option

        assert self.map is not None

        option_found = False
        # traverse the map
        for entry in self.map:
            section_dict = entry['section']
            try:
                omega_section = section_dict[section]
            except KeyError:
                continue
            else:
                options_dict = entry['options']
                option_found = False
                try:
                    omega_option = options_dict[option]
                except KeyError:
                    continue
                else:
                    option_found = True
                    out_section = omega_section
                    out_option = omega_option
                    break

        if not option_found:
            raise ValueError(f'No mapping found for {section}/{option}')

        out_option, out_value = self._map_handle_not(out_option, value)

        return out_section, out_option, out_value

    @staticmethod
    def _warn_not_found(not_found):
        """ Warn about options that were not found in the map """
        if len(not_found) == 0:
            return

        print('WARNING: No Omega mapping found for these MPASO options:')
        for string in not_found:
            print(f'    {string}')
        print()

    @staticmethod
    def _map_handle_not(option, value):
        """
        Handle negation of boolean value if the option starts with "not"
        """
        if option.startswith('not '):
            # a special case where we want the opposite of a boolean value
            option = option[4:]
            value = not value

        return option, value
