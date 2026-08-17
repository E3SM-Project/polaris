"""
Build, set up and run Polaris for one side of a benchmark.

This is the piece that is common to the baseline and test runs: the
only difference between them is that the test run is given a baseline
work directory with ``-b``.
"""

import os
import re

from shared import check_call, check_output, print_commands


def setup_and_run(
    state,
    setup_command,
    run_command,
    work_dir,
    component_path,
    baseline_dir=None,
    config_file=None,
    clean_build=False,
    rebuild=False,
    submit=False,
    dependency=None,
    dry_run=False,
    logger=None,
):
    """
    Set up and run one side of a benchmark

    The ``-p``, ``--branch``, ``-w``, ``-b``, ``-f`` and build flags are
    appended automatically, so they must not appear in ``setup_command``.

    Parameters
    ----------
    state : gitrepo.SourceState
        The resolved state of this side of the benchmark
    setup_command : str
        A ``polaris setup`` or ``polaris suite`` command without paths
    run_command : str
        The command used to run Polaris in the work directory, typically
        ``polaris serial``
    work_dir : str
        The work directory for this side of the benchmark
    component_path : str
        The path to build the component in or find an existing build at
    baseline_dir : str, optional
        A baseline work directory to validate against
    config_file : str, optional
        A config file to pass to Polaris with ``-f``
    clean_build : bool, optional
        Whether to start from a clean build directory
    rebuild : bool, optional
        Whether to force a build even if the component is already built
    submit : bool, optional
        Whether to submit the job script rather than running in place
    dependency : str, optional
        A Slurm job id that must complete successfully before this job
        starts, used only when ``submit`` is set
    dry_run : bool, optional
        Whether to only report the commands that would be run
    logger : logging.Logger, optional
        A logger for command output

    Returns
    -------
    job_id : str or None
        The Slurm job id when ``submit`` is set, otherwise ``None``
    """
    full_setup = build_setup_command(
        setup_command=setup_command,
        state=state,
        work_dir=work_dir,
        component_path=component_path,
        baseline_dir=baseline_dir,
        config_file=config_file,
        clean_build=clean_build,
        rebuild=rebuild,
    )

    setup_commands = (
        f'export NO_POLARIS_REINSTALL=true && '
        f'cd {state.path} && '
        f'source {state.load_script} && '
        f'{full_setup}'
    )

    print_commands(
        setup_commands,
        header=f'Set up: {state.name}',
        logger=logger,
    )
    if not dry_run:
        os.makedirs(work_dir, exist_ok=True)
        check_call(setup_commands, logger=logger)

    if submit:
        job_script = f'job_script.{get_suite_name(setup_command)}.sh'
        flags = ''
        if dependency is not None:
            flags = f'--dependency=afterok:{dependency} '
        run_commands = (
            f'source {state.load_script} && '
            f'cd {work_dir} && '
            f'sbatch {flags}{job_script}'
        )
    else:
        run_commands = (
            f'source {state.load_script} && cd {work_dir} && {run_command}'
        )

    print_commands(
        run_commands,
        header=f'Run: {state.name}',
        logger=logger,
    )
    if dry_run:
        return None

    if not submit:
        check_call(run_commands, logger=logger)
        return None

    _check_job_script(work_dir, setup_command)
    output = check_output(run_commands)
    if logger is not None:
        logger.info(output)
    return _parse_job_id(output)


def build_setup_command(
    setup_command,
    state,
    work_dir,
    component_path,
    baseline_dir=None,
    config_file=None,
    clean_build=False,
    rebuild=False,
):
    """
    Append the paths and build flags to a Polaris setup command

    Parameters
    ----------
    setup_command : str
        A ``polaris setup`` or ``polaris suite`` command without paths
    state : gitrepo.SourceState
        The resolved state of this side of the benchmark
    work_dir : str
        The work directory for this side of the benchmark
    component_path : str
        The path to build the component in or find an existing build at
    baseline_dir : str, optional
        A baseline work directory to validate against
    config_file : str, optional
        A config file to pass to Polaris with ``-f``
    clean_build : bool, optional
        Whether to start from a clean build directory
    rebuild : bool, optional
        Whether to force a build even if the component is already built

    Returns
    -------
    command : str
        The full setup command

    Raises
    ------
    ValueError
        If the setup command already contains a flag that is added here
    """
    check_setup_command(setup_command)

    command = (
        f'{setup_command} '
        f'--model {state.model} '
        f'--branch {state.component_branch_path} '
        f'-p {component_path} '
        f'-w {work_dir}'
    )
    if baseline_dir is not None:
        command = f'{command} -b {baseline_dir}'
    if config_file is not None:
        command = f'{command} -f {config_file}'
    if clean_build:
        command = f'{command} --clean_build'
    elif rebuild:
        command = f'{command} --build'
    return command


def check_setup_command(setup_command):
    """
    Check that a setup command does not contain automatically added flags

    Parameters
    ----------
    setup_command : str
        A ``polaris setup`` or ``polaris suite`` command

    Raises
    ------
    ValueError
        If a forbidden flag is present or the command is not a Polaris
        setup or suite command
    """
    if not re.match(r'^polaris\s+(setup|suite)\b', setup_command.strip()):
        raise ValueError(
            f'setup_command must start with "polaris setup" or '
            f'"polaris suite", got:\n  {setup_command}'
        )

    forbidden = [
        '-p',
        '--component_path',
        '-w',
        '--work_dir',
        '-b',
        '--baseline_dir',
        '-f',
        '--config_file',
        '--branch',
        '--model',
        '--build',
        '--clean_build',
    ]
    parts = setup_command.split()
    found = [flag for flag in forbidden if flag in parts]
    if found:
        raise ValueError(
            f'setup_command must not contain {", ".join(found)}; these are '
            f'added automatically by the benchmark driver.'
        )


def get_suite_name(setup_command):
    """
    Get the suite name implied by a Polaris setup command

    Parameters
    ----------
    setup_command : str
        A ``polaris setup`` or ``polaris suite`` command

    Returns
    -------
    suite : str
        The suite name, which is ``custom`` for ``polaris setup``
    """
    parts = setup_command.split()
    if parts[1] == 'suite':
        for flag in ['-t', '--task_suite']:
            if flag in parts:
                index = parts.index(flag)
                if len(parts) > index + 1:
                    return parts[index + 1]
        raise ValueError(
            f'Could not determine the suite name from:\n  {setup_command}'
        )
    return 'custom'


def _check_job_script(work_dir, setup_command):
    """Raise an OSError if the expected job script is missing."""
    job_script = f'job_script.{get_suite_name(setup_command)}.sh'
    if not os.path.exists(os.path.join(work_dir, job_script)):
        raise OSError(
            f'Could not find the job script {job_script} in {work_dir}'
        )


def _parse_job_id(output):
    """Get the Slurm job id from the output of ``sbatch``."""
    match = re.search(r'Submitted batch job (\d+)', output)
    if match is None:
        raise ValueError(
            f'Could not determine the job id from sbatch output:\n{output}'
        )
    return match.group(1)
