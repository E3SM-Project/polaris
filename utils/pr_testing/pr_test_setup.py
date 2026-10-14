"""
The pieces of a tester's setup that the PR testing utilities share: check
the Polaris checkouts and environment, prepare Omega worktrees, find or set
up a baseline, set up suites and CTests, and submit or print the jobs
"""

import glob
import json
import os
import re
import shlex
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

import pr_test_git as git_tools
from pr_test_config import PrTestConfig
from pr_test_git import REF_PREFIX
from pr_test_rows import FORMER_COMPILERS, Row

from polaris.baselines import (
    BaselineCriteria,
    check_baseline,
    check_build,
    find_baseline,
    find_build_log,
)
from polaris.config import PolarisConfigParser
from polaris.job import (
    SubmissionError,
    get_submit_args,
    is_job_active,
    submit_job,
)
from polaris.provenance import read as read_provenance

#: the build type the rows are tested with
BUILD_TYPE = 'Release'

#: the file in a row's directory that records what setup did
STATE_FILENAME = 'setup.json'

#: the file in a job's directory that holds its id once submitted
JOB_ID_FILENAME = 'job_id'

#: what the PR suite's dependency is called before the baseline is submitted
BASELINE_JOB_PLACEHOLDER = '<baseline job id>'

#: options added when submitting on a machine, overriding the job script.
#: The PR suites ask for each machine's debug target, but Frontier allows
#: only one debug job at a time, and a row submits several.  Off the debug
#: QOS, the suites' 30-minute wall time, chosen to fit debug queues, is
#: lifted, since the GPU row's baseline ran past it on Omega#524.  Aurora's
#: debug queue is limited in the same way; capacity is its queue for jobs of
#: 1 to 16 nodes, since prod starts at 256.  Suites on Aurora ran past 30
#: minutes on slow nights too (Omega#546, polaris#835), so they also get an
#: hour.
SUBMIT_ARGS: Dict[str, List[str]] = {
    'aurora': ['-q', 'capacity', '-l', 'walltime=01:00:00'],
    'frontier': ['--qos=normal', '--time=01:00:00'],
}

#: machines where each of a row's jobs waits for the one before.  Aurora
#: limits how many jobs a user may have in the 'Q' state, and a job waiting
#: on a dependency is held ('H') instead, so this keeps one job queued.
SERIAL_SUBMISSION = {'aurora'}

#: the variables a clean login shell keeps, for setting up a baseline from
#: another Polaris checkout
LOGIN_ENV_VARS = ['HOME', 'USER', 'LOGNAME', 'TERM']

#: the submodules polaris/build/build_omega.template initializes before it
#: builds, if they are not already.  setup initializes them once per Omega
#: worktree first, so that rows set up at the same time never update one
#: tree's submodules at once.
OMEGA_SUBMODULES = [
    'externals/ekat',
    'externals/scorpio',
    'components/omega/external',
    'cime',
]

#: the executable a finished build has, by model, relative to the build
EXECUTABLES = {
    'omega': os.path.join('src', 'omega.exe'),
    'mpas-ocean': 'ocean_model',
}

#: where a Polaris checkout has the E3SM branch MPAS-Ocean is built from
E3SM_SUBMODULE = 'e3sm_submodules/E3SM-Project'

#: how long setup waits for another setup to prepare an Omega worktree
TREE_LOCK_TIMEOUT = 3600

_LOAD_SCRIPT_EXPORT = re.compile(r'^export ([A-Z_]+)="([^"]*)"$', re.MULTILINE)


class SetupError(Exception):
    """The environment does not match the manifest, or setup failed"""


@dataclass
class Job:
    """
    A job to submit

    Attributes
    ----------
    name : str
        What the job runs

    work_dir : str
        The directory to submit it from

    script : str
        The job script

    depends_on_baseline : bool
        Whether it must wait for the baseline job

    job_id : str, optional
        Its id once submitted
    """

    name: str
    work_dir: str
    script: str
    depends_on_baseline: bool = False
    job_id: Optional[str] = None


