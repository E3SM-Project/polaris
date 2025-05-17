import os

from mpas_tools.logging import check_call

from polaris.parallel.login import LoginSystem
from polaris.parallel.pbs import PbsSystem
from polaris.parallel.single_node import SingleNodeSystem
from polaris.parallel.slurm import SlurmSystem


def _get_system(config):
    system = config.get('parallel', 'system')
    if system == 'slurm':
        if 'SLURM_JOB_ID' not in os.environ:
            system = 'login'
    if system == 'slurm':
        return SlurmSystem(config)
    elif system == 'pbs':
        return PbsSystem(config)
    elif system == 'single_node':
        return SingleNodeSystem(config)
    elif system == 'login':
        return LoginSystem(config)
    else:
        raise ValueError(f'Unexpected parallel system: {system}')


def get_available_parallel_resources(config):
    return _get_system(config).get_available_resources()


def set_cores_per_node(config, cores_per_node):
    _get_system(config).set_cores_per_node(cores_per_node)


def run_command(args, cpus_per_task, ntasks, openmp_threads, config, logger):
    env = dict(os.environ)
    env['OMP_NUM_THREADS'] = f'{openmp_threads}'
    if openmp_threads > 1:
        logger.info(f'Running with {openmp_threads} OpenMP threads')
    command_line_args = get_parallel_command(
        args, cpus_per_task, ntasks, config
    )
    check_call(command_line_args, logger, env=env)


def get_parallel_command(args, cpus_per_task, ntasks, config):
    return _get_system(config).get_parallel_command(
        args, cpus_per_task, ntasks
    )
