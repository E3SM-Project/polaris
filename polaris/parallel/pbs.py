import os
import warnings

from polaris.parallel.login import LoginSystem
from polaris.parallel.system import (
    ParallelSystem,
)


class PbsSystem(ParallelSystem):
    """PBS resource manager for parallel jobs."""

    def get_available_resources(self):
        config = self.config
        if 'PBS_JOBID' not in os.environ:
            # fallback to login
            return LoginSystem(config).get_available_resources()
        nodefile = os.environ.get('PBS_NODEFILE')
        if nodefile and os.path.exists(nodefile):
            with open(nodefile) as f:
                nodes_list = [line.strip() for line in f if line.strip()]
            nodes = len(set(nodes_list))
            # Count how many times the first node appears (cores per node)
            first_node = nodes_list[0]
            cores_per_node = nodes_list.count(first_node)
        else:
            # Fallback to config if PBS_NODEFILE is not available
            nodes = config.getint('parallel', 'nodes', fallback=1)
            cores_per_node = config.getint(
                'parallel', 'cores_per_node', fallback=1
            )
        cores = nodes * cores_per_node
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
                f'PBS found {cores_per_node} cpus per node but '
                f'config from mache was {old_cores_per_node}',
                stacklevel=2,
            )

    def get_parallel_command(self, args, cpus_per_task, ntasks):
        config = self.config
        command = config.get('parallel', 'parallel_executable').split(' ')
        # PBS mpiexec/mpirun may not use -N for nodes, but -n for tasks and
        # -c for cpus-per-task are common
        command.extend(['-n', f'{ntasks}', '-c', f'{cpus_per_task}'])
        command.extend(args)
        return command