@dataclass
class SetupState:
    """
    What setup did for a row, which ``report`` reads

    Attributes
    ----------
    fork : str
        The requester's fork

    branch : str
        The test branch

    row : str
        ``<machine>/<compiler>``

    polaris_hash : str
        The Polaris commit this machine used

    baseline_work_dir : str, optional
        The baseline suite's work directory, or ``None`` without a baseline

    baseline_reused : bool
        Whether the baseline was an existing run

    baseline_job : str, optional
        The id of the baseline job the PR suite waits on, if the baseline was
        queued or running when setup ran

    baseline_build_log : str, optional
        A complete build log of the baseline commit, if one was found

    pr_build_dir : str
        The PR build

    pr_work_dir : str
        The PR suite's work directory

    ctest_dir : str, optional
        Where the CTest job was set up, if the row has CTests

    jobs : list of dict
        The jobs to submit, with their ids once submitted

    baseline_polaris_hash : str, optional
        The Polaris commit the baseline was found or set up with, if it is
        not ``polaris_hash``

    no_baseline_reason : str, optional
        Why the PR suite ran without a baseline, if it did

    model : str
        The model the row tests

    suite : str
        The suite the row runs

    environment : dict
        Anything a utility records about the loaded environment, such as
        its Spack environment
    """

    fork: str
    branch: str
    row: str
    polaris_hash: str
    baseline_work_dir: Optional[str]
    baseline_reused: bool
    baseline_job: Optional[str]
    baseline_build_log: Optional[str]
    pr_build_dir: str
    pr_work_dir: str
    ctest_dir: Optional[str]
    jobs: List[Dict] = field(default_factory=list)
    baseline_polaris_hash: Optional[str] = None
    no_baseline_reason: Optional[str] = None
    model: str = 'omega'
    suite: str = 'omega_pr'
    environment: Dict[str, str] = field(default_factory=dict)


@dataclass
class PolarisCheckout:
    """
    A Polaris checkout a baseline is found or set up with

    Attributes
    ----------
    directory : str
        The checkout

    hash : str
        Its commit

    compiler : str
        The row's compiler, or its name before Polaris renamed it

    load_script : str, optional
        Its load script for the row, or ``None`` for the checkout of the
        loaded environment
    """

    directory: str
    hash: str
    compiler: str
    load_script: Optional[str] = None


@dataclass
class Baseline:
    """
    The baseline setup found or made

    Attributes
    ----------
    work_dir : str
        The baseline suite's work directory

    reused : bool
        Whether it is an existing run

    job : pr_test_setup.Job, optional
        Its job, if it was set up and needs submitting

    active_job : str, optional
        The id of its job, if it is queued or running
    """

    work_dir: str
    reused: bool
    job: Optional[Job] = None
    active_job: Optional[str] = None


def get_env_row(rows: List[Row]) -> Row:
    """
    The row for the loaded Polaris environment

    Parameters
    ----------
    rows : list of pr_test_rows.Row
        The rows being tested

    Returns
    -------
    row : pr_test_rows.Row
        The row whose machine and compiler are the environment's
    """
    machine = os.environ.get('POLARIS_MACHINE')
    compiler = os.environ.get('POLARIS_COMPILER')
    if not machine or not compiler:
        raise SetupError(
            'No Polaris environment is loaded.  Source the load script for '
            'the row to test first.'
        )
    matches = [
        row
        for row in rows
        if row.machine == machine and row.compiler == compiler
    ]
    if not matches:
        names = ', '.join(row.name for row in rows)
        raise SetupError(
            f'There is no row for {machine}/{compiler}; the rows are {names}.'
        )
    row = matches[0]
    mpi = os.environ.get('POLARIS_MPI')
    if mpi and mpi != row.mpi:
        raise SetupError(
            f'The loaded Polaris environment uses {mpi}, but the row '
            f'{row.name} uses {row.mpi}.'
        )
    return row


def check_env_checkout(polaris_dir: str) -> None:
    """
    Check that the loaded Polaris environment belongs to a checkout

    Parameters
    ----------
    polaris_dir : str
        The checkout the utility is part of
    """
    branch = os.environ.get('POLARIS_BRANCH')
    if branch and os.path.realpath(branch) != os.path.realpath(polaris_dir):
        raise SetupError(
            f'The loaded Polaris environment belongs to {branch}, not to '
            f'{polaris_dir}, which this utility is part of.  Source the load '
            f'script of this checkout.'
        )


