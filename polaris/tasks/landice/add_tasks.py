from polaris.tasks.landice.dome import add_dome_tasks


def add_landice_tasks(component):
    """
    Add all tasks to the landice component

    component : polaris.tasks.landice.Landice
        the landice component that the tasks will be added to
    """
    # add tasks alphabetically
    add_dome_tasks(component=component)
