from polaris.tasks.e3sm.init.misomip.steps import (
    MESH_PAIRS as MESH_PAIRS,
)
from polaris.tasks.e3sm.init.misomip.steps import (
    get_misomip_experiment_steps as get_misomip_experiment_steps,
)
from polaris.tasks.e3sm.init.misomip.steps import (
    get_misomip_mesh_steps as get_misomip_mesh_steps,
)
from polaris.tasks.e3sm.init.misomip.task import MisomipTask as MisomipTask

#: The ISOMIP+ and MISOMIP1 experiments E3SM runs
EXPERIMENTS = [
    'ocean0',
    'ocean1',
    'ocean2',
    'ocean3',
    'ocean4',
    'iceocean1r',
    'iceocean1ra',
]


def add_misomip_tasks(component):
    """
    Add a task for each MISOMIP experiment on each pair of meshes

    Parameters
    ----------
    component : polaris.Component
        The e3sm/init component that the tasks will be added to
    """
    for mesh_name in MESH_PAIRS:
        for experiment in EXPERIMENTS:
            component.add_task(
                MisomipTask(
                    component=component,
                    mesh_name=mesh_name,
                    experiment=experiment,
                )
            )
