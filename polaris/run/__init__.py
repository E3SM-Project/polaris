import os as os
import pickle as pickle

from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.step import Step

# what complete_step_run() writes in a step's work directory once the step
# has finished successfully, and what anything asking "has this already
# run?" looks for
STEP_COMPLETE_LOG = 'polaris_step_complete.log'

# a step's references to the rest of the suite, which load_dependencies()
# leaves pointing at the suite being run rather than at the copies a pickle
# holds
_SUITE_REFERENCES = ('component', 'tasks', 'dependencies')


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


def setup_config(base_work_dir, config_filepath):
    """
    Set up the config object from the config file

    Parameters
    ----------
    base_work_dir : str
        The base work directory where suites and tasks are being set up

    config_filepath : str
        The path to the config file within the component's work directory

    Returns
    -------
    config : polaris.config.PolarisConfigParser
        The config object
    """
    config_filename = os.path.join(base_work_dir, config_filepath)
    config = PolarisConfigParser()
    config.add_from_file(config_filename)
    config.filepath = config_filepath
    return config


def load_dependencies(step):
    """
    Load each dependency from its pickle file to pick up changes that may have
    happened since it ran

    Each dependency is updated in place rather than replaced, so a step that
    also refers to it directly sees the same changes.  Its references to
    other steps, its tasks and its component are left pointing into the
    suite being run.

    Parameters
    ----------
    step : polaris.step.Step
        The step object

    Returns
    -------
    pickle_filenames : dict
        The pickle file each dependency was loaded from, with the names of
        the dependencies as keys
    """
    pickle_filenames = dict()
    for name, dependency in step.dependencies.items():
        if dependency.cached:
            continue

        pickle_filename = os.path.join(
            dependency.work_dir, 'step_after_run.pickle'
        )
        if not os.path.exists(pickle_filename):
            raise ValueError(
                f'The dependency {name} of step {step.path} was not run.'
            )

        with open(pickle_filename, 'rb') as handle:
            unpickled = pickle.load(handle)
        _update_from_pickle(dependency, unpickled)
        pickle_filenames[name] = pickle_filename
    return pickle_filenames


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
    with open(STEP_COMPLETE_LOG, 'w') as log_file:
        log_file.write(f'{step.path} finished successfully.')
    if step.is_dependency:
        # pickle the test case and step for use at runtime
        pickle_filename = os.path.join(step.work_dir, 'step_after_run.pickle')
        with open(pickle_filename, 'wb') as handle:
            pickle.dump(step, handle, protocol=pickle.HIGHEST_PROTOCOL)


def _update_from_pickle(step, unpickled):
    """
    Give a step the state of its unpickled copy, except for the copy's
    references to the rest of the suite.

    A step's pickle holds copies of every step it refers to.  Replacing a
    dependency with its unpickled copy grafted those copies onto the suite,
    and a step that refers to its dependency both through ``dependencies``
    and directly, as many do, then pickled the copy and the original alike,
    so pickles doubled with each step along a chain of dependencies.
    """
    state = dict()
    for key, value in unpickled.__dict__.items():
        if key in _SUITE_REFERENCES:
            continue
        if isinstance(value, Step) and key in step.__dict__:
            continue
        state[key] = value
    step.__dict__.update(state)
