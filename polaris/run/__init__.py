import os as os
import pickle as pickle

from polaris.config import PolarisConfigParser as PolarisConfigParser


def unpickle_suite(suite_name):
    """
    Unpickle the suite

    Parameters
    ----------
    suite_name : str
        The name of the test suite

    Returns
    -------
    test_suite : dict
        The test suite
    """
    # Allow a suite name to either include or not the .pickle suffix
    if suite_name.endswith('.pickle'):
        # code below assumes no suffix, so remove it
        suite_name = suite_name[: -len('.pickle')]
    # Now open the the suite's pickle file
    if not os.path.exists(f'{suite_name}.pickle'):
        raise ValueError(
            f'The suite "{suite_name}" does not appear to have '
            f'been set up here.'
        )
    with open(f'{suite_name}.pickle', 'rb') as handle:
        test_suite = pickle.load(handle)
    return test_suite


def setup_config(base_work_dir, component_name, config_filepath):
    """
    Set up the config object from the config file

    Parameters
    ----------
    base_work_dir : str
        The base work directory where suites and tasks are being set up

    component_name : str
        The component the config belongs to


    config_filepath : str
        The path to the config file within the component's work directory

    Returns
    -------
    config : polaris.config.PolarisConfigParser
        The config object
    """
    config_filename = os.path.join(
        base_work_dir, component_name, config_filepath
    )
    config = PolarisConfigParser()
    config.add_from_file(config_filename)
    config.filepath = config_filepath
    return config


def load_dependencies(step):
    """
    Load each dependency from its pickle file to pick up changes that may have
    happened since it ran

    Parameters
    ----------
    step : polaris.step.Step
        The step object
    """
    for name, old_dependency in step.dependencies.items():
        if old_dependency.cached:
            continue

        pickle_filename = os.path.join(
            old_dependency.work_dir, 'step_after_run.pickle'
        )
        if not os.path.exists(pickle_filename):
            raise ValueError(
                f'The dependency {name} of step {step.path} was not run.'
            )

        with open(pickle_filename, 'rb') as handle:
            dependency = pickle.load(handle)
            step.dependencies[name] = dependency


def complete_step_run(step):
    """
    Write a file to indicate that the step has completed. If this step is a
    dependency of other steps, pickle the step after it has run so its
    dependencies will pick up any changes in its attributes

    Parameters
    ----------
    step : polaris.step.Step
        The step object
    """
    with open('polaris_step_complete.log', 'w') as log_file:
        log_file.write(f'{step.path} finished successfully.')
    if step.is_dependency:
        # pickle the test case and step for use at runtime
        pickle_filename = os.path.join(step.work_dir, 'step_after_run.pickle')
        with open(pickle_filename, 'wb') as handle:
            pickle.dump(step, handle, protocol=pickle.HIGHEST_PROTOCOL)
