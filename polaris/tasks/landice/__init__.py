import os

from polaris import Component
from polaris.build.mali import (
    build_mali,
    environment_has_albany,
    get_mali_build_albany,
)
from polaris.landice.model import MaliModelStep


class Landice(Component):
    """
    The collection of all tasks for MALI
    """

    def __init__(self):
        """
        Construct the collection of MALI tasks
        """
        super().__init__(name='landice')

    def configure(self, config, steps):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            the config options for this component, to modify

        steps : list of polaris.Step
            The steps this component owns among those being set up.  These may
            belong to tasks in another component.
        """
        model = config.get('landice', 'model')

        configs = {'mali': 'mali.cfg'}

        if model not in configs:
            raise ValueError(f'Unknown landice model {model}')

        config.add_from_package('polaris.landice', configs[model])

        model_steps = [
            step for step in steps if isinstance(step, MaliModelStep)
        ]
        if not model_steps:
            # no MALI runs, so no build is needed
            return

        component_path = config.get('paths', 'component_path')
        if not _detect_mali_build(component_path):
            # looks like we need to build the model
            build = config.getboolean('build', 'build')
            if not build:
                print(
                    f'MALI not found in {component_path}, setting build '
                    f'option to True'
                )
                config.set('build', 'build', 'True', user=True)

        albany_steps = [step.path for step in model_steps if step.needs_albany]
        if albany_steps:
            _check_albany(config, component_path, albany_steps)

    def build_model(self, config, machine):
        """
        Build MALI

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            the config options for this component

        machine : str
            The name of the machine to build the model on
        """
        section = config['build']
        compiler = section.get('compiler')
        mpilib = section.get('mpi')
        key = f'{compiler}_{mpilib}_target'
        if not section.has_option(key):
            raise ValueError(
                f'The build target {key} is not defined in the [build] '
                f'section of the config file for machine {machine}.'
            )

        build_dir = config.get('paths', 'component_path')
        log_filename = os.path.join(build_dir, 'build_mali.log')
        build_mali(
            branch=section.get('branch'),
            build_dir=build_dir,
            clean=section.getboolean('clean'),
            quiet=section.getboolean('quiet'),
            debug=section.getboolean('debug'),
            make_flags=section.get('cmake_flags'),
            make_target=section.get(key),
            albany=get_build_albany(config),
            log_filename=log_filename,
        )


def get_build_albany(config):
    """
    Whether a MALI build should have Albany, from the ``albany`` option in
    the ``[build]`` config section

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        the config options for the landice component

    Returns
    -------
    albany : bool
        Whether to build MALI with Albany
    """
    albany = config.get('build', 'albany')
    if albany == 'detect':
        return environment_has_albany()
    return config.getboolean('build', 'albany')


def _detect_mali_build(path):
    """
    Detect if MALI has been built in the given path
    """
    required_files = [
        'default_inputs/namelist.landice',
        'default_inputs/streams.landice',
        'src/Registry_processed.xml',
        'landice_model',
    ]
    path = os.path.abspath(path)
    return all(
        os.path.exists(os.path.join(path, required_file))
        for required_file in required_files
    )


def _check_albany(config, component_path, albany_steps):
    """
    Make sure MALI will have Albany for the steps that need it
    """
    step_list = '\n  '.join(albany_steps)
    if config.getboolean('build', 'build'):
        if not get_build_albany(config):
            raise ValueError(
                f'These steps need MALI built with Albany:\n  {step_list}\n'
                f'but the build will not have it.  Deploy the Polaris '
                f'environment with "./deploy.py --with-albany", and do not '
                f'set "albany = False" in the [build] config section.'
            )
    elif get_mali_build_albany(component_path) is False:
        raise ValueError(
            f'These steps need MALI built with Albany:\n  {step_list}\n'
            f'but the build in {component_path} does not have it.'
        )


# create a single module-level instance available to other components
landice = Landice()
