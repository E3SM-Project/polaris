import argparse
import os
import pickle
import shutil
import sys
import warnings
from typing import Dict, List

from polaris import Task, provenance
from polaris.components import get_components
from polaris.config import PolarisConfigParser
from polaris.io import symlink
from polaris.job import write_job_script
from polaris.machines import discover_machine


def setup_tasks(work_dir, task_list=None, numbers=None, config_file=None,
                machine=None, baseline_dir=None, component_path=None,
                suite_name='custom', cached=None, copy_executable=False,
                clean=False):
    """
    Set up one or more tasks

    Parameters
    ----------
    work_dir : str
        A directory that will serve as the base for creating task
        directories

    task_list : list of str, optional
        Relative paths for a tasks to set up

    numbers : list of str, optional
        Task numbers to setup, as listed from ``polaris list``, optionally with
        a suffix ``c`` to indicate that all steps in that task should be
        cached

    config_file : {str, None}, optional
        Configuration file with custom options for setting up and running tasks

    machine : str, optional
        The name of one of the machines with defined config options, which can
        be listed with ``polaris list --machines``

    baseline_dir : str, optional
        Location of baselines that can be compared to

    component_path : str, optional
        The relative or absolute path to the location where the model and
        default namelists have been built

    suite_name : str, optional
        The name of the suite if tasks are being set up through a suite or
        ``'custom'`` if not

    cached : list of list of str, optional
        For each task in ``tasks``, which steps (if any) should be cached,
        or a list with "_all" as the first entry if all steps in the task
        should be cached

    copy_executable : bool, optional
        Whether to copy the model executable to the work directory

    clean : bool, optional
        Whether to delete the contents of the base work directory before
        setting up tasks

    Returns
    -------
    tasks : dict of polaris.Task
        A dictionary of tasks, with the relative path in the work
        directory as keys
    """
    machine = __get_machine_and_check_params(machine, config_file, task_list,
                                             numbers, cached)

    if work_dir is None:
        print('Warning: no base work directory was provided so setting up in '
              'the current directory.')
        work_dir = os.getcwd()
    work_dir = os.path.abspath(work_dir)

    components = get_components()

    all_tasks = dict()
    for component in components:
        for task in component.tasks.values():
            all_tasks[task.path] = task

    tasks: Dict[str, Task] = dict()
    cached_steps: Dict[str, List[str]] = dict()
    _add_tasks_by_number(numbers, all_tasks, tasks, cached_steps)
    _add_tasks_by_name(task_list, all_tasks, cached, tasks, cached_steps)

    # get the component of the first task.  We'll ensure that all tasks are
    # for this component
    first_path = next(iter(tasks))
    component = tasks[first_path].component

    basic_config = _get_basic_config(config_file, machine, component_path,
                                     component)

    provenance.write(work_dir, tasks, config=basic_config)

    _expand_and_mark_cached_steps(tasks, cached_steps)

    if clean:
        print('')
        print('Cleaning task and step work directories:')
        _clean_tasks_and_steps(tasks, work_dir)
        print('')

    print('Setting up tasks:')
    for path, task in tasks.items():
        setup_task(path, task, config_file, machine, work_dir,
                   baseline_dir, component_path,
                   cached_steps=cached_steps[path],
                   copy_executable=copy_executable)

    _check_dependencies(tasks)

    suite = {'name': suite_name,
             'tasks': tasks,
             'work_dir': work_dir}

    # pickle the task or step dictionary for use at runtime
    pickle_file = os.path.join(suite['work_dir'],
                               f'{suite_name}.pickle')
    with open(pickle_file, 'wb') as handle:
        pickle.dump(suite, handle, protocol=pickle.HIGHEST_PROTOCOL)

    _symlink_load_script(work_dir)

    max_cores, max_of_min_cores = _get_required_cores(tasks)

    print(f'target cores: {max_cores}')
    print(f'minimum cores: {max_of_min_cores}')

    if machine is not None:
        write_job_script(basic_config, machine, max_cores, max_of_min_cores,
                         work_dir, suite=suite_name)

    return tasks


