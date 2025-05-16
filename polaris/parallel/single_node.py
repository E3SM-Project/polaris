import multiprocessing

from polaris.parallel.system import ParallelSystem


class SingleNodeSystem(ParallelSystem):
    """Resource manager for single-node parallel execution."""

    def get_available_resources(self):
        config = self.config
        cores = multiprocessing.cpu_count()
        if config.has_option('parallel', 'cores_per_node'):
            cores = min(cores, config.getint('parallel', 'cores_per_node'))
        available = dict(
            cores=cores,
            nodes=1,
            cores_per_node=cores,
            mpi_allowed=True,
        )
        if config.has_option('parallel', 'gpus_per_node'):
            available['gpus_per_node'] = config.getint(
                'parallel', 'gpus_per_node'
            )
        return available

    def set_cores_per_node(self, cores_per_node):
        config = self.config
        if not config.has_option('parallel', 'cores_per_node'):
            config.set('parallel', 'cores_per_node', f'{cores_per_node}')

    def get_parallel_command(self, args, cpus_per_task, ntasks):
        command = self.config.get('parallel', 'parallel_executable').split(' ')
        command.extend(['-n', f'{ntasks}'])
        command.extend(args)
        return command
