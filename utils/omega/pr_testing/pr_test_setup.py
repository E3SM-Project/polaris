"""
The tester's setup: check the environment against the manifest, find or
set up a baseline, set up the PR suite and CTests, and submit or print the
jobs
"""

import json
import os
import re
import shlex
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterator, List, Optional

import pr_test_git as git_tools
import pr_test_report as report
from pr_test_config import PrTestConfig
from pr_test_git import REF_PREFIX
from pr_test_init import OMEGA_SUBMODULE, POLARIS_DIR, POLARIS_URL
from pr_test_manifest import (
    POLARIS_SUBMODULE,
    Manifest,
    Row,
    fetch_manifest,
)

from polaris.baselines import (
    BaselineCriteria,
    check_baseline,
    check_build,
    find_baseline,
    find_build_log,
)
from polaris.config import PolarisConfigParser
from polaris.job import get_submit_args, is_job_active, submit_job
from polaris.provenance import read as read_provenance

SUITE = 'omega_pr'

#: the build type the PR template's rows are tested with
BUILD_TYPE = 'Release'

#: the file in a row's directory that records what setup did
STATE_FILENAME = 'setup.json'

#: the file in a job's directory that holds its id once submitted
JOB_ID_FILENAME = 'job_id'

#: what the PR suite's dependency is called before the baseline is submitted
BASELINE_JOB_PLACEHOLDER = '<baseline job id>'

