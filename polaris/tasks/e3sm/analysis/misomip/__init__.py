from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.analysis.misomip.comparisons import (
    MisomipExperimentsTask as MisomipExperimentsTask,
)
from polaris.tasks.e3sm.analysis.misomip.comparisons import (
    MisomipResolutionsTask as MisomipResolutionsTask,
)
from polaris.tasks.e3sm.analysis.misomip.runs import EXPERIMENTS, MESH_NAMES
from polaris.tasks.e3sm.analysis.misomip.task import (
    MisomipAnalysisTask as MisomipAnalysisTask,
)


def add_misomip_analysis_tasks(component):
    """
    Add the tasks that analyze the MISOMIP experiments run in E3SM

    Parameters
    ----------
    component : polaris.Component
        The e3sm/analysis component
    """
    filepath = f'{component.name}/misomip_analysis.cfg'
    config = component.get_or_create_shared_config(
        filepath, create=lambda: _make_config(filepath)
    )
    for mesh_name in MESH_NAMES:
        for experiment in EXPERIMENTS:
            component.add_task(
                MisomipAnalysisTask(
                    component=component,
                    config=config,
                    mesh_name=mesh_name,
                    experiment=experiment,
                )
            )
        component.add_task(
            MisomipExperimentsTask(
                component=component, config=config, mesh_name=mesh_name
            )
        )
    for experiment in EXPERIMENTS:
        component.add_task(
            MisomipResolutionsTask(
                component=component, config=config, experiment=experiment
            )
        )


def _make_config(filepath):
    """Build the config shared by the MISOMIP analysis tasks"""
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.e3sm.analysis.misomip', 'misomip_analysis.cfg'
    )
    return config
