import importlib.resources as imp_res
import json
import os

import xarray as xr
from mache.parallel import ParallelSystem, get_parallel_system
from mpas_tools.io import write_netcdf
from mpas_tools.logging import check_call

from polaris.config import PolarisConfigParser


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
        # configs are added with add_config()
        self.configs = dict()

        self.cached_files = dict()
        self.parallel_system: ParallelSystem | None = None
        self._read_cached_files()

    def set_parallel_system(self, config: PolarisConfigParser) -> None:
        """
        Construct and store the active parallel system for this component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            The config to use in constructing the parallel system
        """
        if config.combined is None:
            config.combine()
        assert config.combined is not None
        self.parallel_system = get_parallel_system(config.combined)

    def get_available_resources(self):
        """
        Get available resources from the active parallel system

        Returns
        -------
        available_resources : dict
            Available CPU and GPU resources and machine capabilities
        """
        if self.parallel_system is None:
            raise ValueError(
                f'Parallel system has not been set for component {self.name}'
            )

        return dict(
            cores=self.parallel_system.cores,
            nodes=self.parallel_system.nodes,
            cores_per_node=self.parallel_system.cores_per_node,
            gpus=self.parallel_system.gpus,
            gpus_per_node=self.parallel_system.gpus_per_node,
            mpi_allowed=self.parallel_system.mpi_allowed,
        )

    def run_parallel_command(
        self,
        args,
        cpus_per_task,
        ntasks,
        openmp_threads,
        logger,
        gpus_per_task=0,
    ):
        """
        Run a command using the active parallel system

        Parameters
        ----------
        args : list of str
            Command line arguments for the executable

        cpus_per_task : int
            Number of CPUs per task

        ntasks : int
            Number of parallel tasks

        openmp_threads : int
            Number of OpenMP threads

        logger : logging.Logger
            Logger to output command-line execution info

        gpus_per_task : int, optional
            Number of GPUs per task
        """
        if self.parallel_system is None:
            raise ValueError(
                f'Parallel system has not been set for component {self.name}'
            )

        env = dict(os.environ)
        env['OMP_NUM_THREADS'] = f'{openmp_threads}'
        if openmp_threads > 1:
            logger.info(f'Running with {openmp_threads} OpenMP threads')

        command_line_args = self.parallel_system.get_parallel_command(
            args=args,
            ntasks=ntasks,
            cpus_per_task=cpus_per_task,
            gpus_per_task=gpus_per_task,
        )
        check_call(command_line_args, logger, env=env)

    def add_task(self, task):
        """
        Add a task to the component

        Parameters
        ----------
        task : polaris.Task
            The task to add
        """
        if task.subdir in self.tasks:
            raise ValueError(
                f'A task has already been added with path {task.subdir}'
            )
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
            raise ValueError(
                f'A different step has already been added with '
                f'path {step.subdir}'
            )
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
            raise ValueError(
                f'step {step.name} at {step.subdir} not in the '
                f'{self.name} component'
            )
        self.steps.pop(step.subdir)

    def add_config(self, config):
        """
        Add a shared config to the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            The config to add
        """
        if config.filepath is None:
            raise ValueError(
                'The filepath attribute of a config must be set '
                'before it can be added to a component'
            )
        if (
            config.filepath in self.configs
            and self.configs[config.filepath] != config
        ):
            raise ValueError(
                f'A different shared config has already been '
                f'added at {config.filepath}'
            )
        self.configs[config.filepath] = config

    def configure(self, config, tasks):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify

        tasks : list of polaris.Task
            The tasks to be set up for this component
        """
        pass

    def get_or_create_shared_step(
        self, step_cls, subdir, config, config_filename=None, **kwargs
    ):
        """
        Get a shared step from the component if it exists, otherwise create and
        add it.

        Parameters
        ----------
        step_cls : type
            The class of the step to create if it doesn't exist

        subdir : str
            The subdirectory for the step

        config : polaris.config.PolarisConfigParser
            The shared config options for this step

        config_filename : str
            the name of the symlink to the shared configuration file in this
            step

        kwargs : dict
            Arguments to pass to the step constructor

        Returns
        -------
        step : polaris.Step
            The shared step instance
        """
        if subdir in self.steps:
            return self.steps[subdir]
        step = step_cls(component=self, subdir=subdir, **kwargs)
        step.set_shared_config(config, link=config_filename)
        self.add_step(step)
        return step

    def open_model_dataset(self, filename, **kwargs):
        """
        Open the given dataset, mapping variable and dimension names from Omega
        to MPAS-Ocean names if appropriate

        Parameters
        ----------
        filename : str
            The path for the NetCDF file to open

        kwargs
            keyword arguments passed to `xarray.open_dataset()`

        Returns
        -------
        ds : xarray.Dataset
            The dataset with variables named as expected in MPAS-Ocean
        """
        ds = xr.open_dataset(filename, **kwargs)
        return ds

    def write_model_dataset(self, ds, filename):
        """
        Write out the given dataset, mapping dimension and variable names from
        MPAS-Ocean to Omega names if appropriate

        Parameters
        ----------
        ds : xarray.Dataset
            A dataset containing MPAS-Ocean variable names

        filename : str
            The path for the NetCDF file to write
        """
        write_netcdf(ds=ds, fileName=filename)

    def _read_cached_files(self):
        """Read in the dictionary of cached files from cached_files.json"""

        package = f'polaris.{self.name.replace("/", ".")}'
        filename = 'cached_files.json'
        try:
            pkg_file = imp_res.files(package).joinpath(filename)
            with pkg_file.open('r') as data_file:
                self.cached_files = json.load(data_file)
        except FileNotFoundError:
            # no cached files for this core
            pass
