import importlib.resources as imp_res
import os as os

import numpy as np
from jinja2 import Template as Template


def write_job_script(
    config, machine, target_cores, min_cores, work_dir, suite=''
):
    """

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Configuration options for this test case, a combination of user configs
        and the defaults for the machine and component

    machine : {str, None}
        The name of the machine

    target_cores : int
        The target number of cores for the job to use

    min_cores : int
        The minimum number of cores for the job to use

    work_dir : str
        The work directory where the job script should be written

    suite : str, optional
        The name of the suite
    """

    if config.has_option('parallel', 'account'):
        account = config.get('parallel', 'account')
    else:
        account = ''

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
        queue, constraint, gpus_per_node, wall_time = get_pbs_options(
            config, machine, nodes
        )
        template_name = 'job_script.pbs.template'
        render_kwargs.update(
            queue=queue,
            constraint=constraint,
            gpus_per_node=gpus_per_node,
            wall_time=wall_time,
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

    render_kwargs.update(
        job_name=job_name,
        account=account,
        nodes=f'{nodes}',
        suite=suite,
    )

    text = template.render(**render_kwargs)
    text = clean_up_whitespace(text)
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
    partition, qos, constraint, gpus_per_node, wall_time = _get_job_options(
        config, machine, nodes, key='partition', list_key='partitions'
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
    queue, _, constraint, gpus_per_node, wall_time = _get_job_options(
        config, machine, nodes, key='queue', list_key='queues'
    )
    return queue, constraint, gpus_per_node, wall_time


def _get_job_options(config, machine, nodes, key, list_key):
    """
    Helper to get job options for slurm or pbs

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
    machine : str
    nodes : int
    key : str
        'partition' for slurm, 'queue' for pbs
    list_key : str
        'partitions' for slurm, 'queues' for pbs

    Returns
    -------
    key_value : str
    qos : str
    constraint : str
    gpus_per_node : str
    wall_time : str
    """
    key_value = config.get('job', key)
    if key_value == '<<<default>>>':
        if machine == 'anvil' and key == 'partition':
            # choose the partition based on the number of nodes
            if nodes <= 5:
                key_value = 'acme-small'
            elif nodes <= 60:
                key_value = 'acme-medium'
            else:
                key_value = 'acme-large'
        elif config.has_option('parallel', list_key):
            # get the first, which is the default
            key_value = config.getlist('parallel', list_key)[0]
        else:
            key_value = ''

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

    return key_value, qos, constraint, gpus_per_node, wall_time


def clean_up_whitespace(text):
    """
    Clean up whitespace after jinja templating

    Parameters
    ----------
    text : str
        Text to clean up

    Returns
    -------
    text : str
        Text with extra blank lines removed
    """
    prev_line = None
    lines = text.split('\n')
    trimmed = list()
    # remove extra blank lines
    for line in lines:
        if line != '' or prev_line != '':
            trimmed.append(line)
            prev_line = line

    line = ''
    lines = list()
    # remove blank lines between comments
    for next_line in trimmed:
        if line != '' or not next_line.startswith('#'):
            lines.append(line)
        line = next_line

    # add the last line that we missed and an extra blank line
    lines.extend([trimmed[-1], ''])
    text = '\n'.join(lines)
    return text