def setup_task(path, task, config_file, machine, work_dir, baseline_dir,
               component_path, cached_steps, copy_executable):
    """
    Set up one or more tasks

    Parameters
    ----------
    path : str
        Relative path for a tasks to set up

    task : polaris.Task
        A task to set up

    config_file : str
        Configuration file with custom options for setting up and running tasks

    machine : str
        The name of one of the machines with defined config options, which can
        be listed with ``polaris list --machines``

    work_dir : str
        A directory that will serve as the base for creating task directories

    baseline_dir : str
        Location of baselines that can be compared to

    component_path : str
        The relative or absolute path to the location where the model and
        default namelists have been built

    cached_steps : list of str
        Which steps (if any) should be cached, identified by a list of
        subdirectories in the component

    copy_executable : bool, optional
        Whether to copy the model executable to the work directory
    """

    print(f'  {path}')

    config = _get_basic_config(config_file, machine, component_path,
                               task.component)

    if copy_executable:
        config.set('setup', 'copy_executable', 'True')

    if 'POLARIS_BRANCH' in os.environ:
        polaris_branch = os.environ['POLARIS_BRANCH']
        config.set('paths', 'polaris_branch', polaris_branch)
    else:
        config.set('paths', 'polaris_branch', os.getcwd())

    task_dir = os.path.join(work_dir, path)
    try:
        os.makedirs(task_dir)
    except OSError:
        pass
    task.work_dir = task_dir
    task.base_work_dir = work_dir

    # add config options specific to the task
    task.config = config
    task.configure()

    # add the baseline directory for this task
    if baseline_dir is not None:
        task.baseline_dir = os.path.join(baseline_dir, path)

    # set the component_path path from the command line if provided
    if component_path is not None:
        component_path = os.path.abspath(component_path)
        config.set('paths', 'component_path', component_path, user=True)

    config.set('task', 'steps_to_run', ' '.join(task.steps_to_run))

    # write out the config file
    task_config = f'{task.name}.cfg'
    task.config_filename = task_config
    with open(os.path.join(task_dir, task_config), 'w') as f:
        config.write(f)

    if len(cached_steps) > 0:
        print_steps = ' '.join(cached_steps)
        print(f'    steps with cached outputs: {print_steps}')

    # iterate over steps
    for step in task.steps.values():
        # make the step directory if it doesn't exist
        step_dir = os.path.join(work_dir, step.path)

        if step.name in task.step_symlinks:
            symlink(step_dir,
                    os.path.join(task_dir, task.step_symlinks[step.name]))

        if step.setup_complete:
            # this is a shared step that has already been set up
            continue
        try:
            os.makedirs(step_dir)
        except OSError:
            pass

        symlink(os.path.join(task_dir, task_config),
                os.path.join(step_dir, task_config))

        step.work_dir = step_dir
        step.base_work_dir = work_dir
        step.config_filename = task_config
        step.config = config

        # set up the step
        step.setup()

        # add the baseline directory for this step
        if baseline_dir is not None:
            step.baseline_dir = os.path.join(baseline_dir, step.path)

        # process input, output, namelist and streams files
        step.process_inputs_and_outputs()

    # wait until we've set up all the steps before pickling because steps may
    # need other steps to be set up
    for step in task.steps.values():
        if step.setup_complete:
            # this is a shared step that has already been set up
            continue

        # pickle the task and step for use at runtime
        pickle_filename = os.path.join(step.work_dir, 'step.pickle')
        with open(pickle_filename, 'wb') as handle:
            pickle.dump(step, handle,
                        protocol=pickle.HIGHEST_PROTOCOL)

        _symlink_load_script(step.work_dir)

        if machine is not None:
            cores = step.cpus_per_task * step.ntasks
            min_cores = step.min_cpus_per_task * step.min_tasks
            write_job_script(config, machine, cores, min_cores,
                             step.work_dir)
        step.setup_complete = True

    # pickle the task and step for use at runtime
    pickle_filename = os.path.join(task.work_dir, 'task.pickle')
    with open(pickle_filename, 'wb') as handle:
        suite = {'name': 'task',
                 'tasks': {task.path: task},
                 'work_dir': task.work_dir}
        pickle.dump(suite, handle, protocol=pickle.HIGHEST_PROTOCOL)

    _symlink_load_script(task_dir)

    if machine is not None:
        max_cores, max_of_min_cores = _get_required_cores({path: task})
        write_job_script(config, machine, max_cores, max_of_min_cores,
                         task_dir)


