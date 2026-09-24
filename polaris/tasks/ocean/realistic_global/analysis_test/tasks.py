from polaris.tasks.ocean.realistic_global.analysis_test.task import (
    RealisticGlobalAnalysisTest,
)


def add_realistic_global_analysis_test_tasks(component):
    """
    Add the tasks that run a short Omega simulation writing what the ocean
    analysis reads

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the tasks will be added to
    """
    component.add_task(
        RealisticGlobalAnalysisTest(component=component, mesh_name='QU.240km')
    )
