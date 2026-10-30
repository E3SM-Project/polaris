from polaris.resolution import resolution_to_string
from polaris.tasks.landice.mismip_plus.cornford import Cornford2020
from polaris.tasks.landice.mismip_plus.experiment import ExperimentTask
from polaris.tasks.landice.mismip_plus.experiments import EXPERIMENTS
from polaris.tasks.landice.mismip_plus.forward import Forward
from polaris.tasks.landice.mismip_plus.spin_up import SpinUpTask
from polaris.tasks.landice.mismip_plus.steps import (
    get_mismip_plus_steady_state_steps,
)


def add_mismip_plus_tasks(component):
    """
    Add the MISMIP+ tasks to the landice component

    component : polaris.tasks.landice.Landice
        the landice component that the tasks will be added to
    """
    resolution = 1.0
    resdir = f'mismip_plus/{resolution_to_string(resolution)}'
    config_filename = 'mismip_plus.cfg'

    shared_steps, config = get_mismip_plus_steady_state_steps(
        resolution=resolution, component=component
    )
    spin_up = shared_steps['spin_up']

    cornford = Cornford2020(component=component, indir='mismip_plus')
    cornford.set_shared_config(config, link=config_filename)
    shared_steps['cornford2020'] = cornford

    spin_up_task = SpinUpTask(
        component=component, shared_steps=shared_steps, indir=resdir
    )
    spin_up_task.set_shared_config(config, link=config_filename)
    component.add_task(spin_up_task)

    forward_steps: dict[str, Forward] = dict()
    for experiment in EXPERIMENTS:
        previous = None
        if experiment.start_from is not None:
            previous = forward_steps[experiment.start_from]
        forward = Forward(
            component=component,
            experiment=experiment,
            indir=f'{resdir}/{experiment.subdir}',
            spin_up=spin_up,
            previous=previous,
        )
        forward.set_shared_config(config, link=config_filename)
        forward_steps[experiment.name] = forward

        experiment_task = ExperimentTask(
            component=component,
            experiment=experiment,
            shared_steps=shared_steps,
            forward=forward,
            previous=previous,
            indir=resdir,
        )
        experiment_task.set_shared_config(config, link=config_filename)
        component.add_task(experiment_task)
