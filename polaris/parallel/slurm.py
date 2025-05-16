import os
import warnings

import numpy as np

from polaris.parallel.login import LoginSystem
from polaris.parallel.system import (
    ParallelSystem,
    _get_subprocess_int,
    _get_subprocess_str,
)


class SlurmSystem(ParallelSystem):
    """SLURM resource manager for parallel jobs."""

    def get_available_resources(self):
        config = self.config
        if 'SLURM_JOB_ID' not in os.environ:
            # fallback to login
            return LoginSystem(config).get_available_resources()
        job_id = os.environ['SLURM_JOB_ID']
        node = os.environ['SLURMD_NODENAME']
        args = ['sinfo', '--noheader', '--node', node, '-o', '%C']
        aiot = _get_subprocess_str(args).split('/')
        cores_per_node = int(aiot[0])
        if cores_per_node == 0:
            cores_per_node = int(aiot[3])
        args = ['sinfo', '--noheader', '--node', node, '-o', '%Z']
        slurm_threads_per_core = _get_subprocess_int(args)
        if config.has_option('parallel', 'threads_per_core'):
            threads_per_core = config.getint('parallel', 'threads_per_core')
            cores_per_node = (
                cores_per_node * threads_per_core
            ) // slurm_threads_per_core
        args = ['squeue', '--noheader', '-j', job_id, '-o', '%D']
        nodes = _get_subprocess_int(args)
        cores = cores_per_node * nodes
        available = dict(
            cores=cores,
            nodes=nodes,
            cores_per_node=cores_per_node,
            mpi_allowed=True,
        )
        if config.has_option('parallel', 'gpus_per_node'):
            available['gpus_per_node'] = config.getint(
                'parallel', 'gpus_per_node'
            )
        return available

    def set_cores_per_node(self, cores_per_node):
        config = self.config
        old_cores_per_node = config.getint('parallel', 'cores_per_node')
        config.set('parallel', 'cores_per_node', f'{cores_per_node}')
        if old_cores_per_node != cores_per_node:
            warnings.warn(
                f'Slurm found {cores_per_node} cpus per node but '
                f'config from mache was {old_cores_per_node}',
                stacklevel=2,
            )

    def get_parallel_command(self, args, cpus_per_task, ntasks):
        config = self.config
        command = config.get('parallel', 'parallel_executable').split(' ')
        cores = ntasks * cpus_per_task
        cores_per_node = config.getint('parallel', 'cores_per_node')
        nodes = int(np.ceil(cores / cores_per_node))
        command.extend(
            ['-c', f'{cpus_per_task}', '-N', f'{nodes}', '-n', f'{ntasks}']
        )
        command.extend(args)
        return command
