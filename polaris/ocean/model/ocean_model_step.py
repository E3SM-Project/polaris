import importlib.resources as imp_res
import os
from types import ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from ruamel.yaml import YAML

from polaris.model_step import ModelStep
from polaris.ocean.conservation import (
    compute_flux_forcing,
    compute_total_energy,
    compute_total_mass,
    compute_total_salt,
    compute_total_tracer,
    get_elapsed_seconds,
)
from polaris.ocean.model.ocean_model_files_mixin import OceanModelFilesMixin

if TYPE_CHECKING:
    # Keep Ocean as a type-only import. Importing it at runtime pulls
    # polaris.tasks.ocean back into polaris.ocean.model while that package is
    # still importing these step classes, creating a circular import.
    from polaris.tasks.ocean import Ocean

OptionValue = Union[str, int, float, bool]
MapSectionKey = Union[str, List[str]]
# in principle, any number of levels but 4 seems sufficient for now
ConfigsType = Dict[
    Union[str, None],
    Union[
        Dict[str, OptionValue],
        Dict[str, Dict[str, OptionValue]],
        Dict[str, Dict[str, Dict[str, OptionValue]]],
        Dict[str, Dict[str, Dict[str, Dict[str, OptionValue]]]],
    ],
]


class OceanModelStep(OceanModelFilesMixin, ModelStep):
    """
    An Omega or MPAS-Ocean step

    Attributes
    ----------
    dynamic_ntasks : bool
        Whether the target and minimum number of MPI tasks (``ntasks`` and
        ``min_tasks``) are computed dynamically from the number of cells
        in the mesh

    config_map : dict
        A nested dictionary that maps from MPAS-Ocean to Omega model config
        options

    graph_target : str
        The name of the graph partition file to link to (relative to the base
        working directory)

    write_coeffs_reconstruct : bool
        Whether to write the coefficients for reconstructing vector
        quantities during the forward run
    """

    # make sure component is of type Ocean, using a string to avoid circular
    # imports
    component: 'Ocean'

    write_coeffs_reconstruct: bool

    def __init__(
        self,
        component: 'Ocean',
        name: str,
        subdir: Optional[str] = None,
        indir: Optional[str] = None,
        ntasks: Optional[int] = None,
        min_tasks: Optional[int] = None,
        openmp_threads: Optional[int] = None,
        max_memory: Optional[int] = None,
        cached: bool = False,
        yaml: Optional[str] = None,
        update_io_tasks: bool = True,
        update_pio: Optional[bool] = None,
        update_eos: bool = False,
        make_graph: bool = False,
        mesh_filename: Optional[str] = None,
        partition_graph: bool = True,
        graph_target: Optional[str] = None,
        target_location='work_dir',
    ) -> None:
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

        update_io_tasks : bool, optional
            Whether to modify model config options controlling IO tasks so the
            number of IO tasks and the stride between them are consistent with
            the number of nodes and cores (one IO task per node).

        update_pio : bool, optional
            Deprecated alias for ``update_io_tasks``.

        update_eos : bool, optional
            Whether to modify the namelist so the equation of state is
            consistent with config options.

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
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            max_memory=max_memory,
            cached=cached,
            yaml=yaml,
            update_io_tasks=update_io_tasks,
            update_pio=update_pio,
            make_graph=make_graph,
            mesh_filename=mesh_filename,
            partition_graph=partition_graph,
            graph_filename='graph.info',
        )

        self.dynamic_ntasks = ntasks is None and min_tasks is None
        self.target_location = target_location
        self.config_map: Union[
            None, List[Dict[str, Dict[MapSectionKey, str]]]
        ] = None
        self.graph_target = graph_target
        self.update_eos = update_eos

    def setup(self) -> None:
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
            self._read_config_map()
            self.partition_graph = False
        elif model == 'mpas-ocean':
            self.config_models = ['ocean', 'mpas-ocean']
            self.make_yaml = False
            if self.target_location == 'work_dir':
                self.add_input_file(
                    filename='graph.info', work_dir_target=self.graph_target
                )
            else:
                self.add_input_file(
                    filename='graph.info',
                    target=self.graph_target,
                    database=self.target_location,
                )
            self.streams_section = 'streams'
        else:
            raise ValueError(f'Unexpected ocean model: {model}')

        self.dynamic_ntasks = self.ntasks is None and self.min_tasks is None

        if self.dynamic_ntasks:
            self._update_ntasks()
        self._set_gpus_per_task()

        super().setup()

    def dynamic_model_config(self, at_setup: bool) -> None:
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        if self.update_io_tasks and not at_setup:
            self.update_io_tasks_config(config_model='ocean')

        self.add_yaml_file(
            'polaris.ocean.config',
            'model_inputs.yaml',
            template_replacements=self._get_model_input_replacements(),
        )

        if self.update_eos:
            self.update_namelist_eos()
        self.write_coeffs_reconstruct = self.config.getboolean(
            'ocean', 'write_coeffs_reconstruct', fallback=False
        )
        if self.write_coeffs_reconstruct:
            model = self.config.get('ocean', 'model')
            if model != 'mpas-ocean':
                raise ValueError(
                    'Coefficients for vector reconstruction can only be '
                    'written for ocean model MPAS-Ocean'
                )
            self.add_yaml_file(
                'polaris.ocean.config', 'coeffs_reconstruct.yaml'
            )

    def constrain_resources(self, available_cores: Dict[str, Any]) -> None:
        """
        Update the number of MPI tasks to use based on the estimated mesh size
        """
        if self.dynamic_ntasks:
            self._update_ntasks()
        self._set_gpus_per_task()
        super().constrain_resources(available_cores)

    def process_inputs_and_outputs(self) -> None:
        """
        Process the model and any configured model-input placeholders.
        For MPAS-Ocean, ``<<<vert_coord>>>`` entries are removed because no
        separate vert coord file is written for that model.
        """
        self._resolve_model_file_placeholders()
        super().process_inputs_and_outputs()

    def compute_cell_count(self) -> Optional[int]:
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        return None

    def map_yaml_options(
        self,
        options: Dict[str, OptionValue],
        config_model: Optional[str],
    ) -> Tuple[Optional[Dict[str, OptionValue]], Optional[ConfigsType]]:
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
        options : dict or None
            A revised dictionary of yaml options and value to use as
            replacements for existing values

        configs : dict or None
            A revised nested dictionary of yaml sections, options and value to
            use as replacements for existing values
        """
        config = self.config
        model = config.get('ocean', 'model')
        if model == 'omega' and config_model == 'ocean':
            # make a dummy configs dict with None as the section
            mpaso_configs: ConfigsType = {None: options}
            configs = self._map_mpaso_to_omega_configs(mpaso_configs)
            return None, configs
        else:
            return options, None

    def map_yaml_configs(
        self,
        configs: ConfigsType,
        config_model: Optional[str],
    ) -> ConfigsType:
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

    def add_namelist_file(
        self,
        package: Union[str, ModuleType],
        namelist: str,
    ) -> None:
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
        raise ValueError(
            'Input namelist files are not supported in OceanModelStep'
        )

    def add_streams_file(
        self,
        package: Union[str, ModuleType],
        streams: str,
        template_replacements: Optional[Dict[str, Any]] = None,
    ) -> None:
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
        raise ValueError(
            'Input streams files are not supported in OceanModelStep'
        )

    def update_namelist_eos(self) -> None:
        """
        Modify the namelist to make it consistent with eos config options
        """
        config = self.config
        section = config['ocean']

        eos_type = section.get('eos_type')
        model = config.get('ocean', 'model')

        if eos_type.lower() in ('linear', 'constant'):
            replacements = self._get_linear_eos_replacements(
                eos_type=eos_type, model=model
            )
        elif eos_type.lower() == 'teos-10':
            replacements = self._get_teos10_eos_replacements(
                eos_type=eos_type, model=model
            )
        else:
            raise ValueError(f'Unsupported equation of state: {eos_type}')

        self.add_model_config_options(
            options=replacements, config_model='ocean'
        )

    def _get_linear_eos_replacements(
        self, eos_type: str, model: str
    ) -> Dict[str, OptionValue]:
        """
        Get model config replacements for the linear or constant EOS
        """
        section = self.config['ocean']
        eos_linear_alpha = section.getfloat('eos_linear_alpha')
        eos_linear_beta = section.getfloat('eos_linear_beta')
        eos_linear_rhoref = section.getfloat('eos_linear_rhoref')
        eos_linear_Tref = section.getfloat('eos_linear_Tref')
        eos_linear_Sref = section.getfloat('eos_linear_Sref')

        replacements: Dict[str, OptionValue] = {
            'config_eos_type': eos_type,
            'config_eos_linear_alpha': eos_linear_alpha,
            'config_eos_linear_beta': eos_linear_beta,
            'config_eos_linear_densityref': eos_linear_rhoref,
        }
        if model == 'mpas-ocean':
            if eos_type.lower() == 'constant':
                # MPAS-Ocean has no constant EOS; the constant.cfg options
                # make its linear EOS constant
                eos_type = 'linear'
            replacements.update(
                {
                    'config_eos_type': eos_type,
                    'config_eos_linear_Tref': eos_linear_Tref,
                    'config_eos_linear_Sref': eos_linear_Sref,
                }
            )
        else:
            if eos_linear_Tref != 0.0 or eos_linear_Sref != 0.0:
                raise ValueError(
                    'Nonzero Tref and Sref are not supported for Omega '
                    'model since they do not affect the linear EOS'
                )
        return replacements

    def _get_teos10_eos_replacements(
        self, eos_type: str, model: str
    ) -> Dict[str, OptionValue]:
        """
        Get model config replacements for the TEOS-10 EOS
        """
        if model == 'mpas-ocean':
            # MPAS-Ocean has no TEOS-10 option; Jackett-McDougall is the
            # closest available nonlinear EOS
            eos_type = 'jm'
        replacements: Dict[str, OptionValue] = {
            'config_eos_type': eos_type,
        }
        return replacements

    def check_properties(self):
        """
        Check conservation properties of the output files of this step

        Returns
        -------
        checked : bool
            Whether any properties were checked

        success : bool
            Whether all checked properties are within tolerance
        """
        logger = self.logger
        config = self.config
        checked = False
        success = True
        mesh_filename = self.get_horiz_mesh_filename()
        init_filename = self.get_init_filename()
        ds_mesh = self.open_model_dataset(
            os.path.join(self.work_dir, mesh_filename)
        )
        ds_init = self.open_model_dataset(
            os.path.join(self.work_dir, init_filename)
        )
        datasets: Dict[str, Any] = {}
        for check in self.properties_to_check:
            filename = check['filename']
            baseline = check['baseline']
            time_index_end = check['time_index_end']
            properties = [
                prop.replace(' conservation', '')
                for prop in check['properties']
            ]

            if filename not in datasets:
                datasets[filename] = self.open_model_dataset(
                    os.path.join(self.work_dir, filename), decode_times=True
                )
            ds = datasets[filename]

            if baseline == 'init':
                ds_start = ds_init
                time_index_start = 0
                dt = get_elapsed_seconds(ds, time_index_end=time_index_end)
                baseline_str = 'init'
            else:
                ds_start = None
                time_index_start = baseline
                dt = get_elapsed_seconds(
                    ds,
                    time_index_start=time_index_start,
                    time_index_end=time_index_end,
                )
                baseline_str = f'time index {time_index_start}'
            print(f'elapsed seconds: {dt}')
            for output_property in properties:
                func: Callable[..., Any]
                kwargs: Dict[str, Any] = {}
                if output_property == 'mass':
                    func = compute_total_mass
                elif output_property == 'energy':
                    func = compute_total_energy
                    kwargs['model'] = self.config.get('ocean', 'model')
                elif output_property == 'salt':
                    func = compute_total_salt
                elif output_property == 'tracer':
                    func = compute_total_tracer
                    kwargs = {'tracer_name': 'tracer1'}
                else:
                    raise ValueError(
                        f'Unknown property to check: {output_property}'
                    )
                tol = config.getfloat(
                    'ocean', f'{output_property}_conservation_tolerance'
                )

                expected_change = 0.0
                if output_property in ['mass', 'energy', 'salt']:
                    expected_change = compute_flux_forcing(
                        ds_mesh,
                        ds,
                        output_property,
                        dt,
                        model=config.get('ocean', 'model'),
                        config=config,
                    )

                relative_error = self._compute_rel_err(
                    func,
                    ds_mesh=ds_mesh,
                    ds_init=ds_start,
                    ds=ds,
                    expected_change=expected_change,
                    time_index_start=time_index_start,
                    time_index_end=time_index_end,
                    **kwargs,
                )
                passed = relative_error <= tol
                status = 'PASS' if passed else 'FAIL'
                logger.info(
                    f'    {output_property} conservation '
                    f'({baseline_str} to time index {time_index_end}): '
                    f'error={relative_error:.3e} tol={tol:.3e} [{status}]'
                )
                checked = True
                success = success and passed

        return checked, success

    def _compute_rel_err(
        self,
        func,
        ds_mesh,
        ds,
        ds_init=None,
        time_index_start=0,
        time_index_end=0,
        expected_change=0.0,
        **kwargs,
    ):
        """
        Compute the error in a budget, relative to the expected change if it
        is nonzero and to the initial content otherwise

        The initial value is taken from ``ds_init`` if it is provided, so that
        the budget starts from the true initial condition rather than the
        first output time slice.
        """
        if ds_init is not None:
            ds_start = ds_init
        else:
            ds_start = ds
        init_val = float(
            func(
                ds_mesh, ds_start.isel(Time=time_index_start), **kwargs
            ).values
        )
        ds_end = ds.isel(Time=time_index_end)
        final_val = float(func(ds_mesh, ds_end, **kwargs).values)
        residual = (final_val - init_val) - expected_change
        print(f'init {init_val}, final {final_val}')
        print(f'recorded change {residual}, expected {expected_change}')
        if init_val != 0.0:
            denom = abs(init_val)
        else:
            denom = 1.0
        return abs(residual) / denom

    def _update_ntasks(self) -> None:
        """
        Update ``ntasks`` and ``min_tasks`` for the step based on the estimated
        mesh size
        """
        config = self.config
        cell_count = self.compute_cell_count()
        if cell_count is None:
            raise ValueError(
                'ntasks and min_tasks were not set explicitly '
                'but they also cannot be computed because '
                'compute_cell_count() does not appear to have '
                'been overridden.'
            )

        if self._use_gpu_resources():
            goal_cells_per_core = config.getfloat(
                'ocean', 'goal_cells_per_gpu'
            )
            max_cells_per_core = config.getfloat('ocean', 'max_cells_per_gpu')
        else:
            goal_cells_per_core = config.getfloat(
                'ocean', 'goal_cells_per_core'
            )
            max_cells_per_core = config.getfloat('ocean', 'max_cells_per_core')
        # machines (e.g. Perlmutter) seem to be happier with ntasks that
        # are multiples of 4
        # ideally, about 200 cells per cpu or 8000 cells per gpu
        self.ntasks = max(1, 4 * round(cell_count / (4 * goal_cells_per_core)))
        # In a pinch, about 2000 cells per cpu or 80000 cells per gpu
        self.min_tasks = max(
            1, 4 * round(cell_count / (4 * max_cells_per_core))
        )

    def _get_model_input_replacements(self) -> Dict[str, str]:
        return {
            'horiz_mesh_filename': self.get_horiz_mesh_filename(),
            'vert_coord_filename': self.get_vert_coord_filename(),
            'init_filename': self.get_init_filename(),
        }

    def _set_gpus_per_task(self) -> None:
        """
        Set ``gpus_per_task`` and ``min_gpus_per_task`` for the step based
        on whether gpus are available and the model is Omega
        """
        if self._use_gpu_resources():
            self.gpus_per_task = 1
            self.min_gpus_per_task = 1
        else:
            self.gpus_per_task = 0
            self.min_gpus_per_task = 0

    def _use_gpu_resources(self) -> bool:
        """
        Whether to use GPU resources based on whether gpus are available and
        the model is Omega
        """
        config = self.config

        model = config.get('ocean', 'model')

        gpus_per_node = 0
        parallel_system = self.component.parallel_system
        if parallel_system is not None:
            gpus_per_node = parallel_system.get_config_int(
                'gpus_per_node', default=0
            )

        return model == 'omega' and gpus_per_node > 0

    def _read_config_map(self) -> None:
        """
        Read the map from MPAS-Ocean to Omega config options
        """
        package = 'polaris.ocean.model'
        filename = 'mpaso_to_omega.yaml'
        text = imp_res.files(package).joinpath(filename).read_text()

        yaml_data = YAML(typ='rt')
        nested_dict = yaml_data.load(text)
        self.config_map = nested_dict['config']

    def _map_mpaso_to_omega_configs(
        self,
        configs: ConfigsType,
    ) -> ConfigsType:
        """
        Map MPAS-Ocean namelist options to Omega config options
        """
        out_configs: ConfigsType = {}
        not_found = []
        for section, options in configs.items():
            for option, mpaso_value in options.items():
                if isinstance(mpaso_value, dict):
                    raise ValueError(
                        f'Nested sections are not supported in '
                        f'MPAS-Ocean configs: {section}/{option}'
                    )
                try:
                    omega_sections, omega_option, omega_value = (
                        self._map_mpaso_to_omega_section_option(
                            section=section, option=option, value=mpaso_value
                        )
                    )
                    local_config: Dict[str | None, Any] = out_configs
                    sec_str = '/'.join(omega_sections)
                    for omega_section in omega_sections:
                        if omega_section not in local_config:
                            local_config[omega_section] = {}
                        if not isinstance(local_config[omega_section], dict):
                            raise ValueError(
                                f'{sec_str} appears to point to a config '
                                f'option, not a section'
                            )
                        local_config = local_config[omega_section]
                    local_config[omega_option] = omega_value
                except ValueError:
                    not_found.append(f'{sec_str}/{option}')

        self._warn_not_found(not_found)

        return out_configs

    def _map_mpaso_to_omega_section_option(
        self,
        option: str,
        value: OptionValue,
        section: str | None = None,
    ) -> Tuple[List[str], str, OptionValue]:
        """
        Map MPAS-Ocean namelist section and option to Omega equivalent
        """
        out_sections: List[str] = []
        out_option = option

        assert self.config_map is not None

        option_found = False
        # traverse the map
        for entry in self.config_map:
            section_dict = entry['section']
            if len(section_dict) != 1:
                raise ValueError(
                    'Mapping entries must have exactly one section'
                )

            mpaso_section = next(iter(section_dict))
            omega_sections: MapSectionKey = section_dict[mpaso_section]
            if section is not None and mpaso_section != section:
                continue

            options_dict = entry['options']
            option_found = False
            try:
                omega_option = options_dict[option]
            except KeyError:
                continue
            else:
                option_found = True
                # make sure out_sections is a list
                out_sections = (
                    omega_sections
                    if isinstance(omega_sections, list)
                    else [omega_sections]
                )
                out_option = omega_option
                break

        if not option_found:
            sec_str = (
                '/'.join(section) if isinstance(section, list) else section
            )
            raise ValueError(f'No mapping found for {sec_str}/{option}')

        out_option, out_value = self._map_handle_not(out_option, value)

        return out_sections, out_option, out_value

    @staticmethod
    def _warn_not_found(not_found: List[str]) -> None:
        """Warn about options that were not found in the map"""
        if len(not_found) == 0:
            return

        print('WARNING: No Omega mapping found for these MPASO options:')
        for string in not_found:
            print(f'    {string}')
        print()

    @staticmethod
    def _map_handle_not(
        option: str,
        value: OptionValue,
    ) -> Tuple[str, OptionValue]:
        """
        Handle negation of boolean value if the option starts with "not"
        """
        if option.startswith('not '):
            # a special case where we want the opposite of a boolean value
            option = option[4:]
            if isinstance(value, bool):
                value = not value
            elif isinstance(value, float):
                value = -value
            else:
                raise ValueError(
                    f"{option}: Cannot apply 'not' to option type "
                    f'{type(value)}'
                )
        return option, value
