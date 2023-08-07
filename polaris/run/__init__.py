import os
import pickle

from polaris.config import PolarisConfigParser


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
        suite_name = suite_name[:-len('.pickle')]
    # Now open the the suite's pickle file
    if not os.path.exists(f'{suite_name}.pickle'):
        raise ValueError(f'The suite "{suite_name}" does not appear to have '
                         f'been set up here.')
    with open(f'{suite_name}.pickle', 'rb') as handle:
        test_suite = pickle.load(handle)
    return test_suite


def setup_config(config_filename):
    """
    Set up the config object from the config file

    Parameters
    ----------
    config_filename : str
        The config filename

    Returns
    -------
    config : polaris.config.PolarisConfigParser
        The config object
    """
    config = PolarisConfigParser()
    config.add_from_file(config_filename)
    return config


def load_dependencies(test_case, step):
    """
    Load each dependency from its pickle file to pick up changes that may have
    happened since it ran

    Parameters
    ----------
    test_case : polaris.testcase.TestCase
        The test case object

    step : polaris.step.Step
        The step object
    """
    for name, old_dependency in step.dependencies.items():
        if old_dependency.cached:
            continue

        pickle_filename = os.path.join(old_dependency.work_dir,
                                       'step_after_run.pickle')
        if not os.path.exists(pickle_filename):
            raise ValueError(f'The dependency {name} of '
                             f'{test_case.path} step {step.name} was '
                             f'not run.')

        with open(pickle_filename, 'rb') as handle:
            _, dependency = pickle.load(handle)
            step.dependencies[name] = dependency


def pickle_step_after_run(test_case, step):
    """
    Pickle a step after it has run so its dependencies will pick up the
    changes

    Parameters
    ----------
    test_case : polaris.testcase.TestCase
        The test case object

    step : polaris.step.Step
        The step object
    """
    if step.is_dependency:
        # pickle the test case and step for use at runtime
        pickle_filename = os.path.join(step.work_dir, 'step_after_run.pickle')
        with open(pickle_filename, 'wb') as handle:
            pickle.dump((test_case, step), handle,
                        protocol=pickle.HIGHEST_PROTOCOL)
