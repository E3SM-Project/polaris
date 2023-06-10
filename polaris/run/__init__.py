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
