from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.realistic_global.analysis_members import (
    AnalysisMembers as AnalysisMembers,
)


def add_realistic_global_tasks(component):
    """
    Add tasks for global-ocean preprocessing and initialization.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component to which the tasks will be added.
    """
    #subdir=f'{component.name}/spherical'
    subdir='spherical'
    config_filename ='analysis_members.cfg'
    for mesh in ['qu/240km']:
        filepath=f'{subdir}/{mesh}/realistic_global/analysis_members/{config_filename}'
        config = PolarisConfigParser(filepath=filepath)
        component.add_task(AnalysisMembers(
            component=component,
            subdir=subdir,
            mesh_name=mesh,
            config=config,
            config_filename=config_filename))

