import logging
import os

from polaris.config import PolarisConfigParser


class Task:
    """
    The base class for tasks---such as a decomposition, threading or
    restart test---that are made up of one or more steps

    Attributes
    ----------
    name : str
        the name of the task

    component : polaris.Component
        The component the task belongs to

    steps : dict
        A dictionary of steps in the task with step names as keys

    step_symlinks : dict
        A dictionary of symlink paths within the test case's work directory
        to shared steps outside the test case

    steps_to_run : list
        A list of the steps to run when ``run()`` gets called.  This list
        includes all steps by default but can be replaced with a list of only
        those tasks that should run by default if some steps are optional and
        should be run manually by the user.

    subdir : str
        the subdirectory for the task

    path : str
        the path within the base work directory of the task, made up of
        ``component`` and the task's ``subdir``

    config : polaris.config.PolarisConfigParser
        Configuration options for this task, a combination of the defaults
        for the machine, core and configuration

    config_filename : str
        The local name of the config file that ``config`` has been written to
        during setup and read from during run

    work_dir : str
        The task's work directory, defined during setup as the combination
        of ``base_work_dir`` and ``path``

    base_work_dir : str
        The base work directory

    stdout_logger : logging.Logger
        A logger for output from the task that goes to stdout regardless
        of whether ``logger`` is a log file or stdout

    logger : logging.Logger
        A logger for output from the task

    log_filename : str
        At run time, the name of a log file where output/errors from the task
        are being logged, or ``None`` if output is to stdout/stderr

    new_step_log_file : bool
        Whether to create a new log file for each step or to log output to a
        common log file for the whole task.  The latter is used when
        running the task as part of a suite
    """

    def __init__(self, component, name, subdir=None, indir=None):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            the component that this task belongs to

        name : str
            the name of the task

        subdir : str, optional
            the subdirectory for the task.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        indir : str, optional
            the directory the task is in, to which ``name`` will be appended
        """
        self.name = name
        self.component = component
        if subdir is not None:
            self.subdir = subdir
        elif indir is not None:
            self.subdir = os.path.join(indir, name)
        else:
            self.subdir = name

        self.path = os.path.join(self.component.name, self.subdir)

        # steps will be added by calling add_step()
        self.steps = dict()
        self.step_symlinks = dict()
        self.steps_to_run = list()

        # these will be set during setup, dummy values for now
        self.config = PolarisConfigParser()
        self.config_filename = ''
        self.work_dir = ''
        self.base_work_dir = ''

        # these will be set when running the task, dummy values for now
        self.new_step_log_file = True
        self.stdout_logger = None
        self.logger = logging.getLogger('dummy')
        self.log_filename = None

    def configure(self):
        """
        Modify the configuration options for this task. Tasks should
        override this method if they want to add config options specific to
        the task, e.g. from a config file stored in the task's python
        package.  If a task overrides this method, it should assume that
        the ``<self.name>.cfg`` file in its package has already been added
        to the config options prior to calling ``configure()``.
        """
        pass

    def add_step(self, step=None, subdir=None, symlink=None,
                 run_by_default=True):
        """
        Add a step to the task and component (if not already present)

        Parameters
        ----------
        step : polaris.Step, optional
            The step to add if adding by Step object, not subdirectory

        subdir : str, optional
            The subdirectory of the step within the component if wish to add
            the step by path, and it has already been added to the component

        symlink : str, optional
            A location for a symlink to the step, relative to the test case's
            work directory. This is typically used for a shared step that lives
            outside of the test case

        run_by_default : bool, optional
            Whether to add this step to the list of steps to run when the
            ``run()`` method gets called.  If ``run_by_default=False``, users
            would need to run this step manually.
        """
        if step is None and subdir is None:
            raise ValueError('One of step or subdir must be provided.')
        if step is not None and subdir is not None:
            raise ValueError('Only one of step or subdir should be provided.')

        component = self.component

        if subdir is not None:
            if subdir not in self.component.steps:
                raise ValueError(f'Could not find {subdir} in the steps in '
                                 f'the component.  Add the step to the '
                                 f'component first, then to the task.')
            step = component.steps[subdir]

        if step.name in self.steps:
            raise ValueError(f'A step has already been added to this task '
                             f'with name {step.name}')

        # add the step to the component (if it's not already there)
        component.add_step(step)

        self.steps[step.name] = step
        step.tasks[self.subdir] = self
        if symlink:
            self.step_symlinks[step.name] = symlink
        if run_by_default:
            self.steps_to_run.append(step.name)

    def remove_step(self, step):
        """
        Remove the given step from this task and the component

        Parameters
        ----------
        step : polaris.Step
            The step to add if adding by Step object, not subdirectory
        """
        if step.name not in self.steps:
            raise ValueError(f'step {step.name} not in this task {self.name}')

        self.component.remove_step(step)
        self.steps.pop(step.name)
        if step.name in self.step_symlinks:
            self.step_symlinks.pop(step.name)
        if step.name in self.steps_to_run:
            self.steps_to_run.remove(step.name)