def check_checkout(polaris_dir: str, commit: str, what: str) -> str:
    """
    Check that a Polaris checkout is clean and contains a commit

    Parameters
    ----------
    polaris_dir : str
        The checkout

    commit : str
        The commit it must contain, fetched from E3SM-Project/polaris if
        the checkout does not have it

    what : str
        What the commit is, for messages, such as ``Polaris commit``

    Returns
    -------
    polaris_hash : str
        The checkout's commit
    """
    changes = git_tools.uncommitted_changes(polaris_dir)
    if changes:
        raise SetupError(
            f'The Polaris checkout {polaris_dir} has uncommitted changes to '
            f'{", ".join(changes[:5])}.  Commit or remove them first.'
        )
    if not git_tools.has_commit(polaris_dir, commit):
        git_tools.fetch(
            polaris_dir,
            git_tools.POLARIS_URL,
            [f'refs/heads/main:{REF_PREFIX}/polaris-main'],
        )
    if not git_tools.has_commit(
        polaris_dir, commit
    ) or not git_tools.is_ancestor(polaris_dir, commit, 'HEAD'):
        raise SetupError(
            f'The Polaris checkout {polaris_dir} does not contain the '
            f"manifest's {what} {commit[:12]}.  Update it (and rerun "
            f'./deploy.py if needed) first.'
        )
    return git_tools.rev_parse(polaris_dir, 'HEAD')


def find_load_script(polaris_dir: str, row: Row) -> str:
    """
    A Polaris checkout's load script for a row, under the name the row's
    compiler had before Polaris renamed it if the checkout is older

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout, such as the settings' ``polaris_main``

    row : pr_test_rows.Row
        The row

    Returns
    -------
    load_script : str
        The newest matching load script
    """
    compilers = [row.compiler]
    former = FORMER_COMPILERS.get((row.machine, row.compiler))
    if former is not None:
        compilers.append(former)
    for compiler in compilers:
        pattern = os.path.join(
            polaris_dir, f'load_polaris*_{row.machine}_{compiler}_{row.mpi}.sh'
        )
        matches = glob.glob(pattern)
        if matches:
            return max(matches, key=os.path.getmtime)
    raise SetupError(
        f'The Polaris checkout {polaris_dir} has no load script for '
        f'{row.machine}/{row.compiler} with {row.mpi}.  Run ./deploy.py '
        f'there with --compiler {compilers[-1]}, or pass '
        f'--baseline-load-script.'
    )


