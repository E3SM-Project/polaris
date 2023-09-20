import json

from polaris.io import imp_res


class Component:
    """
    The base class for housing all the tasks for a given component, such as
    ocean, landice, or seaice

    Attributes
    ----------
    name : str
        the name of the component

    tasks : dict
        A dictionary of tasks in the component with the subdirectories of the
        tasks in the component as keys

    steps : dict
        A dictionary of steps in the component with the subdirectories of the
        steps in the component as keys

    cached_files : dict
        A dictionary that maps from output file names in steps within tasks to
        cached files in the ``polaris_cache`` database for the component. These
        file mappings are read in from ``cached_files.json`` in the component.
    """

    def __init__(self, name):
        """
        Create a new container for the tasks for a given component

        Parameters
        ----------
        name : str
            the name of the component
        """
        self.name = name

        # tasks are added with add_task()
        self.tasks = dict()
        # steps are added with add_step()
        self.steps = dict()

        self.cached_files = dict()
        self._read_cached_files()

    def add_task(self, task):
        """
        Add a task to the component

        Parameters
        ----------
        task : polaris.Task
            The task to add
        """
        if task.subdir in self.tasks:
            raise ValueError(f'A task has already been added with path '
                             f'{task.subdir}')
        self.tasks[task.subdir] = task

    def add_step(self, step):
        """
        Add a step to the component

        Parameters
        ----------
        step : polaris.Step
            The step to add
        """
        if step.subdir in self.steps and self.steps[step.subdir] != step:
            raise ValueError(f'A different step has already been added with '
                             f'path {step.subdir}')
        self.steps[step.subdir] = step

    def remove_step(self, step):
        """
        Remove the given step from this component

        Parameters
        ----------
        step : polaris.Step
            The step to add if adding by Step object, not subdirectory
        """
        if step.subdir not in self.steps:
            raise ValueError(f'step {step.name} not in this component '
                             f'{self.name}')
        self.steps.pop(step.subdir)

    def configure(self, config):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify
        """
        pass

    def _read_cached_files(self):
        """ Read in the dictionary of cached files from cached_files.json """

        package = f'polaris.{self.name}'
        filename = 'cached_files.json'
        try:
            pkg_file = imp_res.files(package).joinpath(filename)
            with pkg_file.open('r') as data_file:
                self.cached_files = json.load(data_file)
        except FileNotFoundError:
            # no cached files for this core
            pass
