import grp
import logging
import os
import shutil
import stat

import progressbar
from mache import MachineInfo

from polaris.config import PolarisConfigParser
from polaris.io import download, imp_res, symlink
from polaris.validate import compare_variables


class Step:
    """
    The base class for a step of a tasks, such as setting up a mesh,
    creating an initial condition, or running the component forward in time.
    The step is the smallest unit of work in polaris that can be run on its
    own by a user, though users will typically run full tasks or suites.

    Below, the terms "input" and "output" refer to inputs and outputs to the
    step itself, not necessarily the MPAS model.  In fact, the MPAS model
    itself is often an input to the step.

    Attributes
    ----------
    name : str
        the name of the step

    component : polaris.Component
        The component the step belongs to

    subdir : str
        the subdirectory for the step

    path : str
        the path within the base work directory of the step, made up of
        ``component``, the task's ``subdir`` and the step's ``subdir``

    cpus_per_task : int, optional
        the number of cores per task the step would ideally use.  If
        fewer cores per node are available on the system, the step will
        run on all available cores as long as this is not below
        ``min_cpus_per_task``

    min_cpus_per_task : int, optional
        the number of cores per task the step requires.  If the system
        has fewer than this number of cores per node, the step will fail

    ntasks : int, optional
        the number of tasks the step would ideally use.  If too few
        cores are available on the system to accommodate the number of
        tasks and the number of cores per task, the step will run on
        fewer tasks as long as as this is not below ``min_tasks``

    min_tasks : int, optional
        the number of tasks the step requires.  If the system has too
        few cores to accommodate the number of tasks and cores per task,
        the step will fail

    openmp_threads : int
        the number of OpenMP threads to use

    max_memory : int
        the amount of memory that the step is allowed to use in MB.
        This is currently just a placeholder for later use with task
        parallelism

    input_data : list of dict
        a list of dict used to define input files typically to be
        downloaded to a database and/or symlinked in the work directory

    inputs : list of str
        a list of absolute paths of input files produced from ``input_data`` as
        part of setting up the step.  These input files must all exist at run
        time or the step will raise an exception

    outputs : list of str
        a list of absolute paths of output files produced by this step (or
        cached) and available as inputs to other tasks and steps.  These
        files must exist after the task has run or an exception will be raised

    dependencies : dict of polaris.Step
        A dictionary of steps that this step depends on (i.e. it can't run
        until they have finished). Dependencies are used when the names of
        the files produced by the dependency aren't known at setup (e.g.
        because they depend on config options or data read in from files).
        Under other circumstances, it is sufficient to indicate that an output
        file from another step is an input of this step to establish a
        dependency.

    is_dependency : bool
        Whether this step is the dependency of one or more other steps.

    tasks : dict
        The tasks this step is used in

    config : polaris.config.PolarisConfigParser
        Configuration options for this task, a combination of the defaults
        for the machine, core and configuration

    machine_info : mache.MachineInfo
        Information about E3SM supported machines

    config_filename : str
        The local name of the config file that ``config`` has been written to
        during setup and read from during run

    work_dir : str
        The step's work directory, defined during setup as the combination
        of ``base_work_dir`` and ``path``

    base_work_dir : str
        The base work directory

    baseline_dir : str
        Location of the same task within the baseline work directory,
        for use in comparing variables and timers

    validate_vars : dict of list
        A list of variables for each output file for which a baseline
        comparison should be performed if a baseline run has been provided. The
        baseline validation is performed after the step has run.

    logger : logging.Logger
        A logger for output from the step

    log_filename : str
        At run time, the name of a log file where output/errors from the step
        are being logged, or ``None`` if output is to stdout/stderr

    cached : bool
        Whether to get all of the outputs for the step from the database of
        cached outputs for this component

    run_as_subprocess : bool
        Whether to run this step as a subprocess, rather than just running
        it directly from the task.  It is useful to run a step as a
        subprocess if there is not a good way to redirect output to a log
        file (e.g. if the step calls external code that, in turn, calls
        additional subprocesses).

    args : {list of str, None}
        A list of command-line arguments to call in parallel
    """

    def __init__(self, component, name, subdir=None, indir=None,
                 cpus_per_task=1, min_cpus_per_task=1, ntasks=1, min_tasks=1,
                 openmp_threads=1, max_memory=None, cached=False,
                 run_as_subprocess=False):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        cpus_per_task : int, optional
            the number of cores per task the step would ideally use.  If
            fewer cores per node are available on the system, the step will
            run on all available cores as long as this is not below
            ``min_cpus_per_task``

        min_cpus_per_task : int, optional
            the number of cores per task the step requires.  If the system
            has fewer than this number of cores per node, the step will fail

        ntasks : int, optional
            the number of tasks the step would ideally use.  If too few
            cores are available on the system to accommodate the number of
            tasks and the number of cores per task, the step will run on
            fewer tasks as long as as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has too
            few cores to accommodate the number of tasks and cores per task,
            the step will fail

        openmp_threads : int
            the number of OpenMP threads to use

        max_memory : int, optional
            the amount of memory that the step is allowed to use in MB.
            This is currently just a placeholder for later use with task
            parallelism

        cached : bool, optional
            Whether to get all of the outputs for the step from the database of
            cached outputs for this component

        run_as_subprocess : bool
            Whether to run this step as a subprocess, rather than just running
            it directly from the task.  It is useful to run a step as a
            subprocess if there is not a good way to redirect output to a log
            file (e.g. if the step calls external code that, in turn, calls
            additional subprocesses).
        """
        self.name = name
        self.component = component
        if subdir is not None:
            self.subdir = subdir
        elif indir is not None:
            self.subdir = os.path.join(indir, name)
        else:
            self.subdir = name

        self.cpus_per_task = cpus_per_task
        self.min_cpus_per_task = min_cpus_per_task
        self.ntasks = ntasks
        self.min_tasks = min_tasks
        self.openmp_threads = openmp_threads
        self.max_memory = max_memory

        self.path = os.path.join(self.component.name, self.subdir)

        self.run_as_subprocess = run_as_subprocess

        # child steps (or tasks) will add to these
        self.input_data = list()
        self.inputs = list()
        self.outputs = list()
        self.args = None
        self.dependencies = dict()
        self.is_dependency = False
        self.tasks = dict()

        # these will be set later during setup, dummy placeholders for now
        self.config = PolarisConfigParser()
        self.machine_info = MachineInfo(machine='default')
        self.config_filename = ""
        self.work_dir = ""
        self.base_work_dir = ""
        # may be set during setup if there is a baseline for comparison
        self.baseline_dir = None
        self.validate_vars = dict()
        self.setup_complete = False

        # these will be set before running the step, dummy placeholders for now
        self.logger = logging.getLogger('dummy')
        self.log_filename = None

        # output caching
        self.cached = cached

    def set_resources(self, cpus_per_task=None, min_cpus_per_task=None,
                      ntasks=None, min_tasks=None, openmp_threads=None,
                      max_memory=None):
        """
        Update the resources for the subtask.  This can be done within init,
        ``setup()`` or ``runtime_setup()`` of this step, or init,
        ``configure()`` or ``run()`` for the task that this step belongs
        to.

        Parameters
        ----------
        cpus_per_task : int, optional
            the number of cores per task the step would ideally use.  If
            fewer cores per node are available on the system, the step will
            run on all available cores as long as this is not below
            ``min_cpus_per_task``

        min_cpus_per_task : int, optional
            the number of cores per task the step requires.  If the system
            has fewer than this number of cores per node, the step will fail

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
        if cpus_per_task is not None:
            self.cpus_per_task = cpus_per_task
        if min_cpus_per_task is not None:
            self.min_cpus_per_task = min_cpus_per_task
        if ntasks is not None:
            self.ntasks = ntasks
        if min_tasks is not None:
            self.min_tasks = min_tasks
        if openmp_threads is not None:
            self.openmp_threads = openmp_threads
        if max_memory is not None:
            self.max_memory = max_memory

    def constrain_resources(self, available_resources):
        """
        Constrain ``cpus_per_task`` and ``ntasks`` based on the number of
        cores available to this step

        Parameters
        ----------
        available_resources : dict
            A dictionary containing available resources (cores, tasks, nodes
            and cores_per_node)
        """
        mpi_allowed = available_resources['mpi_allowed']
        if not mpi_allowed and self.ntasks > 1:
            raise ValueError(
                'You are trying to run an MPI job on a login node.\n'
                'Please switch to a compute node.')

        available_cores = available_resources['cores']
        cores_per_node = available_resources['cores_per_node']
        self.cpus_per_task = min(self.cpus_per_task,
                                 min(available_cores, cores_per_node))
        if self.cpus_per_task < self.min_cpus_per_task:
            raise ValueError(
                f'Available cpus_per_task ({self.cpus_per_task}) is below the '
                f'minimum of {self.min_cpus_per_task} for step {self.name}')

        available_tasks = available_cores // self.cpus_per_task
        self.ntasks = min(self.ntasks, available_tasks)

        if self.ntasks < self.min_tasks:
            raise ValueError(
                f'Available number of MPI tasks ({self.ntasks}) is below the '
                f'minimum of {self.min_tasks} for step {self.name}')

    def setup(self):
        """
        Set up the task in the work directory, including downloading any
        dependencies.  The step should override this function to perform setup
        operations such as generating namelist and streams files, adding inputs
        and outputs.
        """
        pass

    def runtime_setup(self):
        """
        Update attributes of the step at runtime before calling the ``run()``
        method.  The most common reason to override this method is to
        determine the number of cores and threads to run with.  It may also
        be useful for performing small (python) tasks such as creating
        graph and partition files before running a parallel command. When
        running with parallel tasks in the future, this method will be called
        for each step in serial before steps are run in task parallel.
        """
        pass

    def run(self):
        """
        Run the step.  Every child class must override this method to perform
        the main work.
        """
        pass

    def add_input_file(self, filename=None, target=None, database=None,
                       database_component=None, url=None, work_dir_target=None,
                       package=None, copy=False):
        """
        Add an input file to the step (but not necessarily to the MPAS model).
        The file can be local, a symlink to a file that will be created in
        another step, a symlink to a file in one of the databases for files
        cached after download, and/or come from a specified URL.

        Parameters
        ----------
        filename : str, optional
            The relative path of the input file within the step's work
            directory. The default is the file name (without the path) of
            ``target``.

        target : str, optional
            A file that will be the target of a symlink to ``filename``.  If
            ``database`` is not specified, this should be an absolute path or a
            relative path from the step's work directory.  If ``database`` is
            specified, this is a relative path within the database and the name
            of the remote file to download.

        database : str, optional
            The name of a database for caching local files.  This will be a
            subdirectory of the local cache directory for this core.  If
            ``url`` is not provided, the URL for downloading the file will be
            determined by combining the base URL of the data server, the
            relative path for the core, ``database`` and ``target``.

        database_component : {'ocean', 'seaice', 'landice', None}, optional
            The prefix of a database root that the database resides in.  By
            default this is the component name for this step.  The suffix
            ``_database_root`` is appended to this string to determine the
            config option where the database root resides on the local machine.

        url : str, optional
            The URL (including file name) for downloading the file.  This
            option should be set if the file is not in a database on the data
            server. The ``filename``, ``target`` and ``database`` are not
            added to URL even if they are provided.

        work_dir_target : str, optional
            Same as ``target`` but with a path relative to the base work
            directory.  This is useful if it is not easy to determine the
            relative path between the step's work directory and the target.

        package : str or package, optional
            A package within ``polaris`` from which the file should be linked

        copy : bool, optional
            Whether to make a copy of the file, rather than a symlink
        """
        if filename is None:
            if target is None:
                raise ValueError('At least one of local_name and target are '
                                 'required.')
            filename = os.path.basename(target)

        self.input_data.append(dict(filename=filename, target=target,
                                    database=database,
                                    database_component=database_component,
                                    url=url, work_dir_target=work_dir_target,
                                    package=package, copy=copy))

    def add_output_file(self, filename, validate_vars=None):
        """
        Add the output file that must be produced by this step and may be made
        available as an input to steps, perhaps in other tasks.  This file
        must exist after the task has run or an exception will be raised.

        Optionally, a list of variables can be provided for validation against
        a baseline (if one is provided), once the step has been run.

        Parameters
        ----------
        filename : str
            The relative path of the output file within the step's work
            directory

        validate_vars : list, optional
            A list of variable names to compare with a baseline (if one is
            provided)
        """
        self.outputs.append(filename)
        if validate_vars is not None:
            self.validate_vars[filename] = validate_vars

    def add_dependency(self, step, name=None):
        """
        Add `step` as a dependency of this step (i.e. this step can't run
        until the dependency has finished). A dependency should be used when
        the names of the files produced by the dependency aren't known at setup
        (e.g. because they depend on config options or data read in from
        files). Under other circumstances, a dependency can be established by
        indicating that an output (added with the ``add_output_file()`` method)
        from another step is an input (added with ``add_input_file()``) of this
        step .

        Parameters
        ----------
        step : polaris.Step
            The step that is a dependency

        name : str, optional
            The name of the step used to access it in the ``dependencies``
            dictionary.  By default, it is ``step.name`` but another name may
            be required if 2 dependencies have the same ``step.name``.
        """
        if name is None:
            name = step.name
        if name in self.dependencies:
            raise ValueError('Adding a dependency that is already in '
                             'dependencies.')
        self.dependencies[name] = step
        step.is_dependency = True
        step.add_output_file('step_after_run.pickle')
        filename = f'dependencies/{name}_after_run.pickle'
        target = f'{step.path}/step_after_run.pickle'
        self.add_input_file(filename=filename, work_dir_target=target)

    def validate_baselines(self):
        """
        Compare variables between output files in this step and in the same
        step from a baseline run if one was provided.

        Returns
        -------
        compared : bool
            Whether a baseline comparison was performed

        success : bool
            Whether the outputs were successfully validated against a baseline
        """
        if self.work_dir is None:
            raise ValueError('The work directory must be set before the step '
                             'outputs can be validated against baselines.')
        compared = False
        success = True
        if self.baseline_dir is not None:
            for filename, variables in self.validate_vars.items():
                logger = self.logger
                filename = str(filename)

                this_filename = os.path.join(self.work_dir, filename)
                baseline_filename = os.path.join(self.baseline_dir, filename)
                result = compare_variables(
                    variables, this_filename, baseline_filename, logger=logger)
                success = success and result
                compared = True
        return compared, success

    def process_inputs_and_outputs(self):
        """
        Process the inputs to and outputs from a step added with
        :py:meth:`polaris.Step.add_input_file` and
        :py:meth:`polaris.Step.add_output_file`.  This includes downloading
        files, making symlinks, and converting relative paths to absolute
        paths.
       """
        component = self.component.name
        step_dir = self.work_dir
        config = self.config
        base_work_dir = self.base_work_dir

        # process the outputs first because cached outputs will add more inputs
        if self.cached:
            # forget about the inputs -- we won't used them, but we will add
            # the cached outputs as inputs
            self.input_data = list()
            for output in self.outputs:
                filename = os.path.join(self.path, output)
                if filename not in self.component.cached_files:
                    raise ValueError(f'The file {filename} has not been added '
                                     f'to the cache database')
                target = self.component.cached_files[filename]
                self.add_input_file(
                    filename=output,
                    target=target,
                    database='polaris_cache')

        inputs = []
        databases_with_downloads = set()
        for entry in self.input_data:
            input_file, database_subdirs = Step._process_input(
                entry, config, base_work_dir, component, step_dir)
            if database_subdirs is not None:
                databases_with_downloads.update(database_subdirs)
            inputs.append(input_file)
        self.inputs = inputs

        if len(databases_with_downloads) > 0:
            self._fix_permissions(databases_with_downloads)

        # inputs are already absolute paths, convert outputs to absolute paths
        self.outputs = [os.path.abspath(os.path.join(step_dir, filename)) for
                        filename in self.outputs]

    @staticmethod
    def _process_input(entry, config, base_work_dir, component, step_dir):
        database_subdirs = None
        filename = entry['filename']
        target = entry['target']
        database = entry['database']
        database_component = entry['database_component']
        url = entry['url']
        work_dir_target = entry['work_dir_target']
        package = entry['package']
        copy = entry['copy']

        if package is not None:
            if target is None:
                target = filename
            target = str(imp_res.as_file(
                imp_res.files(package).joinpath(target)))

        if work_dir_target is not None:
            target = os.path.join(base_work_dir, work_dir_target)

        if target is not None:
            download_target = target
        else:
            download_target = filename

        download_path = None

        if database is not None:
            # we're downloading a file to a cache of a database (if it's
            # not already there.
            if database_component is None:
                database_component = component

            if url is None:
                base_url = config.get('download', 'server_base_url')
                url = f'{base_url}/{database_component}/{database}/{target}'

            database_root = config.get('paths', 'database_root')
            download_path = os.path.join(database_root, database_component,
                                         database, download_target)
            if not os.path.exists(download_path):
                database_subdirs = {
                    database_root,
                    os.path.join(database_root, database_component),
                    os.path.join(database_root, database_component, database)
                }
        elif url is not None:
            download_path = download_target

        if url is not None:
            download_target = download(url, download_path, config)
            if target is not None:
                # this is the absolute path that we presumably want
                target = download_target

        if target is not None:
            filepath = os.path.join(step_dir, filename)
            dirname = os.path.dirname(filepath)
            if copy:
                shutil.copy(target, filepath)
            else:
                try:
                    os.makedirs(dirname)
                except FileExistsError:
                    pass
                symlink(target, filepath)
            input_file = os.path.join(dirname, target)
        else:
            input_file = os.path.join(step_dir, filename)

        input_file = os.path.abspath(input_file)

        return input_file, database_subdirs

    def _fix_permissions(self, databases):  # noqa: C901
        """
        Fix permissions on the databases where files were downloaded so
        everyone in the group can read/write to them
        """
        config = self.config

        if not config.has_option('e3sm_unified', 'group'):
            return

        group = config.get('e3sm_unified', 'group')

        new_uid = os.getuid()
        new_gid = grp.getgrnam(group).gr_gid

        write_perm = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP |
                      stat.S_IWGRP | stat.S_IROTH)
        exec_perm = (stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR |
                     stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP |
                     stat.S_IROTH | stat.S_IXOTH)

        mask = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO

        print('changing permissions on downloaded files')

        # first the base directories that don't seem to be included in
        # os.walk()
        for directory in databases:
            dir_stat = os.stat(directory)

            perm = dir_stat.st_mode & mask

            if dir_stat.st_uid != new_uid:
                # current user doesn't own this dir so let's move on
                continue

            if perm == exec_perm and dir_stat.st_gid == new_gid:
                continue

            try:
                os.chown(directory, new_uid, new_gid)
                os.chmod(directory, exec_perm)
            except OSError:
                continue

        files_and_dirs = []
        for base in databases:
            for root, dirs, files in os.walk(base):
                files_and_dirs.extend(dirs)
                files_and_dirs.extend(files)

        widgets = [progressbar.Percentage(), ' ', progressbar.Bar(),
                   ' ', progressbar.ETA()]
        bar = progressbar.ProgressBar(widgets=widgets,
                                      maxval=len(files_and_dirs)).start()
        progress = 0
        for base in databases:
            for root, dirs, files in os.walk(base):
                for directory in dirs:
                    progress += 1
                    bar.update(progress)

                    directory = os.path.join(root, directory)

                    try:
                        dir_stat = os.stat(directory)
                    except OSError:
                        continue

                    if dir_stat.st_uid != new_uid:
                        # current user doesn't own this dir so let's move on
                        continue

                    perm = dir_stat.st_mode & mask

                    if perm == exec_perm and dir_stat.st_gid == new_gid:
                        continue

                    try:
                        os.chown(directory, new_uid, new_gid)
                        os.chmod(directory, exec_perm)
                    except OSError:
                        continue

                for file_name in files:
                    progress += 1
                    bar.update(progress)
                    file_name = os.path.join(root, file_name)
                    try:
                        file_stat = os.stat(file_name)
                    except OSError:
                        continue

                    if file_stat.st_uid != new_uid:
                        # current user doesn't own this file so let's move on
                        continue

                    perm = file_stat.st_mode & mask

                    if perm & stat.S_IXUSR:
                        # executable, so make sure others can execute it
                        new_perm = exec_perm
                    else:
                        new_perm = write_perm

                    if perm == new_perm and file_stat.st_gid == new_gid:
                        continue

                    try:
                        os.chown(file_name, new_uid, new_gid)
                        os.chmod(file_name, new_perm)
                    except OSError:
                        continue

        bar.finish()
        print('  done.')