def read_load_script(load_script: str, row: Row) -> Tuple[str, str]:
    """
    The Polaris checkout a load script belongs to and its compiler, after
    checking that it is for the row.  The compiler may be the row's name
    from before Polaris renamed it.

    Parameters
    ----------
    load_script : str
        The load script

    row : pr_test_rows.Row
        The row it must be for

    Returns
    -------
    directory : str
        The Polaris checkout

    compiler : str
        The load script's compiler
    """
    try:
        with open(load_script, 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError as exc:
        raise SetupError(
            f'The load script {load_script} cannot be read: {exc}'
        ) from exc
    values = read_exports(text)
    former = FORMER_COMPILERS.get((row.machine, row.compiler))
    if former is not None and values.get('POLARIS_COMPILER') == former:
        compiler = former
    else:
        compiler = row.compiler
    expected = {
        'POLARIS_MACHINE': row.machine,
        'POLARIS_COMPILER': compiler,
        'POLARIS_MPI': row.mpi,
    }
    for name, value in expected.items():
        if values.get(name) != value:
            raise SetupError(
                f'The load script {load_script} sets {name} to '
                f'{values.get(name)}, not {value} for the row {row.name}.'
            )
    directory = values.get('POLARIS_BRANCH')
    if not directory or not os.path.isdir(directory):
        raise SetupError(
            f'The load script {load_script} does not name a Polaris '
            f'checkout in POLARIS_BRANCH.'
        )
    return directory, compiler


def read_exports(text: str) -> Dict[str, str]:
    """The variables a load script exports, with their values"""
    return dict(_LOAD_SCRIPT_EXPORT.findall(text))


def ensure_commit(repo: str, url: str, sha: str) -> None:
    """
    Make sure a repository has a commit, fetching it from a URL if needed

    Parameters
    ----------
    repo : str
        The repository

    url : str
        Where to fetch the commit from

    sha : str
        The full hash of the commit
    """
    if not git_tools.has_commit(repo, sha):
        git_tools.fetch(repo, url, [f'{sha}:{REF_PREFIX}/commit-{sha[:12]}'])


def prepare_tree(repo: str, sha: str, tree: str) -> None:
    """
    Make an Omega worktree and initialize the submodules its build needs,
    once, even when several setups need the tree at the same time

    Parameters
    ----------
    repo : str
        The Omega clone to make the worktree from

    sha : str
        The commit to check out

    tree : str
        The path of the worktree
    """
    ready = f'{tree}.ready'
    if not os.path.exists(ready):
        with _tree_lock(tree):
            if not os.path.exists(ready):
                git_tools.add_worktree(repo, sha, tree)
                git_tools.git(
                    ['submodule', 'update', '--init', '--recursive', '--']
                    + OMEGA_SUBMODULES,
                    tree,
                )
                with open(ready, 'w') as f:
                    f.write(f'{sha}\n')
    git_tools.add_worktree(repo, sha, tree)


def get_baseline(
    config: PrTestConfig,
    criteria: BaselineCriteria,
    roots: List[str],
    baseline_dir: Optional[str],
    checkout: PolarisCheckout,
    model: str,
) -> Baseline:
    """
    Find, wait on or set up a baseline

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    criteria : polaris.baselines.BaselineCriteria
        What the baseline must match; its component commit is the one set
        up if no baseline is found

    roots : list of str
        Where to look for a baseline to reuse

    baseline_dir : str, optional
        An existing baseline work directory the tester named, which must
        match

    checkout : pr_test_setup.PolarisCheckout
        The Polaris checkout to set the baseline up with

    model : str
        The model the suite runs, ``omega`` or ``mpas-ocean``.  Omega is
        built from a worktree of the component commit, and MPAS-Ocean from
        the checkout's E3SM-Project submodule.

    Returns
    -------
    baseline : pr_test_setup.Baseline
        The baseline
    """
    suite = criteria.suite
    if baseline_dir is not None:
        reasons = check_baseline(baseline_dir, criteria)
        if reasons:
            raise SetupError(
                f'{baseline_dir} cannot be the baseline: {"; ".join(reasons)}.'
            )
        return Baseline(baseline_dir, reused=True)

    matches, _ = find_baseline(roots, criteria)
    if matches:
        return Baseline(_newest(matches, suite), reused=True)

    component = 'omega' if model == 'omega' else 'e3sm'
    own_dir = os.path.join(
        config.work_base,
        'baselines',
        f'{criteria.machine}_{criteria.compiler}_polaris-'
        f'{criteria.polaris_hash[:7]}_{component}-'
        f'{criteria.component_hash[:7]}',
    )
    work_dir = os.path.join(own_dir, suite)
    job = Job(
        name='baseline suite',
        work_dir=work_dir,
        script=f'job_script.{suite}.sh',
    )
    if os.path.exists(os.path.join(work_dir, f'{suite}.pickle')):
        job_id = _read_job_id(work_dir)
        if job_id is None:
            # set up earlier but never submitted
            return Baseline(work_dir, reused=False, job=job)
        if is_job_active(job_id, get_system(criteria.machine)):
            return Baseline(work_dir, reused=False, active_job=job_id)
        if _finished(work_dir, suite):
            # This utility set the baseline up, from a checkout whose
            # tracked files were checked, so a finished run is used even if
            # some of its tasks failed or the checkout's submodules were not
            # at their pins, which the stricter test for reusing a run
            # rejects.  The report gives each task's comparison.
            return Baseline(work_dir, reused=False)
        reasons = check_baseline(work_dir, criteria)
        raise SetupError(
            f'The baseline in {work_dir} is not usable and its job '
            f'{job_id} is not running: {"; ".join(reasons)}.  Remove '
            f'{own_dir} to set it up again.'
        )

    baseline_tree = None
    if model == 'omega':
        baseline_tree = os.path.join(
            config.work_base, 'omega', criteria.component_hash[:12]
        )
        prepare_tree(config.omega_repo, criteria.component_hash, baseline_tree)
    polaris_suite(
        checkout.directory,
        suite=suite,
        model=model,
        branch=baseline_tree,
        build_dir=os.path.join(own_dir, 'build'),
        work_dir=work_dir,
        load_script=checkout.load_script,
    )
    return Baseline(work_dir, reused=False, job=job)


def polaris_suite(
    polaris_dir: str,
    suite: str,
    model: str,
    branch: Optional[str],
    build_dir: str,
    work_dir: str,
    baseline_work_dir: Optional[str] = None,
    load_script: Optional[str] = None,
) -> None:
    """
    Set up a suite, building the model on this (login) node, with the
    loaded environment or in a clean login shell with another checkout's
    load script sourced

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout to set the suite up with

    suite : str
        The suite, such as ``omega_pr``

    model : str
        The model it runs, ``omega`` or ``mpas-ocean``

    branch : str, optional
        The model's source tree, or ``None`` for the checkout's submodule.
        MPAS-Ocean builds in its source tree, so builds from the checkout's
        E3SM-Project submodule take turns.

    build_dir : str
        Where to build, or the finished build to reuse

    work_dir : str
        The suite's work directory

    baseline_work_dir : str, optional
        The baseline to compare against

    load_script : str, optional
        Another checkout's load script to source in a clean login shell
    """
    args = ['polaris', 'suite', '-c', 'ocean', '-t', suite, '--model', model]
    args.extend(_build_flags(build_dir, model))
    if branch is not None:
        args.extend(['--branch', branch])
    args.extend(['-p', build_dir, '-w', work_dir])
    if baseline_work_dir is not None:
        args.extend(['-b', baseline_work_dir])
    print(f'\nRunning in {polaris_dir}:\n  {shlex.join(args)}\n', flush=True)
    if load_script is not None:
        print(
            f'with {load_script} sourced in a clean login shell\n',
            flush=True,
        )
        env = {
            name: os.environ[name]
            for name in LOGIN_ENV_VARS
            if name in os.environ
        }
        command = (
            f'source {shlex.quote(load_script)} && '
            f'cd {shlex.quote(polaris_dir)} && {shlex.join(args)}'
        )
        args = ['/bin/bash', '-l', '-c', command]
    else:
        env = None
    # provenance reads the Polaris commit from the directory Polaris runs in,
    # and the job script loads the environment Polaris was set up with
    if model == 'mpas-ocean' and branch is None:
        with _tree_lock(os.path.join(polaris_dir, E3SM_SUBMODULE)):
            subprocess.run(args, cwd=polaris_dir, env=env, check=True)
    else:
        subprocess.run(args, cwd=polaris_dir, env=env, check=True)


def set_up_ctests(
    polaris_dir: str, row: Row, build_dir: str, ctest_dir: str
) -> Job:
    """
    Link the CTest meshes into an Omega build and write the job script

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout with the CTest utility

    row : pr_test_rows.Row
        The row

    build_dir : str
        The Omega build

    ctest_dir : str
        Where to set the CTests up

    Returns
    -------
    job : pr_test_setup.Job
        The CTest job
    """
    os.makedirs(ctest_dir, exist_ok=True)
    utility = os.path.join(polaris_dir, 'utils', 'omega', 'ctest')
    args = ['python', os.path.join(utility, 'omega_ctest.py'), '-p', build_dir]
    print(f'\nRunning in {ctest_dir}:\n  {shlex.join(args)}\n', flush=True)
    subprocess.run(args, cwd=ctest_dir, check=True)
    script = os.path.join(
        'build_omega',
        f'job_build_and_ctest_omega_{row.machine}_{row.compiler}.sh',
    )
    return Job(name='CTests', work_dir=ctest_dir, script=script)


def get_baseline_build_log(
    criteria: BaselineCriteria, roots: List[str], baseline_work_dir: str
) -> Optional[str]:
    """A complete build log of the baseline commit, if there is one"""
    provenance = read_provenance(baseline_work_dir)
    build_dir = None
    if provenance is not None:
        build_dir = provenance.get('build directory')
    if build_dir and not check_build(build_dir, criteria):
        return os.path.join(build_dir, 'build_omega.log')
    logs, _ = find_build_log(roots, criteria)
    return logs[0] if logs else None


def read_submitted_state(row_dir: str) -> Optional[SetupState]:
    """What setup did for a row, if it has submitted any of its jobs"""
    if not os.path.exists(os.path.join(row_dir, STATE_FILENAME)):
        return None
    state = read_state(row_dir)
    if not any(job['job_id'] is not None for job in state.jobs):
        return None
    return state


def resume(
    state: SetupState, machine: str, row_dir: str, submit: bool
) -> SetupState:
    """
    Submit the jobs a row's earlier setup did not, without setting it up
    again under the jobs already running
    """
    jobs = [Job(**job) for job in state.jobs]
    if all(job.job_id is not None for job in jobs):
        ids = ', '.join(f'{job.name} {job.job_id}' for job in jobs)
        raise SetupError(
            f'This row has already submitted its jobs ({ids}).  Run report '
            f'when they finish, or remove {row_dir} to test it again.'
        )
    if submit:
        submit_jobs(state, jobs, machine, row_dir)
    return state


def submit_jobs(
    state: SetupState, jobs: List[Job], machine: str, row_dir: str
) -> None:
    """
    Submit the jobs that have no id yet, recording each id in the state as
    it is submitted, so a refused job leaves the others' ids behind
    """
    system = get_system(machine)
    baseline_id = state.baseline_job
    previous_id = None
    for job in jobs:
        if job.job_id is None:
            dependency = baseline_id if job.depends_on_baseline else None
            if machine in SERIAL_SUBMISSION and previous_id is not None:
                dependency = previous_id
            try:
                job.job_id = submit_job(
                    job.script,
                    job.work_dir,
                    system,
                    dependency,
                    extra_args=SUBMIT_ARGS.get(machine),
                )
            except SubmissionError as exc:
                raise SubmissionError(
                    f'{exc}\nThe jobs submitted before it are recorded in '
                    f'{os.path.join(row_dir, STATE_FILENAME)}.  Once the '
                    f'scheduler allows it, run setup --submit again to '
                    f'submit the rest.'
                ) from exc
            with open(os.path.join(job.work_dir, JOB_ID_FILENAME), 'w') as f:
                f.write(f'{job.job_id}\n')
            state.jobs = [asdict(submitted) for submitted in jobs]
            write_state(row_dir, state)
        previous_id = job.job_id
        if job.name == 'baseline suite':
            baseline_id = job.job_id


def format_state(state: SetupState, row_dir: str, machine: str) -> str:
    """The summary setup prints, with the commands to submit the jobs"""
    lines = [
        f'Row:        {state.row}',
        f'Polaris:    {state.polaris_hash}',
    ]
    if state.baseline_polaris_hash is not None:
        lines.append(f'            {state.baseline_polaris_hash} (baseline)')
    if state.no_baseline_reason is not None:
        baseline = f'none, because {state.no_baseline_reason}'
    else:
        baseline = (
            f'{state.baseline_work_dir}'
            f'{" (reused)" if state.baseline_reused else ""}'
        )
    lines += [
        f'Baseline:   {baseline}',
        f'PR build:   {state.pr_build_dir}',
        f'PR suite:   {state.pr_work_dir}',
    ]
    if state.ctest_dir is not None:
        lines += [
            f'CTests:     {state.ctest_dir}',
            f'Warnings:   baseline build log '
            f'{state.baseline_build_log or "not found"}',
        ]
    lines.append('')
    submitted = [job for job in state.jobs if job['job_id'] is not None]
    if submitted:
        lines.append('Submitted:')
        lines.extend(
            f'  {job["name"]}: job {job["job_id"]}' for job in submitted
        )
        pending = [job['name'] for job in state.jobs if job['job_id'] is None]
        if pending:
            lines.append(
                f'Not yet submitted: {", ".join(pending)}.  With the '
                f"requester's permission, run setup --submit again to "
                f'submit them.'
            )
    else:
        system = get_system(machine)
        lines.append(
            "Nothing was submitted.  With the requester's permission, run "
            'these, one at a time, in this order:'
        )
        previous = None
        for job in state.jobs:
            dependency = None
            if job['depends_on_baseline']:
                dependency = state.baseline_job or _baseline_placeholder(state)
            if machine in SERIAL_SUBMISSION and previous is not None:
                dependency = _job_placeholder(previous)
            args = get_submit_args(
                job['script'], system, dependency, SUBMIT_ARGS.get(machine)
            )
            lines.append(f'  cd {job["work_dir"]} && {shlex.join(args)}')
            previous = job['name']
        lines.append(
            f'Then record each job id in {JOB_ID_FILENAME} in the directory '
            f'it was submitted from.'
        )
    lines.append(
        f"\nWhen all of this machine's rows have finished, run report.  "
        f'State: {row_dir}'
    )
    return '\n'.join(lines)


def write_state(row_dir: str, state: SetupState) -> None:
    """Write what setup did for a row"""
    os.makedirs(row_dir, exist_ok=True)
    with open(os.path.join(row_dir, STATE_FILENAME), 'w') as f:
        json.dump(asdict(state), f, indent=2)
        f.write('\n')


def read_state(row_dir: str) -> SetupState:
    """Read what setup did for a row"""
    path = os.path.join(row_dir, STATE_FILENAME)
    try:
        with open(path) as f:
            return SetupState(**json.load(f))
    except OSError as exc:
        raise SetupError(
            f'There is no {STATE_FILENAME} in {row_dir}; run setup first.'
        ) from exc


def get_system(machine: str) -> str:
    """The job scheduler of a machine, such as ``slurm`` or ``pbs``"""
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('mache.machines', f'{machine}.cfg')
    config.add_from_package('polaris.machines', f'{machine}.cfg')
    return config.get('parallel', 'system')


@contextmanager
def _tree_lock(tree: str) -> Iterator[None]:
    """
    Hold a lock on a source tree, made with mkdir, which is atomic on the
    shared file systems where flock may not work
    """
    lock = f'{tree}.lock'
    os.makedirs(os.path.dirname(lock), exist_ok=True)
    start = time.monotonic()
    waiting = False
    while True:
        try:
            os.mkdir(lock)
            break
        except FileExistsError:
            if time.monotonic() - start > TREE_LOCK_TIMEOUT:
                raise SetupError(
                    f'Another setup has been using {tree} for more than '
                    f'{TREE_LOCK_TIMEOUT // 60} minutes.  If none is '
                    f'running, remove {lock} and run setup again.'
                ) from None
            if not waiting:
                print(
                    f'Waiting for another setup to finish with {tree}',
                    flush=True,
                )
                waiting = True
            time.sleep(10)
    try:
        yield
    finally:
        os.rmdir(lock)


def _build_flags(build_dir, model):
    """
    The build flags for a build directory: none for a finished build, which
    is reused, and a clean build for an unfinished one, since only a
    complete log from an empty build directory can be compared for warnings
    """
    if os.path.exists(os.path.join(build_dir, EXECUTABLES[model])):
        return []
    if os.path.exists(build_dir):
        return ['--clean_build', '--quiet_build']
    return ['--build', '--quiet_build']


def _finished(work_dir, suite):
    """Whether a suite's run finished, whatever its tasks' results"""
    path = os.path.join(work_dir, f'{suite}_results.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return bool(json.load(f).get('complete', False))
    except (OSError, ValueError):
        return False


def _read_job_id(work_dir):
    path = os.path.join(work_dir, JOB_ID_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().strip() or None


def _newest(work_dirs, suite):
    return max(
        work_dirs,
        key=lambda work_dir: os.path.getmtime(
            os.path.join(work_dir, f'{suite}_results.json')
        ),
    )


def _baseline_placeholder(state):
    if any(job['name'] == 'baseline suite' for job in state.jobs):
        return BASELINE_JOB_PLACEHOLDER
    return None


def _job_placeholder(name):
    """What a job's id is called before it is submitted"""
    if name == 'baseline suite':
        return BASELINE_JOB_PLACEHOLDER
    return f'<{name} job id>'
