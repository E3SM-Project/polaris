import subprocess
from typing import Any, Dict, List


class ParallelSystem:
    """Base class for parallel system resource management."""

    def __init__(self, config: Any):
        self.config = config

    def get_available_resources(self) -> Dict[str, Any]:
        """Return available resources for the system."""
        raise NotImplementedError

    def set_cores_per_node(self, cores_per_node: int) -> None:
        """Set the number of cores per node."""
        raise NotImplementedError

    def get_parallel_command(
        self, args: List[str], cpus_per_task: int, ntasks: int
    ) -> List[str]:
        """Get the parallel execution command."""
        raise NotImplementedError


def _get_subprocess_str(args: List[str]) -> str:
    """Run a subprocess and return its output as a string."""
    value = subprocess.check_output(args)
    value_str = value.decode('utf-8').strip('\n')
    return value_str


def _get_subprocess_int(args: List[str]) -> int:
    """Run a subprocess and return its output as an integer."""
    value_int = int(_get_subprocess_str(args))
    return value_int
