class TestGroup:
    """
    The base class for test groups, which are collections of tasks with
    a common purpose (e.g. global ocean, baroclinic channel, Greenland, or
    EISMINT2)

    Attributes
    ----------
    name : str
        the name of the test group

    component : polaris.Component
        the component that this test group belongs to

    tasks : dict
        A dictionary of tasks in the test group with the names of the
        tasks as keys
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

        # tasks will be added with calls to add_task()
        self.tasks = dict()

    def add_task(self, task):
        """
        Add a task to the test group

        Parameters
        ----------
        task : polaris.Task
            The task to add
        """
        self.tasks[task.subdir] = task
