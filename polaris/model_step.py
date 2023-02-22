import os
import shutil

import numpy as np
import xarray as xr
from lxml import etree
from mpas_tools.logging import check_call

import polaris.namelist
import polaris.streams
from polaris.step import Step


class ModelStep(Step):
    """
    Attributes
    ----------
    namelist : str
        The name of the namelist file

    streams : str
        The name of the streams file

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

    namelist_data : dict
        a dictionary used internally to keep track of updates to the default
        namelist options from calls to
        :py:meth:`polaris.Step.add_namelist_file`
        and :py:meth:`polaris.Step.add_namelist_options`

    streams_data : dict
        a dictionary used internally to keep track of updates to the default
        streams from calls to :py:meth:`polaris.Step.add_streams_file`
    """
    def __init__(self, test_case, name, subdir=None, ntasks=None,
                 min_tasks=None, openmp_threads=None, max_memory=None,
                 cached=False, namelist=None, streams=None, update_pio=True,
                 make_graph=False, mesh_filename=None, partition_graph=True,
                 graph_filename='graph.info'):
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
        """
        super().__init__(test_case=test_case, name=name, subdir=subdir,
                         cpus_per_task=openmp_threads,
                         min_cpus_per_task=openmp_threads, ntasks=ntasks,
                         min_tasks=min_tasks, openmp_threads=openmp_threads,
                         max_memory=max_memory, cached=cached)

        component = test_case.component.name
        if namelist is None:
            namelist = f'namelist.{component}'

        if streams is None:
            streams = f'streams.{component}'

        self.namelist = namelist
        self.streams = streams
        self.update_pio = update_pio
        self.make_graph = make_graph
        self.mesh_filename = mesh_filename
        self.partition_graph = partition_graph
        self.graph_filename = graph_filename

        self.add_input_file(filename='<<<model>>>')

        self.namelist_data = dict()
        self.streams_data = dict()

    def setup(self):
        """ Setup the command-line arguments """
        config = self.config
        component = config.get('executables', 'component')
        model_basename = os.path.basename(component)
        self.args = [f'./{model_basename}', '-n', self.namelist,
                     '-s', self.streams]

    def set_model_resources(self, ntasks=None, min_tasks=None,
                            openmp_threads=None, max_memory=None):
        """
        Update the resources for the step.  This can be done within init,
        ``setup()`` or ``runtime_setup()`` for the step that this step
        belongs to, or init, ``configure()`` or ``run()`` for the test case
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

    def add_namelist_file(self, package, namelist, out_name=None,
                          mode='forward'):
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

        out_name : str, optional
            The name of the namelist file to write out, ``namelist.<core>`` by
            default

        mode : {'init', 'forward'}, optional
            The mode that the model will run in
        """
        if out_name is None:
            out_name = f'namelist.{self.component.name}'

        if out_name not in self.namelist_data:
            self.namelist_data[out_name] = list()

        namelist_list = self.namelist_data[out_name]

        namelist_list.append(dict(package=package, namelist=namelist,
                                  mode=mode))

    def add_namelist_options(self, options, out_name=None, mode='forward'):
        """
        Add the namelist replacements to be parsed when generating a namelist
        file if and when the step gets set up.

        Parameters
        ----------
        options : dict
            A dictionary of options and value to replace namelist options with
            new values

        out_name : str, optional
            The name of the namelist file to write out, ``namelist.<core>`` by
            default

        mode : {'init', 'forward'}, optional
            The mode that the model will run in
        """
        if out_name is None:
            out_name = f'namelist.{self.component.name}'

        if out_name not in self.namelist_data:
            self.namelist_data[out_name] = list()

        namelist_list = self.namelist_data[out_name]

        namelist_list.append(dict(options=options, mode=mode))

    def update_namelist_at_runtime(self, options, out_name=None):
        """
        Update an existing namelist file with additional options.  This would
        typically be used for namelist options that are only known at runtime,
        not during setup, typically those related to the number of nodes and
        cores.

        Parameters
        ----------
        options : dict
            A dictionary of options and value to replace namelist options with
            new values

        out_name : str, optional
            The name of the namelist file to write out, ``namelist.<core>`` by
            default
        """

        if out_name is None:
            out_name = f'namelist.{self.component.name}'

        print(f'Warning: replacing namelist options in {out_name}')
        for key, value in options.items():
            print(f'{key} = {value}')

        filename = os.path.join(self.work_dir, out_name)

        namelist = polaris.namelist.ingest(filename)

        namelist = polaris.namelist.replace(namelist, options)

        polaris.namelist.write(namelist, filename)

    def add_streams_file(self, package, streams, template_replacements=None,
                         out_name=None, mode='forward'):
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

        out_name : str, optional
            The name of the streams file to write out, ``streams.<core>`` by
            default

        mode : {'init', 'forward'}, optional
            The mode that the model will run in
        """
        if out_name is None:
            out_name = f'streams.{self.component.name}'

        if out_name not in self.streams_data:
            self.streams_data[out_name] = list()

        self.streams_data[out_name].append(
            dict(package=package, streams=streams,
                 replacements=template_replacements, mode=mode))

    def update_streams_at_runtime(self, package, streams,
                                  template_replacements, out_name=None):
        """
        Update the streams files during the run phase of this step using the
        given template and replacements.  This may be useful for updating
        streams based on config options that a user may have changed before
        running the step.

        Parameters
        ----------
        package : Package
            The package name or module object that contains the streams file

        streams : str
            The name of a Jinja2 template to be rendered with replacements

        template_replacements : dict
            A dictionary of replacements

        out_name : str, optional
            The name of the streams file to write out, ``streams.<core>`` by
            default
        """

        if out_name is None:
            out_name = f'streams.{self.component.name}'

        if template_replacements is not None:
            print(f'Warning: updating streams in {out_name} using the '
                  f'following template and replacements:')
            print(f'{package} {streams}')
            for key, value in template_replacements.items():
                print(f'{key} = {value}')

        filename = os.path.join(self.work_dir, out_name)

        tree = etree.parse(filename)
        tree = polaris.streams.read(package, streams, tree=tree,
                                    replacements=template_replacements)
        polaris.streams.write(tree, filename)

    def runtime_setup(self):
        """
        Update PIO namelist options, make graph file, and partition graph file
        (if any of these are requested)
        """

        namelist = self.namelist

        if self.update_pio:
            self.update_namelist_pio(namelist)

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

        self._generate_namelists()
        self._generate_streams()

    def update_namelist_pio(self, out_name=None):
        """
        Modify the namelist so the number of PIO tasks and the stride between
        them consistent with the number of nodes and cores (one PIO task per
        node).

        Parameters
        ----------
        out_name : str, optional
            The name of the namelist file to write out, ``namelist.<core>`` by
            default
        """
        config = self.config

        cores = self.ntasks * self.cpus_per_task

        if out_name is None:
            out_name = f'namelist.{self.component.name}'

        cores_per_node = config.getint('parallel', 'cores_per_node')

        # update PIO tasks based on the machine settings and the available
        # number or cores
        pio_num_iotasks = int(np.ceil(cores / cores_per_node))
        pio_stride = self.ntasks // pio_num_iotasks
        if pio_stride > cores_per_node:
            raise ValueError(f'Not enough nodes for the number of cores.  '
                             f'cores: {cores}, cores per node: '
                             f'{cores_per_node}')

        replacements = {'config_pio_num_iotasks': f'{pio_num_iotasks}',
                        'config_pio_stride': f'{pio_stride}'}

        self.update_namelist_at_runtime(options=replacements,
                                        out_name=out_name)

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
        model = config.get('executables', 'component')
        filename = os.path.basename(model)
        copy_executable = config.getboolean('setup', 'copy_executable')
        if copy_executable:
            # make a copy of the model executable, then link to that
            mpas_subdir = os.path.basename(
                config.get('paths', 'mpas_model'))
            mpas_workdir = os.path.join(base_work_dir, mpas_subdir)
            target = os.path.join(mpas_workdir, filename)
            try:
                os.makedirs(mpas_workdir)
            except FileExistsError:
                pass

            try:
                shutil.copy(model, target)
            except FileExistsError:
                pass
        else:
            target = os.path.abspath(model)
        return filename, target

    def _generate_namelists(self):
        """
        Writes out a namelist file in the work directory with new values given
        by parsing the files and dictionaries in the step's ``namelist_data``.
        """

        if self.cached:
            # no need for namelists
            return

        step_work_dir = self.work_dir
        config = self.config

        for out_name in self.namelist_data:

            replacements = dict()

            mode = None

            for entry in self.namelist_data[out_name]:
                if mode is None:
                    mode = entry['mode']
                else:
                    assert mode == entry['mode']
                if 'options' in entry:
                    # this is a dictionary of replacement namelist options
                    options = entry['options']
                else:
                    options = polaris.namelist.parse_replacements(
                        entry['package'], entry['namelist'])
                replacements.update(options)

            defaults_filename = config.get('namelists', mode)
            out_filename = f'{step_work_dir}/{out_name}'

            namelist = polaris.namelist.ingest(defaults_filename)

            namelist = polaris.namelist.replace(namelist, replacements)

            polaris.namelist.write(namelist, out_filename)

    def _generate_streams(self):
        """
        Writes out a streams file in the work directory with new values given
        by parsing the files and dictionaries in the step's ``streams_data``.
        """
        if self.cached:
            # no need for streams
            return

        step_work_dir = self.work_dir
        config = self.config

        for out_name in self.streams_data:

            # generate the streams file
            tree = None

            mode = None

            for entry in self.streams_data[out_name]:
                if mode is None:
                    mode = entry['mode']
                else:
                    assert mode == entry['mode']

                tree = polaris.streams.read(
                    package=entry['package'],
                    streams_filename=entry['streams'],
                    replacements=entry['replacements'], tree=tree)

            if tree is None:
                raise ValueError('No streams were added to the streams file.')

            defaults_filename = config.get('streams', mode)
            out_filename = f'{step_work_dir}/{out_name}'

            defaults_tree = etree.parse(defaults_filename)

            defaults = next(defaults_tree.iter('streams'))
            streams = next(tree.iter('streams'))

            for stream in streams:
                polaris.streams.update_defaults(stream, defaults)

            # remove any streams that aren't requested
            for default in defaults:
                found = False
                for stream in streams:
                    if stream.attrib['name'] == default.attrib['name']:
                        found = True
                        break
                if not found:
                    defaults.remove(default)

            polaris.streams.write(defaults_tree, out_filename)


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