#: options added when submitting on a machine, overriding the job script.
#: The omega_pr suite asks for each machine's debug target, but Frontier
#: allows only one debug job at a time, and a row submits several.  Off the
#: debug QOS, the suite's 30-minute wall time, chosen to fit debug queues,
#: is lifted, since the GPU row's baseline ran past it on Omega#524.
#: Aurora's debug queue is limited in the same way; capacity is its queue
#: for jobs of 1 to 16 nodes, since prod starts at 256.
SUBMIT_ARGS: Dict[str, List[str]] = {
    'aurora': ['-q', 'capacity'],
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
#: builds.  setup initializes them once per Omega worktree first, so that
#: rows set up at the same time never update one tree's submodules at once.
OMEGA_SUBMODULES = [
    'externals/ekat',
    'externals/scorpio',
    'components/omega/external',
    'cime',
]

#: how long setup waits for another setup to prepare an Omega worktree
TREE_LOCK_TIMEOUT = 3600

_LOAD_SCRIPT_EXPORT = re.compile(
    r'^export (POLARIS_[A-Z]+)="([^"]*)"$', re.MULTILINE
)


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

    baseline_work_dir : str
        The baseline suite's work directory

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

    ctest_dir : str
        Where the CTest job was set up

    jobs : list of dict
        The jobs to submit, with their ids once submitted

    baseline_polaris_hash : str, optional
        The Polaris commit the baseline was found or set up with, if it is
        not ``polaris_hash``
    """

    fork: str
    branch: str
    row: str
    polaris_hash: str
    baseline_work_dir: str
    baseline_reused: bool
    baseline_job: Optional[str]
    baseline_build_log: Optional[str]
    pr_build_dir: str
    pr_work_dir: str
    ctest_dir: str
    jobs: List[Dict] = field(default_factory=list)
    baseline_polaris_hash: Optional[str] = None


def run_setup(
    config: PrTestConfig,
    fork: str,
    branch: str,
    submit: bool = False,
    baseline_dir: Optional[str] = None,
    baseline_load_script: Optional[str] = None,
    polaris_dir: str = POLARIS_DIR,
) -> SetupState:
    """
    Set up the baseline, PR suite and CTests for this machine's row

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    fork : str
        The URL of the requester's fork

    branch : str
        The test branch

    submit : bool, optional
        Whether to submit the jobs

    baseline_dir : str, optional
        An existing baseline work directory to use, which must match

    baseline_load_script : str, optional
        The load script of a second Polaris checkout to find or set up the
        baseline with, needed when the manifest's baseline Polaris commit
        is not its Polaris commit

    polaris_dir : str, optional
        The Polaris checkout the loaded environment runs

    Returns
    -------
    state : pr_test_setup.SetupState
        What setup did
    """
    manifest = fetch_manifest(config.omega_repo, fork, branch)
    row = _get_env_row(manifest, polaris_dir)
    polaris_hash = _check_checkout(
        polaris_dir, manifest.polaris_commit, 'Polaris commit'
    )
    baseline_polaris = _get_baseline_polaris(
        manifest, row, polaris_dir, baseline_load_script
    )

    run_dir = get_row_dir(config, manifest, row)
    pr_work_dir = os.path.join(run_dir, SUITE)
    if os.path.exists(os.path.join(pr_work_dir, f'{SUITE}_results.json')):
        raise SetupError(
            f'The PR suite in {pr_work_dir} has already run.  Remove '
            f'{run_dir} to test this row again.'
        )

    omega_dir = os.path.join(config.work_base, 'omega')
    test_tree = os.path.join(omega_dir, manifest.test_commit[:12])
    prepare_tree(config.omega_repo, manifest.test_commit, test_tree)

    criteria = BaselineCriteria(
        machine=row.machine,
        compiler=row.compiler,
        build_type=BUILD_TYPE,
        component_hash=manifest.baseline_commit,
        polaris_hash=baseline_polaris.hash,
        suite=SUITE,
    )
    roots = [
        os.path.join(config.work_base, 'baselines')
    ] + config.baseline_search_roots

    jobs = []
    baseline = _get_baseline(
        config, manifest, criteria, roots, baseline_dir, baseline_polaris
    )
    if baseline.job is not None:
        jobs.append(baseline.job)
    baseline_work_dir = baseline.work_dir

    pr_build_dir = os.path.join(run_dir, 'build')
    _polaris_suite(
        polaris_dir,
        branch=test_tree,
        build_dir=pr_build_dir,
        work_dir=pr_work_dir,
        baseline_work_dir=baseline_work_dir,
    )
    jobs.append(
        Job(
            name='PR suite',
            work_dir=pr_work_dir,
            script=f'job_script.{SUITE}.sh',
            depends_on_baseline=True,
        )
    )

    ctest_dir = os.path.join(run_dir, 'ctest')
    jobs.append(_set_up_ctests(polaris_dir, row, pr_build_dir, ctest_dir))

    state = SetupState(
        fork=fork,
        branch=branch,
        row=row.name,
        polaris_hash=polaris_hash,
        baseline_work_dir=baseline_work_dir,
        baseline_reused=baseline.reused,
        baseline_job=baseline.active_job,
        baseline_build_log=_get_baseline_build_log(
            criteria, roots, baseline_work_dir
        ),
        pr_build_dir=pr_build_dir,
        pr_work_dir=pr_work_dir,
        ctest_dir=ctest_dir,
    )
    if baseline_polaris.hash != polaris_hash:
        state.baseline_polaris_hash = baseline_polaris.hash

    if submit:
        _submit(jobs, row.machine, baseline.active_job)
    state.jobs = [asdict(job) for job in jobs]
    write_state(run_dir, state)
    return state


def format_state(state: SetupState, row_dir: str, machine: str) -> str:
    """The summary setup prints, with the commands to submit the jobs"""
    lines = [
        f'Row:        {state.row}',
        f'Polaris:    {state.polaris_hash}',
    ]
    if state.baseline_polaris_hash is not None:
        lines.append(f'            {state.baseline_polaris_hash} (baseline)')
    lines += [
        f'Baseline:   {state.baseline_work_dir}'
        f'{" (reused)" if state.baseline_reused else ""}',
        f'PR build:   {state.pr_build_dir}',
        f'PR suite:   {state.pr_work_dir}',
        f'CTests:     {state.ctest_dir}',
        f'Warnings:   baseline build log '
        f'{state.baseline_build_log or "not found"}',
        '',
    ]
    submitted = [job for job in state.jobs if job['job_id'] is not None]
    if submitted:
        lines.append('Submitted:')
        lines.extend(
            f'  {job["name"]}: job {job["job_id"]}' for job in submitted
        )
    else:
        system = _get_system(machine)
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
    lines.append(f'\nWhen the jobs finish, run report.  State: {row_dir}')
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


def get_row_dir(config: PrTestConfig, manifest: Manifest, row: Row) -> str:
    """The directory a row's runs go in"""
    return os.path.join(
        report.get_run_dir(config, manifest), f'{row.machine}_{row.compiler}'
    )


def get_env_row(manifest: Manifest) -> Row:
    """The manifest's row for the loaded Polaris environment"""
    machine = os.environ.get('POLARIS_MACHINE')
    compiler = os.environ.get('POLARIS_COMPILER')
    if not machine or not compiler:
        raise SetupError(
            'No Polaris environment is loaded.  Source the load script for '
            'the row to test first.'
        )
    row = manifest.get_row(machine, compiler)
    mpi = os.environ.get('POLARIS_MPI')
    if mpi and mpi != row.mpi:
        raise SetupError(
            f'The loaded Polaris environment uses {mpi}, but the row '
            f'{row.name} uses {row.mpi}.'
        )
    return row


def _get_env_row(manifest, polaris_dir):
    branch = os.environ.get('POLARIS_BRANCH')
    if branch and os.path.realpath(branch) != os.path.realpath(polaris_dir):
        raise SetupError(
            f'The loaded Polaris environment belongs to {branch}, not to '
            f'{polaris_dir}, which this utility is part of.  Source the load '
            f'script of this checkout.'
        )
    return get_env_row(manifest)


@contextmanager
def _tree_lock(tree: str) -> Iterator[None]:
    """
    Hold a lock on an Omega worktree, made with mkdir, which is atomic on
    the shared file systems where flock may not work
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
                    f'Another setup has been preparing {tree} for more than '
                    f'{TREE_LOCK_TIMEOUT // 60} minutes.  If none is '
                    f'running, remove {lock} and run setup again.'
                ) from None
            if not waiting:
                print(
                    f'Waiting for another setup to prepare {tree}',
                    flush=True,
                )
                waiting = True
            time.sleep(10)
    try:
        yield
    finally:
        os.rmdir(lock)


@dataclass
class _PolarisCheckout:
    """The Polaris checkout a baseline is found or set up with"""

    directory: str
    hash: str
    # None for the checkout of the loaded environment
    load_script: Optional[str] = None


def _check_checkout(polaris_dir, commit, what):
    """
    Check that a Polaris checkout is clean and contains one of the
    manifest's commits; return its commit
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
            POLARIS_URL,
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


def _get_baseline_polaris(manifest, row, polaris_dir, load_script):
    """
    Check the Polaris checkout the baseline is found or set up with: this
    one, or the one a second load script belongs to
    """
    separate = manifest.baseline_polaris_commit != manifest.polaris_commit
    if load_script is None:
        if separate:
            raise SetupError(
                f'The baseline runs with Polaris '
                f'{manifest.baseline_polaris_commit[:12]}, without the '
                f"changes in the manifest's Polaris commit "
                f'{manifest.polaris_commit[:12]}.  Pass '
                f'--baseline-load-script with the load script for '
                f'{row.name} of a Polaris checkout at that commit.'
            )
        checkout = _PolarisCheckout(
            polaris_dir, git_tools.rev_parse(polaris_dir, 'HEAD')
        )
    else:
        directory = _read_load_script(load_script, row)
        polaris_hash = _check_checkout(
            directory,
            manifest.baseline_polaris_commit,
            'baseline Polaris commit',
        )
        if separate and git_tools.is_ancestor(
            directory, manifest.polaris_commit, 'HEAD'
        ):
            raise SetupError(
                f'The baseline Polaris checkout {directory} contains the '
                f"manifest's Polaris commit {manifest.polaris_commit[:12]}, "
                f'whose changes the baseline Omega cannot run.  Use a '
                f'checkout at {manifest.baseline_polaris_commit[:12]}.'
            )
        checkout = _PolarisCheckout(
            directory, polaris_hash, os.path.abspath(load_script)
        )

    if manifest.baseline_source == POLARIS_SUBMODULE:
        pin = git_tools.submodule_pin(
            checkout.directory, 'HEAD', OMEGA_SUBMODULE
        )
        if pin != manifest.baseline_commit:
            raise SetupError(
                f'The Polaris checkout {checkout.directory} pins Omega '
                f'{pin[:12]}, but the baseline is the submodule of Polaris '
                f'{manifest.baseline_polaris_commit[:12]}, Omega '
                f'{manifest.baseline_commit[:12]}.  Use a Polaris checkout '
                f'that pins the same Omega.'
            )
    return checkout


def _read_load_script(load_script, row):
    """
    The Polaris checkout a load script belongs to, after checking that it
    is for the row
    """
    try:
        with open(load_script, 'r', encoding='utf-8') as f:
            text = f.read()
    except OSError as exc:
        raise SetupError(
            f'The load script {load_script} cannot be read: {exc}'
        ) from exc
    values = dict(_LOAD_SCRIPT_EXPORT.findall(text))
    expected = {
        'POLARIS_MACHINE': row.machine,
        'POLARIS_COMPILER': row.compiler,
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
    return directory


@dataclass
class _Baseline:
    """The baseline setup found or made"""

    work_dir: str
    reused: bool
    job: Optional[Job] = None
    active_job: Optional[str] = None


def _get_baseline(
    config, manifest, criteria, roots, baseline_dir, baseline_polaris
):
    """Find, wait on or set up the baseline"""
    if baseline_dir is not None:
        reasons = check_baseline(baseline_dir, criteria)
        if reasons:
            raise SetupError(
                f'{baseline_dir} cannot be the baseline: {"; ".join(reasons)}.'
            )
        return _Baseline(baseline_dir, reused=True)

    matches, _ = find_baseline(roots, criteria)
    if matches:
        return _Baseline(_newest(matches), reused=True)

    own_dir = os.path.join(
        config.work_base,
        'baselines',
        f'{criteria.machine}_{criteria.compiler}_polaris-'
        f'{criteria.polaris_hash[:7]}_omega-{criteria.component_hash[:7]}',
    )
    work_dir = os.path.join(own_dir, SUITE)
    job = Job(
        name='baseline suite',
        work_dir=work_dir,
        script=f'job_script.{SUITE}.sh',
    )
    if os.path.exists(os.path.join(work_dir, f'{SUITE}.pickle')):
        job_id = _read_job_id(work_dir)
        if job_id is None:
            # set up earlier but never submitted
            return _Baseline(work_dir, reused=False, job=job)
        if is_job_active(job_id, _get_system(criteria.machine)):
            return _Baseline(work_dir, reused=False, active_job=job_id)
        reasons = check_baseline(work_dir, criteria)
        raise SetupError(
            f'The baseline in {work_dir} is not usable and its job '
            f'{job_id} is not running: {"; ".join(reasons)}.  Remove '
            f'{own_dir} to set it up again.'
        )

    baseline_tree = os.path.join(
        config.work_base, 'omega', manifest.baseline_commit[:12]
    )
    prepare_tree(config.omega_repo, manifest.baseline_commit, baseline_tree)
    _polaris_suite(
        baseline_polaris.directory,
        branch=baseline_tree,
        build_dir=os.path.join(own_dir, 'build'),
        work_dir=work_dir,
        load_script=baseline_polaris.load_script,
    )
    return _Baseline(work_dir, reused=False, job=job)


def _polaris_suite(
    polaris_dir,
    branch,
    build_dir,
    work_dir,
    baseline_work_dir=None,
    load_script=None,
):
    """
    Set up the suite, building Omega on this (login) node, with the loaded
    environment or in a clean login shell with another checkout's load
    script sourced
    """
    args = ['polaris', 'suite', '-c', 'ocean', '-t', SUITE, '--model', 'omega']
    args.extend(_build_flags(build_dir))
    args.extend(['--branch', branch, '-p', build_dir, '-w', work_dir])
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
    subprocess.run(args, cwd=polaris_dir, env=env, check=True)


def _build_flags(build_dir):
    """
    The build flags for a build directory: none for a finished build, which
    is reused, and a clean build for an unfinished one, since only a
    complete log from an empty build directory can be compared for warnings
    """
    if os.path.exists(os.path.join(build_dir, 'src', 'omega.exe')):
        return []
    if os.path.exists(build_dir):
        return ['--clean_build', '--quiet_build']
    return ['--build', '--quiet_build']


def _set_up_ctests(polaris_dir, row, build_dir, ctest_dir):
    """Link the CTest meshes into the PR build and write the job script"""
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


def _get_baseline_build_log(criteria, roots, baseline_work_dir):
    """A complete build log of the baseline commit, if there is one"""
    provenance = read_provenance(baseline_work_dir)
    build_dir = None
    if provenance is not None:
        build_dir = provenance.get('build directory')
    if build_dir and not check_build(build_dir, criteria):
        return os.path.join(build_dir, 'build_omega.log')
    logs, _ = find_build_log(roots, criteria)
    return logs[0] if logs else None


def _submit(jobs, machine, active_baseline_id):
    system = _get_system(machine)
    baseline_id = active_baseline_id
    previous_id = None
    for job in jobs:
        dependency = baseline_id if job.depends_on_baseline else None
        if machine in SERIAL_SUBMISSION and previous_id is not None:
            dependency = previous_id
        job.job_id = submit_job(
            job.script,
            job.work_dir,
            system,
            dependency,
            extra_args=SUBMIT_ARGS.get(machine),
        )
        with open(os.path.join(job.work_dir, JOB_ID_FILENAME), 'w') as f:
            f.write(f'{job.job_id}\n')
        previous_id = job.job_id
        if job.name == 'baseline suite':
            baseline_id = job.job_id


def _read_job_id(work_dir):
    path = os.path.join(work_dir, JOB_ID_FILENAME)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read().strip() or None


def _get_system(machine):
    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('mache.machines', f'{machine}.cfg')
    config.add_from_package('polaris.machines', f'{machine}.cfg')
    return config.get('parallel', 'system')


def _newest(work_dirs):
    return max(
        work_dirs,
        key=lambda work_dir: os.path.getmtime(
            os.path.join(work_dir, f'{SUITE}_results.json')
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