def main():
    parser = argparse.ArgumentParser(
        description='Set up one or more tasks', prog='polaris setup')
    parser.add_argument("-t", "--task", dest="task",
                        help="Relative path for a task to set up.",
                        metavar="PATH")
    parser.add_argument("-n", "--task_number", nargs='+', dest="task_num",
                        type=str,
                        help="Task number(s) to setup, as listed from "
                             "'polaris list'. Can be a space-separated "
                             "list of task numbers.  A suffix 'c' indicates "
                             "that all steps in the task should use cached "
                             "outputs.", metavar="NUM")
    parser.add_argument("-f", "--config_file", dest="config_file",
                        help="Configuration file for task setup.",
                        metavar="FILE")
    parser.add_argument("-m", "--machine", dest="machine",
                        help="The name of the machine for loading machine-"
                             "related config options.", metavar="MACH")
    parser.add_argument("-w", "--work_dir", dest="work_dir", required=True,
                        help="A base directory for setting up tasks.",
                        metavar="PATH")
    parser.add_argument("-b", "--baseline_dir", dest="baseline_dir",
                        help="Location of baselines that can be compared to.",
                        metavar="PATH")
    parser.add_argument("-p", "--component_path", dest="component_path",
                        help="The path where the component executable and "
                             "default namelists have been built.",
                        metavar="PATH")
    parser.add_argument("--suite_name", dest="suite_name", default="custom",
                        help="The name to use for the 'custom' suite "
                             "containing all setup tasks.",
                        metavar="SUITE")
    parser.add_argument("--cached", dest="cached", nargs='+',
                        help="A list of steps in the task supplied with "
                             "--task that should use cached outputs, or "
                             "'_all' if all steps should be cached.",
                        metavar="STEP")
    parser.add_argument("--copy_executable", dest="copy_executable",
                        action="store_true",
                        help="If the model executable should be copied to the "
                             "work directory.")
    parser.add_argument("--clean", dest="clean", action="store_true",
                        help="If the base work directory should be deleted "
                             "before setting up the tasks.")

    args = parser.parse_args(sys.argv[2:])
    cached = None
    if args.task is None:
        task_list = None
    else:
        task_list = [args.task]
        if args.cached is not None:
            cached = [args.cached]
    setup_tasks(task_list=task_list, numbers=args.task_num,
                config_file=args.config_file, machine=args.machine,
                work_dir=args.work_dir, baseline_dir=args.baseline_dir,
                component_path=args.component_path, suite_name=args.suite_name,
                cached=cached, copy_executable=args.copy_executable,
                clean=args.clean)


def _expand_and_mark_cached_steps(tasks, cached_steps):
    """
    Mark any steps that will be cached.  If any task asked for a step to
    be cached, it will be cached for all tasks that share the step.
    """
    for path, task in tasks.items():
        cached_names = cached_steps[path]
        if len(cached_names) > 0 and cached_names[0] == '_all':
            cached_steps[path] = list(task.steps.keys())

        for step_name in cached_steps[path]:
            task.steps[step_name].cached = True


def _clean_tasks_and_steps(tasks, base_work_dir):
    """
    Remove contents of task and step work directories to start fresh
    """
    print(f'{base_work_dir}:')
    for path, task in tasks.items():
        task_work_dir = os.path.join(base_work_dir, path)
        try:
            shutil.rmtree(task_work_dir)
            print(f' {path}')
        except FileNotFoundError:
            pass

        for step in task.steps.values():
            step_work_dir = os.path.join(base_work_dir, step.path)
            try:
                shutil.rmtree(step_work_dir)
                print(f'  {step.path}')
            except FileNotFoundError:
                pass


