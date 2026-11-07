from polaris.tasks.e3sm.analysis.misomip import add_misomip_analysis_tasks


def add_e3sm_analysis_tasks(component):
    """
    Add all tasks to the e3sm/analysis component

    component : polaris.Component
        the e3sm/analysis component that the tasks will be added to
    """
    add_misomip_analysis_tasks(component=component)
