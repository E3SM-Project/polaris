import pytest

from polaris.tasks.e3sm.init import e3sm_init
from polaris.tasks.e3sm.init.component_inputs.steps import (
    get_component_inputs_steps,
)
from polaris.tasks.mesh import mesh as mesh_component
from polaris.tasks.ocean import ocean

MESH_NAME = 'u-oi30-lr10'


@pytest.mark.parametrize(
    'step_name', ['ocean_graph_partition', 'seaice_graph_partition']
)
def test_the_partition_steps_take_their_cores_from_the_config(step_name):
    """
    And no more than a node has, since the processes share one.
    """
    step, config = _partition_step(step_name)
    config.set('component_inputs', 'partition_cpus_per_task', '8')
    step.constrain_resources(_available(cores=64))
    assert step.cpus_per_task == 8

    config.set('component_inputs', 'partition_cpus_per_task', '128')
    step.constrain_resources(_available(cores=64))
    assert step.cpus_per_task == 64


@pytest.mark.parametrize(
    'step_name', ['ocean_graph_partition', 'seaice_graph_partition']
)
def test_a_login_node_gets_only_its_login_cores(step_name):
    """
    Every partition is still built there, just a few at a time.
    """
    step, _ = _partition_step(step_name)
    step.constrain_resources(_available(cores=4, mpi_allowed=False))
    assert step.cpus_per_task == 4


def _partition_step(step_name):
    _reset_shared_components()
    steps, config = get_component_inputs_steps(mesh_name=MESH_NAME)
    step = steps[step_name]
    step.config = config
    return step, config


def _available(cores, mpi_allowed=True):
    return dict(
        cores=cores,
        nodes=1,
        cores_per_node=cores,
        gpus=0,
        gpus_per_node=0,
        memory=None,
        memory_per_node=None,
        mpi_allowed=mpi_allowed,
    )


def _reset_shared_components():
    for component in [e3sm_init, mesh_component, ocean]:
        component.tasks.clear()
        component.steps.clear()
        component.configs.clear()
