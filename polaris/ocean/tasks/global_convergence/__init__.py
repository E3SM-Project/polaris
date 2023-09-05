from polaris.ocean.tasks.global_convergence.cosine_bell import CosineBell


def add_cosine_bell_tasks(component):
    """
    Add tasks that define variants of the cosine bell test case

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """

    for icosahedral in [False, True]:
        for include_viz in [False, True]:
            component.add_task(CosineBell(component=component,
                                          icosahedral=icosahedral,
                                          include_viz=include_viz))
