import os
import shutil
from collections import OrderedDict
from typing import List, Union

import numpy as np
import xarray as xr
from lxml import etree
from mpas_tools.logging import check_call

import polaris.namelist
import polaris.streams
from polaris.step import Step
from polaris.yaml import PolarisYaml, yaml_to_mpas_streams


class ModelStep(Step):
    """
    Attributes
    ----------
    namelist : str
        The name of the namelist file

    streams : str
        The name of the streams file

    yaml : str
        The name of the yaml file

    config_models : list of str
        If config options are available for multiple models, a list of valid
        models from which config options should be taken.  For example, for
        MPAS-Ocean this would be ``['ocean', 'mpas-ocean']`` and for Omega it
        is ``['ocean', 'omega']``, since both models share the generic
        ``ocean`` config options.

    update_pio : bool
        Whether to modify the namelist so the number of PIO tasks and the
        stride between them is consistent with the number of nodes and
        cores (one PIO task per node).

    make_graph : bool
        Whether to make a graph file from the given MPAS mesh file.  If
        ``True``, ``mesh_filename`` must be given.

    mesh_filename : str
        The name of an MPAS mesh file to use to make the graph file

    partition_graph : bool
        Whether to partition the domain for the requested number of cores.
        If so, the partitioning executable is taken from the ``partition``
        option of the ``[executables]`` config section.

    graph_filename : str
        The name of the graph file to partition

    model_config_data : list
        a list used internally to keep track of updates to the default
        model config options from calls to
        :py:meth:`polaris.ModelStep.add_yaml_file`
        :py:meth:`polaris.ModelStep.add_namelist_file`
        and :py:meth:`polaris.ModelStep.add_model_config_options`

    streams_data : list
        a list used internally to keep track of updates to the default
        streams from calls to :py:meth:`polaris.ModelStep.add_streams_file`

    make_yaml : bool
        Whether to create a yaml file with model config options and streams
        instead of MPAS namelist and streams files

    streams_section : str
        The name of the streams section in yaml files
    """
    def __init__(self, component, name, subdir=None, indir=None, ntasks=None,
                 min_tasks=None, openmp_threads=None, max_memory=None,
                 cached=False, namelist=None, streams=None, yaml=None,
                 update_pio=True, make_graph=False, mesh_filename=None,
                 partition_graph=True, graph_filename='graph.info',
                 make_yaml=False):
        """
        Make a step for running the model

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

        namelist : str, optional
            The name of the namelist file, default is ``namelist.<component>``

        streams : str, optional
            The name of the streams file, default is ``streams.<component>``

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

        make_yaml : bool, optional
            Whether to create a yaml file with model config options and streams
            instead of MPAS namelist and streams files
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=indir, cpus_per_task=openmp_threads,
                         min_cpus_per_task=openmp_threads, ntasks=ntasks,
                         min_tasks=min_tasks, openmp_threads=openmp_threads,
                         max_memory=max_memory, cached=cached)

        if namelist is None:
            namelist = f'namelist.{component.name}'

        if streams is None:
            streams = f'streams.{component.name}'

        if yaml is None:
            yaml = f'{component.name}.yaml'

        self.namelist = namelist
        self.streams = streams
        self.yaml = yaml
        self.config_models: Union[List[None], List[str]] = [None]
        self.update_pio = update_pio
        self.make_graph = make_graph
        self.mesh_filename = mesh_filename
        self.partition_graph = partition_graph
        self.graph_filename = graph_filename

        self.make_yaml = make_yaml
        self.streams_section = 'streams'

        self.add_input_file(filename='<<<model>>>')

        self.model_config_data = list()
        self.streams_data = list()

        # used during generating yaml, namelist and streams files
        self._yaml = None
        self._namelist = None
        self._streams_tree = None

    def setup(self):
        """ Setup the command-line arguments """
        config = self.config
        component_path = config.get('executables', 'component')
        model_basename = os.path.basename(component_path)
        if self.make_yaml:
            self.args = [[f'./{model_basename}']]
        else:
            self.args = [[f'./{model_basename}',
                          '-n', self.namelist,
                          '-s', self.streams]]

    def set_model_resources(self, ntasks=None, min_tasks=None,
                            openmp_threads=None, max_memory=None):
        """
        Update the resources for the step.  This can be done within init,
        ``setup()`` or ``runtime_setup()`` for the step that this step
        belongs to, or init, ``configure()`` or ``run()`` for the task
        that this step belongs to.

        Parameters
        ----------
        ntasks : int, optional
            the number of tasks the step would ideally use.  If too few
            cores are available on the system to accommodate the number of
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
        """
        self.set_resources(cpus_per_task=openmp_threads,
                           min_cpus_per_task=openmp_threads, ntasks=ntasks,
                           min_tasks=min_tasks, openmp_threads=openmp_threads,
                           max_memory=max_memory)

    def add_model_config_options(self, options, config_model=None):
        """
        Add the replacement model config options to be parsed when generating
        a namelist or yaml file if and when the step gets set up.  The config
        values should be in the appropriate python data type: bool, float,
        int or str.

        Parameters
        ----------
        options : dict
            A dictionary of options and value to replace model config options
            with new values

        config_model : str, optional
            If config options are available for multiple models, the model that
            the config options are from
        """
        self.model_config_data.append(dict(options=options,
                                           config_model=config_model))

    def add_yaml_file(self, package, yaml, template_replacements=None):
        """
        Add a file with updates to yaml config options to the step to be parsed
        when generating a complete yaml file if and when the step gets set
        up.

        Parameters
        ----------
        package : Package
            The package name or module object that contains ``yaml``

        yaml : str
            The name of the yaml file with replacement config options to read

        template_replacements : dict, optional
            A dictionary of replacements, in which case ``yaml`` must be a
            Jinja2 template to be rendered with these replacements
        """
        self.model_config_data.append(dict(package=package, yaml=yaml,
                                           replacements=template_replacements))
        self.streams_data.append(dict(package=package, yaml=yaml,
                                      replacements=template_replacements))

    def map_yaml_options(self, options, config_model):
        """
        A mapping between model config options between different models.  This
        method should be overridden for situations in which yaml config
        options have diverged in name or structure from their counterparts in
        another model (e.g. when translating from MPAS-Ocean namelist options
        to Omega config options)

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
        return options

    def map_yaml_configs(self, configs, config_model):
        """
        A mapping between model config options between different models.  This
        method should be overridden for situations in which yaml config
        options have diverged in name or structure from their counterparts in
        another model (e.g. when translating from MPAS-Ocean namelist options
        to Omega config options)

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
        return configs

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
        namelist = dict()
        # flatten the dictionary, since MPAS is expecting a flat set of options
        # and values
        for section_or_option in options:
            if isinstance(options[section_or_option], (dict, OrderedDict)):
                section = section_or_option
                for option in options[section]:
                    namelist[option] = options[section][option]
            else:
                option = section_or_option
                namelist[option] = options[option]

        for option in namelist:
            value = namelist[option]
            if isinstance(value, bool):
                if value:
                    namelist[option] = '.true.'
                else:
                    namelist[option] = '.false.'
            elif isinstance(value, str):
                # extra set of quotes
                namelist[option] = f"'{value}'"
            elif isinstance(value, float):
                namelist[option] = f'{value:g}'
            else:
                namelist[option] = f'{value}'

        return namelist

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
        self.model_config_data.append(dict(package=package, namelist=namelist))

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
        self.streams_data.append(
            dict(package=package, streams=streams,
                 replacements=template_replacements))

    def dynamic_model_config(self, at_setup):
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
        if self.update_pio and not at_setup:
            self.update_namelist_pio()

    def runtime_setup(self):
        """
        Update PIO namelist options, make graph file, and partition graph file
        (if any of these are requested)
        """
        quiet = False
        self._read_model_config()

        # start fresh for dynamic model configuration
        self.model_config_data = list()
        self.streams_data = list()
        self.dynamic_model_config(at_setup=False)

        if self.make_yaml:
            self._process_yaml(quiet=quiet)
        else:
            self._process_namelists(quiet=quiet)
            self._process_streams(quiet=quiet, remove_unrequested=False)

        self._write_model_config()

        if self.make_graph:
            make_graph_file(mesh_filename=self.mesh_filename,
                            graph_filename=self.graph_filename)

        if self.partition_graph:
            self.partition(graph_file=self.graph_filename)

    def process_inputs_and_outputs(self):
        """
        Process the model as an input, then call the parent class' version

        Also generates namelist and streams files
        """
        for entry in self.input_data:
            filename = entry['filename']

            if filename == '<<<model>>>':
                filename, target = ModelStep._process_model(
                    self.config, self.base_work_dir)

                entry['filename'] = filename
                entry['target'] = target

        super().process_inputs_and_outputs()

        if self.cached:
            return

        self.dynamic_model_config(at_setup=True)

        quiet = True
        self._create_model_config()

        if self.make_yaml:
            self._process_yaml(quiet=quiet)
        else:
            self._process_namelists(quiet=quiet)
            self._process_streams(quiet=quiet, remove_unrequested=True)

        self._write_model_config()

    def update_namelist_pio(self):
        """
        Modify the namelist so the number of PIO tasks and the stride between
        them consistent with the number of nodes and cores (one PIO task per
        node).
        """
        config = self.config

        cores = self.ntasks * self.cpus_per_task

        cores_per_node = config.getint('parallel', 'cores_per_node')

        # update PIO tasks based on the machine settings and the available
        # number or cores
        pio_num_iotasks = int(np.ceil(cores / cores_per_node))
        pio_stride = self.ntasks // pio_num_iotasks
        if pio_stride > cores_per_node:
            raise ValueError(f'Not enough nodes for the number of cores.  '
                             f'cores: {cores}, cores per node: '
                             f'{cores_per_node}')

        replacements = {'config_pio_num_iotasks': pio_num_iotasks,
                        'config_pio_stride': pio_stride}

        self.add_model_config_options(options=replacements)

    def partition(self, graph_file='graph.info'):
        """
        Partition the domain for the requested number of tasks

        Parameters
        ----------
        graph_file : str, optional
            The name of the graph file to partition

        """
        ntasks = self.ntasks
        if ntasks > 1:
            executable = self.config.get('parallel', 'partition_executable')
            args = [executable, graph_file, f'{ntasks}']
            check_call(args, self.logger)

    @staticmethod
    def _process_model(config, base_work_dir):
        """ Process the E3SM component model as an input to the step """
        model = config.get('executables', 'component')
        filename = os.path.basename(model)
        copy_executable = config.getboolean('setup', 'copy_executable')
        if copy_executable:
            # make a copy of the model executable, then link to that
            component_subdir = os.path.basename(
                config.get('paths', 'component_path'))
            component_workdir = os.path.join(base_work_dir, component_subdir)
            target = os.path.join(component_workdir, filename)
            try:
                os.makedirs(component_workdir)
            except FileExistsError:
                pass

            try:
                shutil.copy(model, target)
            except FileExistsError:
                pass
        else:
            target = os.path.abspath(model)
        return filename, target

    def _create_model_config(self):
        """
        At setup, create either the yaml or the namelist/streams file for the
        step
        """
        config = self.config
        if self.make_yaml:
            defaults_filename = config.get('model_config', 'defaults')
            self._yaml = PolarisYaml.read(defaults_filename,
                                          streams_section=self.streams_section)
        else:
            defaults_filename = config.get('namelists', 'forward')
            self._namelist = polaris.namelist.ingest(defaults_filename)

            defaults_filename = config.get('streams', 'forward')
            self._streams_tree = etree.parse(defaults_filename)

    def _read_model_config(self):
        """
        At runtime, read either the yaml or the namelist/streams file for the
        step
        """
        if self.make_yaml:
            filename = os.path.join(self.work_dir, self.yaml)
            self._yaml = PolarisYaml.read(filename,
                                          streams_section=self.streams_section)
        else:
            filename = os.path.join(self.work_dir, self.namelist)
            self._namelist = polaris.namelist.ingest(filename)

            filename = os.path.join(self.work_dir, self.streams)
            self._streams_tree = etree.parse(filename)

    def _write_model_config(self):
        """
        At setup or runtime, write either the yaml or the namelist/streams
        file for the step
        """
        step_work_dir = self.work_dir
        if self.make_yaml:
            yaml_filename = f'{step_work_dir}/{self.yaml}'
            if self._yaml is None:
                raise ValueError('Trying to write a yaml file but no yaml '
                                 'object was created.')
            self._yaml.write(yaml_filename)
        else:
            namelist_filename = f'{step_work_dir}/{self.namelist}'
            if self._namelist is None:
                raise ValueError('Trying to write a namelist file but no '
                                 'namelist object was created.')
            polaris.namelist.write(self._namelist, namelist_filename)

            streams_filename = f'{step_work_dir}/{self.streams}'
            if self._streams_tree is None:
                raise ValueError('Trying to write a streams file but no '
                                 'streams XML tree was created.')
            polaris.streams.write(self._streams_tree, streams_filename)
        # set these back to None because we don't need to keep them around
        # and the streams tree can't be pickled
        self._yaml = None
        self._namelist = None
        self._streams_tree = None

    def _process_namelists(self, quiet):
        """
        Processes changes to a namelist file from the files and dictionaries
        in the step's ``model_config_data``.
        """
        if not self.model_config_data:
            return

        replacements = dict()

        for entry in self.model_config_data:
            if 'namelist' in entry:
                options = polaris.namelist.parse_replacements(
                    entry['package'], entry['namelist'])
                replacements.update(options)
            for config_model in self.config_models:
                if 'options' in entry and \
                        entry['config_model'] == config_model:
                    # this is a dictionary of replacement model config options
                    options = entry['options']
                    options = self.map_yaml_options(options=entry['options'],
                                                    config_model=config_model)
                    options = self.map_yaml_to_namelist(options)
                    replacements.update(options)
                if 'yaml' in entry:
                    yaml = PolarisYaml.read(
                        filename=entry['yaml'], package=entry['package'],
                        replacements=entry['replacements'], model=config_model,
                        streams_section=self.streams_section)

                    configs = self.map_yaml_configs(configs=yaml.configs,
                                                    config_model=config_model)
                    configs = self.map_yaml_to_namelist(configs)
                    replacements.update(configs)

        if not quiet:
            print(f'Warning: replacing namelist options in {self.namelist}')
            for key, value in replacements.items():
                print(f'{key} = {value}')

        if self._streams_tree is None:
            raise ValueError('Trying to update a namelist object but it was '
                             'never created.')
        self._namelist = polaris.namelist.replace(self._namelist, replacements)

    def _process_streams(self, quiet, remove_unrequested):
        """
        Processes changes to a streams file from the files and dictionaries
        in the step's ``streams_data``.
        """
        if not self.streams_data:
            return

        config = self.config

        # generate the streams file
        tree = None

        processed_registry_filename = None
        if config.has_section('registry') and \
                config.has_option('registry', 'processed'):
            processed_registry_filename = config.get('registry', 'processed')

        for entry in self.streams_data:
            package = entry['package']
            replacements = entry['replacements']
            if 'streams' in entry:
                streams_filename = entry['streams']
                if not quiet:
                    print(f'{package} {streams_filename}')

                tree = polaris.streams.read(
                    package=package, streams_filename=streams_filename,
                    replacements=replacements, tree=tree)
            for config_model in self.config_models:
                if 'yaml' in entry:
                    tree = self._process_yaml_streams(
                        entry['yaml'], package, replacements, config_model,
                        processed_registry_filename, tree, quiet)

            if not quiet and replacements is not None:
                for key, value in replacements.items():
                    print(f'{key} = {value}')

        if tree is None:
            # nothing to add
            return

        if self._streams_tree is None:
            raise ValueError('Trying to update a streams XML tree but it was '
                             'never created.')

        defaults = next(self._streams_tree.iter('streams'))
        streams = next(tree.iter('streams'))

        for stream in streams:
            polaris.streams.update_defaults(stream, defaults)

        if remove_unrequested:
            # during setup, we remove any streams that aren't requested but
            # at runtime we don't want to do this because we would lose any
            # streams added only during setup.
            for default in defaults:
                found = False
                for stream in streams:
                    if stream.attrib['name'] == default.attrib['name']:
                        found = True
                        break
                if not found:
                    defaults.remove(default)

    def _process_yaml_streams(self, yaml_filename, package, replacements,
                              config_model, processed_registry_filename,
                              tree, quiet):
        if not quiet:
            print(f'{package} {yaml_filename}')

        yaml = PolarisYaml.read(filename=yaml_filename,
                                package=package,
                                replacements=replacements,
                                model=config_model,
                                streams_section=self.streams_section)
        assert processed_registry_filename is not None
        new_tree = yaml_to_mpas_streams(
            processed_registry_filename, yaml)
        tree = polaris.streams.update_tree(tree, new_tree)
        return tree

    def _process_yaml(self, quiet):
        """
        Processes changes to a yaml file from the files and dictionaries
        in the step's ``model_config_data``.
        """
        if not self.model_config_data:
            return

        if self._yaml is None:
            raise ValueError('Trying to update a yaml object but it was '
                             'never created.')

        if not quiet:
            print(f'Warning: replacing yaml options in {self.yaml}')

        for entry in self.model_config_data:
            if 'namelist' in entry:
                raise ValueError('Cannot generate a yaml config from an MPAS '
                                 'namelist file.')

            for config_model in self.config_models:
                if 'options' in entry and \
                        entry['config_model'] == config_model:
                    # this is a dictionary of replacement model config options
                    options = entry['options']
                    options = self.map_yaml_options(options=entry['options'],
                                                    config_model=config_model)
                    self._yaml.update(options=options, quiet=quiet)
                if 'yaml' in entry:
                    yaml = PolarisYaml.read(
                        filename=entry['yaml'], package=entry['package'],
                        replacements=entry['replacements'], model=config_model,
                        streams_section=self.streams_section)

                    configs = self.map_yaml_configs(configs=yaml.configs,
                                                    config_model=config_model)
                    self._yaml.update(configs=configs, quiet=quiet)


def make_graph_file(mesh_filename, graph_filename='graph.info',
                    weight_field=None):
    """
    Make a graph file from the MPAS mesh for use in the Metis graph
    partitioning software

    Parameters
    ----------
     mesh_filename : str
        The name of the input MPAS mesh file

    graph_filename : str, optional
        The name of the output graph file

    weight_field : str
        The name of a variable in the MPAS mesh file to use as a field of
        weights
    """

    with xr.open_dataset(mesh_filename) as ds:

        nCells = ds.sizes['nCells']

        nEdgesOnCell = ds.nEdgesOnCell.values
        cellsOnCell = ds.cellsOnCell.values - 1
        if weight_field is not None:
            if weight_field in ds:
                raise ValueError(f'weight_field {weight_field} not found in '
                                 f'{mesh_filename}')
            weights = ds[weight_field].values
        else:
            weights = None

    nEdges = 0
    for i in range(nCells):
        for j in range(nEdgesOnCell[i]):
            if cellsOnCell[i][j] != -1:
                nEdges = nEdges + 1

    nEdges = nEdges // 2

    with open(graph_filename, 'w+') as graph:
        if weights is None:
            graph.write(f'{nCells} {nEdges}\n')

            for i in range(nCells):
                for j in range(0, nEdgesOnCell[i]):
                    if cellsOnCell[i][j] >= 0:
                        graph.write(f'{cellsOnCell[i][j] + 1} ')
                graph.write('\n')
        else:
            graph.write(f'{nCells} {nEdges} 010\n')

            for i in range(nCells):
                graph.write(f'{int(weights[i])} ')
                for j in range(0, nEdgesOnCell[i]):
                    if cellsOnCell[i][j] >= 0:
                        graph.write(f'{cellsOnCell[i][j] + 1} ')
                graph.write('\n')