def _get_required_cores(tasks):
    """ Get the maximum number of target cores and the max of min cores """

    max_cores = 0
    max_of_min_cores = 0
    for task in tasks.values():
        for step_name in task.steps_to_run:
            step = task.steps[step_name]
            if step.ntasks is None:
                raise ValueError(
                    f'The number of tasks (ntasks) was never set for '
                    f'{task.path} step {step_name}')
            if step.cpus_per_task is None:
                raise ValueError(
                    f'The number of CPUs per task (cpus_per_task) was never '
                    f'set for {task.path} step {step_name}')
            cores = step.cpus_per_task * step.ntasks
            min_cores = step.min_cpus_per_task * step.min_tasks
            max_cores = max(max_cores, cores)
            max_of_min_cores = max(max_of_min_cores, min_cores)

    return max_cores, max_of_min_cores


def __get_machine_and_check_params(machine, config_file, tasks, numbers,
                                   cached):
    if machine is None and 'POLARIS_MACHINE' in os.environ:
        machine = os.environ['POLARIS_MACHINE']

    if machine is None:
        machine = discover_machine()

    if config_file is None and machine is None:
        raise ValueError('At least one of config_file and machine is needed.')

    if config_file is not None and not os.path.exists(config_file):
        raise FileNotFoundError(
            f'The user config file wasn\'t found: {config_file}')

    if tasks is None and numbers is None:
        raise ValueError('At least one of tasks or numbers is needed.')

    if cached is not None:
        if tasks is None:
            warnings.warn('Ignoring "cached" argument because "tasks" was '
                          'not provided')
        elif len(cached) != len(tasks):
            raise ValueError('A list of cached steps must be provided for '
                             'each task in "tasks"')

    return machine


def _get_basic_config(config_file, machine, component_path, component):
    """
    Get a base config parser for the machine and component but not a specific
    task
    """
    config = PolarisConfigParser()

    if config_file is not None:
        config.add_user_config(config_file)

    # start with default polaris config options
    config.add_from_package('polaris', 'default.cfg')

    # add the E3SM config options from mache
    if machine is not None:
        config.add_from_package('mache.machines', f'{machine}.cfg',
                                exception=False)

    # add the polaris machine config file
    if machine is None:
        machine = 'default'
    config.add_from_package('polaris.machines', f'{machine}.cfg')

    if 'POLARIS_BRANCH' in os.environ:
        polaris_branch = os.environ['POLARIS_BRANCH']
        config.set('paths', 'polaris_branch', polaris_branch)
    else:
        config.set('paths', 'polaris_branch', os.getcwd())

    # add the config options for the component
    config.add_from_package(f'polaris.{component.name}',
                            f'{component.name}.cfg')

    component.configure(config)

    # set the component_path path from the command line if provided
    if component_path is not None:
        component_path = os.path.abspath(component_path)
        config.set('paths', 'component_path', component_path, user=True)

    return config


def _add_tasks_by_number(numbers, all_tasks, tasks, cached_steps):
    if numbers is not None:
        keys = list(all_tasks)
        for number in numbers:
            cache_all = False
            if number.endswith('c'):
                cache_all = True
                number = int(number[:-1])
            else:
                number = int(number)

            if number >= len(keys):
                raise ValueError(f'task number {number} is out of range.  '
                                 f'There are only {len(keys)} tasks.')
            path = keys[number]
            if cache_all:
                cached_steps[path] = ['_all']
            else:
                cached_steps[path] = list()
            tasks[path] = all_tasks[path]


def _add_tasks_by_name(task_list, all_tasks, cached, tasks, cached_steps):
    if task_list is not None:
        for index, path in enumerate(task_list):
            if path not in all_tasks:
                raise ValueError(f'Task with path {path} is not in '
                                 f'tasks')
            if cached is not None:
                cached_steps[path] = cached[index]
            else:
                cached_steps[path] = list()
            tasks[path] = all_tasks[path]


def _symlink_load_script(work_dir):
    """ make a symlink to the script for loading the polaris conda env. """
    if 'LOAD_POLARIS_ENV' in os.environ:
        script_filename = os.environ['LOAD_POLARIS_ENV']
        symlink(script_filename,
                os.path.join(work_dir, 'load_polaris_env.sh'))


def _check_dependencies(tasks):
    for task in tasks.values():
        for step in task.steps.values():
            for name, dependency in step.dependencies.items():
                if dependency.work_dir == '':
                    raise ValueError(f'The dependency {name} of '
                                     f'{task.path} step {step.name} was '
                                     f'not set up.')
