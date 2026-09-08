from configparser import ConfigParser

import pytest
from mache.parallel import ParallelSystem

from polaris import Component, ModelStep

# resources taken from mache's frontier.cfg: the [parallel] section describes
# the CPU-only compilers while [parallel.craygnu_mphipcc] describes a
# GPU-enabled compiler with one MPI task per GPU
FRONTIER_CORES_PER_NODE = 56
FRONTIER_GPUS_PER_NODE = 8


def _make_parallel_system(nodes, gpu_compiler):
    """
    Build a parallel system with Frontier's resources, as
    ``SlurmSystem.__init__()`` would if we were in a job on that machine
    """
    config = ConfigParser()
    config.add_section('parallel')
    config.set('parallel', 'system', 'slurm')
    config.set('parallel', 'cores_per_node', f'{FRONTIER_CORES_PER_NODE}')
    config.set(
        'parallel', 'max_mpi_tasks_per_node', f'{FRONTIER_CORES_PER_NODE}'
    )
    config.set('parallel', 'gpus_per_node', '0')

    config.add_section('parallel.craygnu_mphipcc')
    config.set(
        'parallel.craygnu_mphipcc',
        'max_mpi_tasks_per_node',
        f'{FRONTIER_GPUS_PER_NODE}',
    )
    config.set(
        'parallel.craygnu_mphipcc',
        'gpus_per_node',
        f'{FRONTIER_GPUS_PER_NODE}',
    )

    config.add_section('build')
    compiler = 'craygnu-mphipcc' if gpu_compiler else 'craygnu'
    config.set('build', 'compiler', compiler)

    parallel_system = ParallelSystem(config)
    parallel_system.nodes = nodes
    parallel_system.cores_per_node = parallel_system.get_config_int(
        'cores_per_node'
    )
    parallel_system.cores = parallel_system.cores_per_node * nodes
    parallel_system.gpus_per_node = parallel_system.get_config_int(
        'gpus_per_node'
    )
    parallel_system.gpus = parallel_system.gpus_per_node * nodes
    parallel_system.mpi_allowed = True
    return parallel_system


def _make_step(
    nodes,
    ntasks,
    cpus_per_task=1,
    gpus_per_task=0,
    gpu_compiler=False,
):
    component = Component(name='ocean')
    component.parallel_system = _make_parallel_system(
        nodes=nodes, gpu_compiler=gpu_compiler
    )
    # ModelStep uses openmp_threads as cpus_per_task, and states its GPU
    # need as a total for the step rather than a count per task
    return ModelStep(
        component=component,
        name='forward',
        ntasks=ntasks,
        min_tasks=ntasks,
        openmp_threads=cpus_per_task,
        gpus=gpus_per_task * ntasks,
        min_gpus=gpus_per_task * ntasks,
    )


def _get_io_options(step):
    """Get the options passed to add_model_config_options"""
    assert len(step.model_config_data) == 1
    return step.model_config_data[0]['options']


def test_gpu_one_io_task_per_node():
    """
    On 19 GPU nodes with one MPI task per GPU, there should be one IO task
    per node and a stride of one node's worth of tasks (the GPUs per node,
    not the cores per node)
    """
    step = _make_step(
        nodes=19,
        ntasks=19 * FRONTIER_GPUS_PER_NODE,
        gpus_per_task=1,
        gpu_compiler=True,
    )
    step.update_io_tasks_config()
    assert _get_io_options(step) == {
        'config_pio_num_iotasks': 19,
        'config_pio_stride': FRONTIER_GPUS_PER_NODE,
    }


@pytest.mark.parametrize('nodes', [1, 2, 5, 19, 64])
def test_gpu_io_tasks_fit_within_ntasks(nodes):
    """
    The IO tasks must fit within the tasks the GPU step is running on, with
    at most one IO task per node
    """
    ntasks = nodes * FRONTIER_GPUS_PER_NODE
    step = _make_step(
        nodes=nodes, ntasks=ntasks, gpus_per_task=1, gpu_compiler=True
    )
    step.update_io_tasks_config()
    options = _get_io_options(step)
    num_iotasks = options['config_pio_num_iotasks']
    stride = options['config_pio_stride']
    assert num_iotasks == nodes
    assert stride <= FRONTIER_GPUS_PER_NODE
    # the last IO task must be a rank that actually exists
    assert (num_iotasks - 1) * stride < ntasks


def test_gpu_partially_filled_last_node():
    """
    When the tasks don't fill the last node, the IO tasks must still be valid
    ranks
    """
    ntasks = 150
    step = _make_step(
        nodes=19, ntasks=ntasks, gpus_per_task=1, gpu_compiler=True
    )
    step.update_io_tasks_config()
    options = _get_io_options(step)
    num_iotasks = options['config_pio_num_iotasks']
    stride = options['config_pio_stride']
    assert num_iotasks == 19
    assert (num_iotasks - 1) * stride < ntasks


def test_gpu_single_task():
    step = _make_step(nodes=1, ntasks=1, gpus_per_task=1, gpu_compiler=True)
    step.update_io_tasks_config()
    assert _get_io_options(step) == {
        'config_pio_num_iotasks': 1,
        'config_pio_stride': 1,
    }


def test_gpu_two_gpus_per_task():
    """
    With 2 GPUs per task, only 4 tasks fit on each of Frontier's 8-GPU nodes
    """
    step = _make_step(nodes=3, ntasks=12, gpus_per_task=2, gpu_compiler=True)
    step.update_io_tasks_config()
    assert _get_io_options(step) == {
        'config_pio_num_iotasks': 3,
        'config_pio_stride': 4,
    }


def test_gpu_without_gpus_available_raises():
    step = _make_step(nodes=2, ntasks=8, gpus_per_task=1, gpu_compiler=False)
    with pytest.raises(ValueError, match='gpus_per_node is not set'):
        step.update_io_tasks_config()


@pytest.mark.parametrize(
    'nodes,ntasks,cpus_per_task,expected_num_iotasks,expected_stride',
    [
        # one full CPU node
        (1, FRONTIER_CORES_PER_NODE, 1, 1, FRONTIER_CORES_PER_NODE),
        # two full CPU nodes
        (2, 2 * FRONTIER_CORES_PER_NODE, 1, 2, FRONTIER_CORES_PER_NODE),
        # fewer tasks than a full node
        (1, 4, 1, 1, 4),
        # 4 CPUs per task means only 14 tasks fit on each 56-core node
        (2, 28, 4, 2, 14),
    ],
)
def test_cpu_io_tasks(
    nodes, ntasks, cpus_per_task, expected_num_iotasks, expected_stride
):
    """CPU-only behavior must be unchanged by the GPU-aware task placement"""
    step = _make_step(
        nodes=nodes,
        ntasks=ntasks,
        cpus_per_task=cpus_per_task,
        gpu_compiler=False,
    )
    step.update_io_tasks_config()
    assert _get_io_options(step) == {
        'config_pio_num_iotasks': expected_num_iotasks,
        'config_pio_stride': expected_stride,
    }


def test_no_parallel_system_raises():
    component = Component(name='ocean')
    step = ModelStep(
        component=component, name='forward', ntasks=1, openmp_threads=1
    )
    with pytest.raises(ValueError, match='Parallel system has not been set'):
        step.update_io_tasks_config()
