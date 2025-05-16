import multiprocessing

from polaris.parallel.system import ParallelSystem


class LoginSystem(ParallelSystem):
    """Resource manager for login nodes (no parallel execution)."""

    def get_available_resources(self):
        config = self.config
        cores = min(
            multiprocessing.cpu_count(),
            config.getint('parallel', 'login_cores'),
        )
        available = dict(
            cores=cores,
            nodes=1,
            cores_per_node=cores,
            mpi_allowed=False,
        )
        if config.has_option('parallel', 'gpus_per_node'):
            available['gpus_per_node'] = config.getint(
                'parallel', 'gpus_per_node'
            )
        return available

    def set_cores_per_node(self, cores_per_node):
        # No-op for login system
        pass

    def get_parallel_command(self, args, cpus_per_task, ntasks):
        # Not supported for login system
        raise ValueError('Parallel execution is not allowed on login nodes.')
