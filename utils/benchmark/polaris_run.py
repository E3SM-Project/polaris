"""
Build, set up and run Polaris for one side of a benchmark.

This is the piece that is common to the baseline and test runs: the
only difference between them is that the test run is given a baseline
work directory with ``-b``.
"""

import os
import re

from shared import check_call, check_output, print_commands

#: The job id reported for a submitted job during a dry run
#:
#: A dry run submits nothing, so there is no id to give the test side for
#: its ``--dependency``.  Without a stand-in, the dry run prints an
#: ``sbatch`` line that is not the one it would really run, which is how
#: the dependency went unexamined long enough to ship as ``afterok``.
DRY_RUN_JOB_ID = '<baseline job id>'


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

    The ``-p``, ``--model``, ``--branch``, ``-w``, ``-b``, ``-f`` and build
    flags are appended automatically, so they must not appear in
    ``setup_command``.  ``--model`` and ``--branch`` are omitted when the
    side's model is ``none``, since there is then no component to build.

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
        A Slurm job id that must finish -- with or without failing tasks
        -- before this job starts, used only when ``submit`` is set
    dry_run : bool, optional
        Whether to only report the commands that would be run
    logger : logging.Logger, optional
        A logger for command output

    Returns
    -------
    job_id : str or None
        The Slurm job id when ``submit`` is set, otherwise ``None``.  A
        dry run submits nothing and reports ``DRY_RUN_JOB_ID``, so that
        the ``sbatch`` line it prints for the test side is the one it
        would really run.
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
            # afterany, not afterok.  A suite exits non-zero when any
            # task in it fails.  A baseline should not have failures, and
            # one that does is worth fixing -- but a single failed task
            # does not invalidate the rest, whose baseline output is on
            # disk and comparable.  With afterok one failure cost the
            # whole comparison, with nothing to do but run it all again.
            #
            # --kill-on-invalid-dep so that a dependency that can never be
            # satisfied, as when the baseline job is cancelled, removes
            # this job instead of leaving it queued forever.
            flags = (
                f'--dependency=afterany:{dependency} '
                f'--kill-on-invalid-dep=yes '
            )
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
        return DRY_RUN_JOB_ID if submit else None

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

    parts = [setup_command]
    # a side that builds no component has no model and no branch to pass on
    branch = state.component_branch_path
    if branch is not None:
        parts.append(f'--model {state.model}')
        parts.append(f'--branch {branch}')
    parts.append(f'-p {component_path}')
    parts.append(f'-w {work_dir}')
    if baseline_dir is not None:
        parts.append(f'-b {baseline_dir}')
    if config_file is not None:
        parts.append(f'-f {config_file}')
    if clean_build:
        parts.append('--clean_build')
    elif rebuild:
        parts.append('--build')
    return ' '.join(parts)


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
    Get the name a Polaris setup command gives its suite

    ``polaris suite`` takes the name from ``-t``.  ``polaris setup`` calls
    its suite ``custom`` unless it is given ``--suite_name``, so the name
    is required there: it is what tells one benchmark's baseline and job
    script apart from another's.

    Parameters
    ----------
    setup_command : str
        A ``polaris setup`` or ``polaris suite`` command

    Returns
    -------
    suite : str
        The suite name

    Raises
    ------
    ValueError
        If the command does not name its suite
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

    if '--suite_name' in parts:
        index = parts.index('--suite_name')
        if len(parts) > index + 1:
            return parts[index + 1]

    raise ValueError(
        f'A "polaris setup" command must name its suite with --suite_name.  '
        f'Polaris would otherwise call it "custom", so every benchmark set '
        f'up this way would share one baseline directory and one job script '
        f'name.  Got:\n  {setup_command}'
    )


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
