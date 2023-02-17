class TestGroup:
    """
    The base class for test groups, which are collections of test cases with
    a common purpose (e.g. global ocean, baroclinic channel, Greenland, or
    EISMINT2)

    Attributes
    ----------
    name : str
        the name of the test group

    component : polaris.Component
        the component that this test group belongs to

    test_cases : dict
        A dictionary of test cases in the test group with the names of the
        test cases as keys
    """

    def __init__(self, component, name):
        """
        Create a new test group

        Parameters
        ----------
        component : polaris.Component
            the component that this test group belongs to

        name : str
            the name of the test group
        """
        self.name = name
        self.component = component

        # test cases will be added with calls to add_test_case()
        self.test_cases = dict()

    def add_test_case(self, test_case):
        """
        Add a test case to the test group

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case to add
        """
        self.test_cases[test_case.subdir] = test_case
