import os
import re
import subprocess
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

        # First, try to get nodes and cores_per_node from qstat
        nodes, cores_per_node = self._get_resources_from_qstat()

        if nodes is None or cores_per_node is None:
            # Final fallback: use config values
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
        section = config['parallel']
        command = section.get('parallel_executable').split(' ')
        # PBS mpiexec/mpirun options are launcher's responsibility, so the
        # flag used for CPUs per task is configurable per machine
        if section.has_option('cpus_per_task_flag'):
            cpus_per_task_flag = section.get('cpus_per_task_flag')
        else:
            cpus_per_task_flag = '-c'
        command.extend(
            ['-n', f'{ntasks}', cpus_per_task_flag, f'{cpus_per_task}']
        )
        command.extend(args)
        return command

    def _get_resources_from_qstat(self):
        """Try to determine nodes and cores_per_node from qstat output."""

        jobid = os.environ.get('PBS_JOBID')
        if not jobid:
            return None, None

        try:
            # text=True is available in Python 3.7+
            output = subprocess.check_output(['qstat', '-f', jobid], text=True)
        except FileNotFoundError:  # qstat executable not found
            return None, None
        except subprocess.CalledProcessError:  # qstat returned non-zero
            return None, None

        # Try to infer nodes and cores_per_node from various Resource_List
        # fields. Different PBS installations format these differently.

        # Case 1: Aurora style (current ALCF Aurora machine): separate
        # ncpus and nodect, and select
        #   Resource_List.ncpus = total_cores_for_job
        #   Resource_List.nodect = number_of_nodes
        #   Resource_List.select = number_of_nodes (or chunks)
        ncpus_match = re.search(r'Resource_List\.ncpus\s*=\s*(\d+)', output)
        nodect_match = re.search(r'Resource_List\.nodect\s*=\s*(\d+)', output)
        simple_select_match = re.search(
            r'Resource_List\.select\s*=\s*(\d+)', output
        )

        total_cores = int(ncpus_match.group(1)) if ncpus_match else None
        nodect = int(nodect_match.group(1)) if nodect_match else None
        simple_select = (
            int(simple_select_match.group(1)) if simple_select_match else None
        )

        if total_cores is not None and nodect is not None and nodect != 0:
            nodes = nodect
            cores_per_node = total_cores // nodect
            return nodes, cores_per_node

        if (
            total_cores is not None
            and simple_select is not None
            and simple_select != 0
        ):
            nodes = simple_select
            cores_per_node = total_cores // simple_select
            return nodes, cores_per_node

        # Case 2: PBS Pro style "select=N:ncpus=M" on a single line
        select_match = re.search(
            r'Resource_List\.select\s*=\s*(\d+)[^\n]*?:ncpus=(\d+)',
            output,
        )
        if select_match:
            nodes = int(select_match.group(1))
            cores_per_node = int(select_match.group(2))
            return nodes, cores_per_node

        # Case 3: older PBS/Torque style: "nodes=N:ppn=M"
        nodes_match = re.search(
            r'Resource_List\.nodes\s*=\s*(\d+)[^\n]*?:ppn=(\d+)',
            output,
        )
        if nodes_match:
            nodes = int(nodes_match.group(1))
            cores_per_node = int(nodes_match.group(2))
            return nodes, cores_per_node
        return None, None
