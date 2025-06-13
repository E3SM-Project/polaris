import importlib.resources as imp_res
import os as os

import numpy as np
from jinja2 import Template as Template


def write_job_script(
    config,
    machine,
    work_dir,
    nodes=None,
    target_cores=None,
    min_cores=None,
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

    suite : str, optional
        The name of the suite

    script_filename : str, optional
        The name of the job script file to write. If not provided, defaults to
        'job_script.sh' or 'job_script.{suite}.sh' if suite is specified.

    run_command : str, optional
        The command(s) to run in the job script. If not provided, defaults to
        'polaris serial {{suite}}'.
    """

    if config.has_option('parallel', 'account'):
        account = config.get('parallel', 'account')
    else:
        account = ''

    if nodes is None:
        if target_cores is None or min_cores is None:
            raise ValueError(
                'If nodes is not provided, both target_cores and min_cores '
                'must be provided.'
            )
        cores_per_node = config.getint('parallel', 'cores_per_node')
        cores = np.sqrt(target_cores * min_cores)
        nodes = int(np.ceil(cores / cores_per_node))

    # Determine parallel system type
    system = (
        config.get('parallel', 'system')
        if config.has_option('parallel', 'system')
        else 'single_node'
    )

    render_kwargs: dict[str, str] = {}

    if system == 'slurm':
        partition, qos, constraint, gpus_per_node, wall_time = (
            get_slurm_options(config, machine, nodes)
        )
        template_name = 'job_script.slurm.template'
        render_kwargs.update(
            partition=partition,
            qos=qos,
            constraint=constraint,
            gpus_per_node=gpus_per_node,
            wall_time=wall_time,
        )
    elif system == 'pbs':
        queue, constraint, gpus_per_node, wall_time, filesystems = (
            get_pbs_options(config, machine, nodes)
        )
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


def get_slurm_options(config, machine, nodes):
    """
    Get Slurm options for job submission.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options for this test case, a combination of user configs
        and the defaults for the machine and component.

    machine : str
        The name of the machine.

    nodes : int
        The number of nodes required for the job.

    Returns
    -------
    partition : str
        The partition to use for the job.

    qos : str
        The quality of service to use for the job.

    constraint : str
        Any constraints to use for the job.

    gpus_per_node : str
        The number of GPUs per node to request.

    wall_time : str
        The wall time to request for the job.
    """
    partition, qos, constraint, gpus_per_node, wall_time, _ = _get_job_options(
        config,
        machine,
        nodes,
        partition_or_queue_option='partition',
        partitions_or_queues='partitions',
    )
    return partition, qos, constraint, gpus_per_node, wall_time


def get_pbs_options(config, machine, nodes):
    """
    Get PBS options for job submission.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options for this test case, a combination of user configs
        and the defaults for the machine and component.

    machine : str
        The name of the machine.

    nodes : int
        The number of nodes required for the job.

    Returns
    -------
    queue : str
        The queue to use for the job.

    constraint : str
        Any constraints to use for the job.

    gpus_per_node : str
        The number of GPUs per node to request.

    wall_time : str
        The wall time to request for the job.
    """
    queue, _, constraint, gpus_per_node, wall_time, filesystems = (
        _get_job_options(
            config,
            machine,
            nodes,
            partition_or_queue_option='queue',
            partitions_or_queues='queues',
        )
    )
    return queue, constraint, gpus_per_node, wall_time, filesystems


def _get_job_options(
    config, machine, nodes, partition_or_queue_option, partitions_or_queues
):
    """
    Helper to get job options for slurm or pbs

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
    machine : str
    nodes : int
    partition_or_queue_option : str
        'partition' for slurm, 'queue' for pbs
    partitions_or_queues : str
        'partitions' for slurm, 'queues' for pbs

    Returns
    -------
    partition_or_queue : str
    qos : str
    constraint : str
    gpus_per_node : str
    wall_time : str
    filesystems : str
    """
    partition_or_queue = config.get('job', partition_or_queue_option)
    if partition_or_queue == '<<<default>>>':
        if machine == 'anvil' and partition_or_queue == 'partition':
            # choose the partition based on the number of nodes
            if nodes <= 5:
                partition_or_queue = 'acme-small'
            elif nodes <= 60:
                partition_or_queue = 'acme-medium'
            else:
                partition_or_queue = 'acme-large'
        elif config.has_option('parallel', partitions_or_queues):
            # get the first, which is the default
            partition_or_queue = config.getlist(
                'parallel', partitions_or_queues
            )[0]
        else:
            partition_or_queue = ''

    qos = config.get('job', 'qos')
    if qos == '<<<default>>>':
        if config.has_option('parallel', 'qos'):
            qos = config.getlist('parallel', 'qos')[0]
        else:
            qos = ''

    constraint = config.get('job', 'constraint')
    if constraint == '<<<default>>>':
        if config.has_option('parallel', 'constraints'):
            constraint = config.getlist('parallel', 'constraints')[0]
        else:
            constraint = ''

    if config.has_option('parallel', 'gpus_per_node'):
        gpus_per_node = config.get('parallel', 'gpus_per_node')
    else:
        gpus_per_node = ''

    wall_time = config.get('job', 'wall_time')

    if config.has_option('job', 'filesystems'):
        filesystems = config.get('job', 'filesystems')
    else:
        filesystems = ''

    return (
        partition_or_queue,
        qos,
        constraint,
        gpus_per_node,
        wall_time,
        filesystems,
    )
