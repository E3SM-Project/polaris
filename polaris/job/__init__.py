import importlib.resources as imp_res
import os as os
import re
import subprocess

import numpy as np
from jinja2 import Template as Template
from mache.parallel import get_parallel_system
from mache.parallel.pbs import PbsOptions, PbsSystem
from mache.parallel.slurm import SlurmOptions, SlurmSystem


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

    Returns
    -------
    options : {mache.parallel.slurm.SlurmOptions, \
mache.parallel.pbs.PbsOptions, None}
        The scheduler options that were rendered into the job script, or
        ``None`` if no job script was written because the machine does not
        use a supported job scheduler
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

    # a specific scheduler target the user has asked for, if any.  mache
    # treats placeholders such as '<<<default>>>' as "no request", so they
    # are passed through unmodified.
    requested_partition = _get_job_option(config, 'partition')
    requested_qos = _get_job_option(config, 'qos')
    requested_queue = _get_job_option(config, 'queue')
    requested_constraint = _get_job_option(config, 'constraint')

    # a target named without saying which axis it is on.  mache maps it onto
    # whichever of the machine's partitions, qos or queues lists it, so the
    # options above win on the axis they name.
    requested_target = _get_job_option(config, 'scheduler_target')

    options: SlurmOptions | PbsOptions
    if system == 'slurm':
        options = SlurmSystem.resolve_slurm_options(
            config=config.combined,
            nodes=nodes,
            min_nodes_allowed=min_nodes_allowed,
            partition=requested_partition,
            qos=requested_qos,
            constraint=requested_constraint,
            desired_wall_time=desired_wall_time,
            scheduler_target=requested_target,
        )
        template_name = 'job_script.slurm.template'
        render_kwargs.update(
            partition=options.partition,
            qos=options.qos,
            constraint=options.constraint,
            gpus_per_node=options.gpus_per_node,
            wall_time=options.wall_time,
        )
    elif system == 'pbs':
        options = PbsSystem.resolve_pbs_options(
            config=config.combined,
            nodes=nodes,
            min_nodes_allowed=min_nodes_allowed,
            queue=requested_queue,
            constraint=requested_constraint,
            desired_wall_time=desired_wall_time,
            scheduler_target=requested_target,
        )
        template_name = 'job_script.pbs.template'
        render_kwargs.update(
            queue=options.queue,
            constraint=options.constraint,
            gpus_per_node=options.gpus_per_node,
            wall_time=options.wall_time,
            filesystems=options.filesystems,
        )
    else:
        # Do not write a job script for other systems
        return None

    nodes = options.effective_nodes

    if not options.honored:
        print(f'Warning: {options.reason}')

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

    return options


class SubmissionError(RuntimeError):
    """The scheduler refused a job script"""


def get_submit_args(job_script, system, dependency=None, extra_args=None):
    """
    Get the command that submits a job script, optionally after another job

    Parameters
    ----------
    job_script : str
        The job script to submit

    system : {'slurm', 'pbs'}
        The scheduler, as in the ``[parallel] system`` config option

    dependency : str, optional
        A job id that must finish, successfully or not, before this job
        starts

    extra_args : list of str, optional
        More options for ``sbatch`` or ``qsub``, which override those in the
        job script

    Returns
    -------
    args : list of str
        The submission command and its arguments
    """
    if system == 'slurm':
        args = ['sbatch']
        if dependency is not None:
            args.extend(
                [
                    f'--dependency=afterany:{dependency}',
                    '--kill-on-invalid-dep=yes',
                ]
            )
    elif system == 'pbs':
        args = ['qsub']
        if dependency is not None:
            args.extend(['-W', f'depend=afterany:{dependency}'])
    else:
        raise ValueError(f'Unsupported parallel system: {system}')
    if extra_args:
        args.extend(extra_args)
    args.append(job_script)
    return args


def submit_job(job_script, work_dir, system, dependency=None, extra_args=None):
    """
    Submit a job script from its work directory

    Polaris job scripts change to the directory they were submitted from, so
    the script is always submitted from ``work_dir``.

    Parameters
    ----------
    job_script : str
        The job script to submit, relative to ``work_dir`` or absolute

    work_dir : str
        The directory to submit the job from

    system : {'slurm', 'pbs'}
        The scheduler, as in the ``[parallel] system`` config option

    dependency : str, optional
        A job id that must finish, successfully or not, before this job
        starts

    extra_args : list of str, optional
        More options for ``sbatch`` or ``qsub``, which override those in the
        job script

    Returns
    -------
    job_id : str
        The id of the submitted job

    Raises
    ------
    polaris.job.SubmissionError
        If the scheduler refuses the job, with its message
    """
    args = get_submit_args(job_script, system, dependency, extra_args)
    result = subprocess.run(args, cwd=work_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise SubmissionError(
            f'"{" ".join(args)}" in {work_dir} failed:\n'
            f'{result.stderr.strip()}'
        )
    return parse_job_id(result.stdout, system)


def parse_job_id(output, system):
    """
    Get the job id from the output of a submission command

    Parameters
    ----------
    output : str
        The output of ``sbatch`` or ``qsub``

    system : {'slurm', 'pbs'}
        The scheduler, as in the ``[parallel] system`` config option

    Returns
    -------
    job_id : str
        The id of the submitted job
    """
    if system == 'slurm':
        match = re.search(r'Submitted batch job (\d+)', output)
        if match is not None:
            return match.group(1)
    else:
        for line in reversed(output.splitlines()):
            job_id = line.strip()
            if re.fullmatch(r'\d+(?:\.[\w.-]+)?', job_id):
                return job_id

    raise ValueError(
        f'Could not determine the {system} job id from output:\n{output}'
    )


def is_job_active(job_id, system):
    """
    Whether a job is still queued or running

    Parameters
    ----------
    job_id : str
        The id of the job

    system : {'slurm', 'pbs'}
        The scheduler, as in the ``[parallel] system`` config option

    Returns
    -------
    active : bool
        Whether the scheduler still lists the job as queued or running
    """
    if system == 'slurm':
        args = ['squeue', '--noheader', '--jobs', job_id, '--format=%T']
    elif system == 'pbs':
        args = ['qstat', job_id]
    else:
        raise ValueError(f'Unsupported parallel system: {system}')

    # both commands fail for a job that has finished and been purged
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() != ''


def _get_job_option(config, option):
    """Get a requested ``[job]`` option, or None if it is unset or empty."""
    if not config.has_option('job', option):
        return None
    value = config.get('job', option).strip()
    if value == '':
        return None
    return value


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
