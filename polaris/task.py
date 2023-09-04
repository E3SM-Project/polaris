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

    baseline_dir : str
        Location of the same task within the baseline work directory,
        for use in comparing variables and timers

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

    validation : dict
        A dictionary with the status of internal and baseline comparisons, used
        by the ``polaris`` framework to determine whether the task passed
        or failed internal and baseline validation.
    """

    def __init__(self, component, name, subdir=None):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            the component that this task belongs to

        name : str
            the name of the task

        subdir : str, optional
            the subdirectory for the task.  The default is ``name``
        """
        self.name = name
        self.component = component
        if subdir is not None:
            self.subdir = subdir
        else:
            self.subdir = name

        self.path = os.path.join(self.component.name, self.subdir)

        # steps will be added by calling add_step()
        self.steps = dict()
        self.steps_to_run = list()

        # these will be set during setup, dummy values for now
        self.config = PolarisConfigParser()
        self.config_filename = ''
        self.work_dir = ''
        self.base_work_dir = ''
        # may be set during setup if there is a baseline for comparison
        self.baseline_dir = None

        # these will be set when running the task, dummy values for now
        self.new_step_log_file = True
        self.stdout_logger = None
        self.logger = logging.getLogger('dummy')
        self.log_filename = None
        self.validation = None

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

    def add_step(self, step, run_by_default=True):
        """
        Add a step to the task

        Parameters
        ----------
        step : polaris.Step
            The step to add

        run_by_default : bool, optional
            Whether to add this step to the list of steps to run when the
            ``run()`` method gets called.  If ``run_by_default=False``, users
            would need to run this step manually.
        """
        self.steps[step.name] = step
        if run_by_default:
            self.steps_to_run.append(step.name)

    def check_validation(self):
        """
        Check the task's "validation" dictionary to see if validation
        failed.
        """
        validation = self.validation
        logger = self.logger
        if validation is not None:
            internal_pass = validation['internal_pass']
            baseline_pass = validation['baseline_pass']

            both_pass = True
            if internal_pass is not None and not internal_pass:
                if logger is not None:
                    logger.error('Comparison failed between files within the '
                                 'task.')
                both_pass = False

            if baseline_pass is not None and not baseline_pass:
                if logger is not None:
                    logger.error('Comparison failed between the task and '
                                 'the baseline.')
                both_pass = False

            if both_pass:
                raise ValueError('Comparison failed, see above.')
