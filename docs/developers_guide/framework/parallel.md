(dev-parallel)=

# Parallel

The `polaris.parallel` module provides a unified interface for querying and managing parallel resources across different computing environments. It abstracts the details of various parallel systems, allowing tasks and steps to request resources and construct parallel execution commands in a system-agnostic way.

## Public API

The following functions are available in `polaris.parallel`:

- **get_available_parallel_resources(config):**
  Returns a dictionary describing the available parallel resources (cores, nodes, cores per node, etc.) for the current environment, as determined by the selected parallel system.

- **set_cores_per_node(config, cores_per_node):**
  Sets the number of cores per node in the configuration, updating any relevant settings for the current parallel system.

- **get_parallel_command(args, cpus_per_task, ntasks, config):**
  Returns the command (as a list of strings) to launch a parallel job with the specified arguments, CPUs per task, and number of tasks, using the appropriate parallel launcher for the current system.

- **run_command(args, cpus_per_task, ntasks, openmp_threads, config, logger):**
  Runs a parallel command with the specified resources and OpenMP thread count, using the appropriate launcher and logging output.

See also the API documentation for:
- {py:func}`polaris.parallel.get_available_parallel_resources`
- {py:func}`polaris.parallel.set_cores_per_node`
- {py:func}`polaris.parallel.get_parallel_command`
- {py:func}`polaris.parallel.run_command`

## Supported Parallel Systems

The module currently supports four parallel systems, each with its own resource manager class:

- **single_node:**
  For running on a single node, using all available local CPU cores.
  Managed by {py:class}`polaris.parallel.SingleNodeSystem`.

- **login:**
  For running on a login node (no parallel execution, typically for setup or analysis).
  Managed by {py:class}`polaris.parallel.LoginSystem`.

- **slurm:**
  For running under the SLURM workload manager, using environment variables and SLURM commands to determine resources.
  Managed by {py:class}`polaris.parallel.SlurmSystem`.

- **pbs:**
  For running under the PBS workload manager, using environment variables and PBS node files to determine resources.
  Managed by {py:class}`polaris.parallel.PbsSystem`.

The appropriate system is selected automatically based on the configuration and environment variables.

## Adding Support for a New Parallel System

To add a new parallel system:

1. **Create a new system class:**
   Subclass `ParallelSystem` in `polaris/parallel/`, implementing the following methods:
   - `get_available_resources(self)`
   - `set_cores_per_node(self, cores_per_node)`
   - `get_parallel_command(self, args, cpus_per_task, ntasks)`

2. **Handle environment detection:**
   In your new system class, use environment variables or other mechanisms to detect when your system should be active.

3. **Register the new system:**
   Update the logic in `polaris/parallel/__init__.py` (the `_get_system` function) to recognize your new system based on the config or environment, and return an instance of your new class.

4. **(Optional) Add documentation:**
   Update this documentation page to describe your new system and its usage.

By following this structure, you can extend Polaris to support additional parallel resource managers or custom environments as needed.
