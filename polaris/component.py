import json

from polaris.io import imp_res


class Component:
    """
    The base class for housing all the tests for a given component, such as
    ocean, landice, or seaice

    Attributes
    ----------
    name : str
        the name of the component

    test_groups : dict
        A dictionary of test groups for the component with their names as keys

    cached_files : dict
        A dictionary that maps from output file names in test cases to cached
        files in the ``polaris_cache`` database for the component.  These
        file mappings are read in from ``cached_files.json`` in the component.
    """

    def __init__(self, name):
        """
        Create a new container for the test groups for a given component

        Parameters
        ----------
        name : str
            the name of the component
        """
        self.name = name

        # test groups are added with add_test_groups()
        self.test_groups = dict()

        self.cached_files = dict()
        self._read_cached_files()

    def add_test_group(self, test_group):
        """
        Add a test group to the component

        Parameters
        ----------
        test_group : polaris.TestGroup
            the test group to add
        """
        self.test_groups[test_group.name] = test_group

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
