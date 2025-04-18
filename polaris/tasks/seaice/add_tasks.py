from polaris.tasks.seaice.single_column import add_single_column_tasks


def add_seaice_tasks(component):
    """
    Add all tasks to the seaice component

    component : polaris.Component
        the seaice component that the tasks will be added to
    """
    # add tasks alphabetically
    add_single_column_tasks(component=component)
