import importlib.resources as imp_res
import os as os

import numpy as np
from jinja2 import Template as Template
from mache.parallel import get_parallel_system
from mache.parallel.pbs import PbsSystem
from mache.parallel.slurm import SlurmSystem


def write_job_script(
    config,
    machine,
    work_dir,
    nodes=None,
    target_cores=None,
    min_cores=None,
    target_gpus=None,
    min_gpus=None,
    suite='',
    script_filename=None,
    run_command=None,
):
    """

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options for this test case, a combination of user configs
        and the defaults for the machine and component

    machine : {str, None}
        The name of the machine

    work_dir : str
        The work directory where the job script should be written

    nodes : int, optional
        The number of nodes for the job. If not provided, it will be
        calculated based on ``target_cores`` and ``min_cores``.

    target_cores : int, optional
        The target number of cores for the job to use if ``nodes`` not
        provided

    min_cores : int, optional
        The minimum number of cores for the job to use if ``nodes`` not
        provided

    target_gpus : int, optional
        The target number of GPUs for the job to use if ``nodes`` not
        provided

    min_gpus : int, optional
        The minimum number of GPUs for the job to use if ``nodes`` not
        provided

    suite : str, optional
        The name of the suite

    script_filename : str, optional
        The name of the job script file to write. If not provided, defaults to
        'job_script.sh' or 'job_script.{suite}.sh' if suite is specified.

    run_command : str, optional
        The command(s) to run in the job script. If not provided, defaults to
        'polaris serial {{suite}}'.
    """
    if config.combined is None:
        config.combine()
    assert config.combined is not None
    parallel_system = get_parallel_system(config.combined)

    requested_nodes = nodes

    if config.has_option('parallel', 'account'):
        account = config.get('parallel', 'account')
    else:
        account = ''

    cores_per_node = parallel_system.get_config_int('cores_per_node')
    gpus_per_node = parallel_system.get_config_int('gpus_per_node', default=0)

    use_gpu_nodes = False
    if nodes is None:
        if target_cores is None or min_cores is None:
            raise ValueError(
                'If nodes is not provided, both target_cores and min_cores '
                'must be provided.'
            )

        use_gpu_nodes = (
            gpus_per_node > 0
            and target_gpus is not None
            and min_gpus is not None
            and max(target_gpus, min_gpus) > 0
        )
        if use_gpu_nodes:
            assert target_gpus is not None
            assert min_gpus is not None
            gpus = np.sqrt(target_gpus * min_gpus)
            nodes = int(np.ceil(gpus / gpus_per_node))
            nodes = max(nodes, 1)
        else:
            if cores_per_node is None:
                raise ValueError(
                    'cores_per_node must be set when computing nodes from '
                    'CPU resources'
                )
            cores = np.sqrt(target_cores * min_cores)
            nodes = int(np.ceil(cores / cores_per_node))
            nodes = max(nodes, 1)

    if requested_nodes is None:
        requested_nodes = nodes

    min_nodes_allowed = _get_min_nodes_allowed(
        cores_per_node=cores_per_node,
        gpus_per_node=gpus_per_node,
        min_cores=min_cores,
        min_gpus=min_gpus,
    )

    # Determine parallel system type
    system = (
        config.get('parallel', 'system')
        if config.has_option('parallel', 'system')
        else 'single_node'
    )

    render_kwargs: dict[str, str] = {}

    desired_wall_time = config.get('job', 'wall_time')

    if system == 'slurm':
        (
            partition,
            qos,
            constraint,
            gpus_per_node,
            max_wallclock,
            nodes,
        ) = SlurmSystem.get_slurm_options(
            config=config.combined,
            nodes=nodes,
            min_nodes_allowed=min_nodes_allowed,
        )
        wall_time = _cap_wall_time(desired_wall_time, max_wallclock)
        template_name = 'job_script.slurm.template'
        render_kwargs.update(
            partition=partition,
            qos=qos,
            constraint=constraint,
            gpus_per_node=gpus_per_node,
            wall_time=wall_time,
        )
    elif system == 'pbs':
        (
            queue,
            constraint,
            gpus_per_node,
            max_wallclock,
            filesystems,
            nodes,
        ) = PbsSystem.get_pbs_options(
            config=config.combined,
            nodes=nodes,
            min_nodes_allowed=min_nodes_allowed,
        )
        wall_time = _cap_wall_time(desired_wall_time, max_wallclock)
        template_name = 'job_script.pbs.template'
        render_kwargs.update(
            queue=queue,
            constraint=constraint,
            gpus_per_node=gpus_per_node,
            wall_time=wall_time,
            filesystems=filesystems,
        )
    else:
        # Do not write a job script for other systems
        return

    job_name = config.get('job', 'job_name')
    if job_name == '<<<default>>>':
        job_name = f'polaris{f"_{suite}" if suite else ""}'

    if requested_nodes is not None and requested_nodes != nodes:
        print(
            f'Adjusted node count from {requested_nodes} to {nodes} for '
            f'machine {machine} based on scheduler node limits.'
        )

    template = Template(
        imp_res.files('polaris.job').joinpath(template_name).read_text()
    )

    if run_command is None:
        run_command = f'polaris serial {suite}' if suite else 'polaris serial'
        run_command = f'source load_polaris_env.sh\n{run_command}'

    render_kwargs.update(
        job_name=job_name,
        account=account,
        nodes=f'{nodes}',
        suite=suite,
        run_command=run_command,
    )

    text = template.render(**render_kwargs)
    if script_filename is None:
        script_filename = f'job_script{f".{suite}" if suite else ""}.sh'
        script_filename = os.path.join(work_dir, script_filename)
    with open(script_filename, 'w') as handle:
        handle.write(text)


def _get_min_nodes_allowed(
    cores_per_node,
    gpus_per_node,
    min_cores,
    min_gpus,
):
    """Compute the minimum feasible nodes from minimum requested resources."""
    minima = []

    if (
        min_cores is not None
        and cores_per_node is not None
        and cores_per_node > 0
    ):
        minima.append(max(int(np.ceil(min_cores / cores_per_node)), 1))

    if (
        min_gpus is not None
        and gpus_per_node is not None
        and gpus_per_node > 0
    ):
        minima.append(max(int(np.ceil(min_gpus / gpus_per_node)), 1))

    if len(minima) == 0:
        return None
    return max(minima)


def _wallclock_to_seconds(wallclock):
    """Convert HH:MM:SS wall-clock string to total seconds, or None."""
    parts = wallclock.split(':')
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None


def _cap_wall_time(desired, max_wallclock):
    """Return desired wall time, capped at max_wallclock if it is smaller.

    Defaults to desired if max_wallclock is empty or cannot be parsed.
    """
    if not max_wallclock:
        return desired
    desired_secs = _wallclock_to_seconds(desired)
    max_secs = _wallclock_to_seconds(max_wallclock)
    if desired_secs is None or max_secs is None:
        return desired
    if desired_secs <= max_secs:
        return desired
    return max_wallclock
