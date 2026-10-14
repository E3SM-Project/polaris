"""
The tester's setup: check the checkout and loaded environment against the
manifest, then, for each row the load script tests, find or set up a
baseline, set up the PR suite and any CTests, and submit or print the jobs
"""

import os
from dataclasses import asdict
from typing import Dict, List, Optional, Tuple

import pr_test_git as git_tools
import pr_test_setup as setup_tools
from polaris_update_deploy import DeployError, read_environment
from polaris_update_manifest import (
    SUITES,
    Manifest,
    PolarisSide,
    fetch_manifest,
)
from pr_test_config import PrTestConfig
from pr_test_git import OMEGA_SUBMODULE, OMEGA_URL, POLARIS_DIR, REF_PREFIX
from pr_test_rows import Row
from pr_test_setup import (
    BUILD_TYPE,
    E3SM_SUBMODULE,
    Baseline,
    Job,
    PolarisCheckout,
    SetupError,
    SetupState,
)

from polaris.baselines import BaselineCriteria


def run_setup(
    config: PrTestConfig,
    fork: str,
    branch: str,
    submit: bool = False,
    baseline_load_script: Optional[str] = None,
    no_baseline: Optional[str] = None,
    model: Optional[str] = None,
    polaris_dir: str = POLARIS_DIR,
) -> List[Tuple[SetupState, str]]:
    """
    Set up the rows the loaded load script tests

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    fork : str
        The URL of the requester's Polaris fork

    branch : str
        The test branch

    submit : bool, optional
        Whether to submit the jobs

    baseline_load_script : str, optional
        The load script for the same compiler in a second Polaris checkout
        at the manifest's baseline commit, needed when the manifest has a
        baseline

    no_baseline : str, optional
        Why these rows run without the manifest's baseline, for rows the
        baseline cannot run

    model : str, optional
        Set up only the load script's row for this model, ``omega`` or
        ``mpas-ocean``, rather than all of its rows

    polaris_dir : str, optional
        The Polaris checkout the loaded environment runs

    Returns
    -------
    states : list of tuple
        What setup did for each row, and the row's directory
    """
    if no_baseline is not None and baseline_load_script is not None:
        raise SetupError(
            '--no-baseline cannot be used with --baseline-load-script.'
        )
    manifest = fetch_manifest(polaris_dir, fork, branch)
    setup_tools.check_env_checkout(polaris_dir)
    rows = _get_env_rows(manifest)
    if model is not None:
        rows = [row for row in rows if row.model == model]
        if not rows:
            raise SetupError(f'The loaded load script tests no {model} row.')
    machine = rows[0].machine
    polaris_hash = setup_tools.check_checkout(
        polaris_dir, manifest.pr_head, 'PR head'
    )
    _check_pins(polaris_dir, manifest.test, 'This Polaris checkout')
    try:
        environment = read_environment(polaris_dir, machine)
    except DeployError as exc:
        raise SetupError(str(exc)) from exc

    baseline_checkout = None
    if manifest.baseline is not None and no_baseline is None:
        baseline_checkout = _get_baseline_checkout(
            manifest, rows[0], baseline_load_script, config.polaris_main
        )
    elif baseline_load_script is not None:
        raise SetupError(
            'The manifest has no baseline, so there is no use for '
            '--baseline-load-script.'
        )

    run_dir = get_run_dir(config, manifest, environment['spack'])
    states = []
    for row in rows:
        row_dir = get_row_dir(run_dir, row)
        state = _set_up_row(
            config,
            manifest,
            row,
            row_dir,
            polaris_dir,
            polaris_hash,
            baseline_checkout,
            no_baseline,
            environment,
            fork,
            branch,
            submit,
        )
        states.append((state, row_dir))
    return states


def get_run_dir(config: PrTestConfig, manifest: Manifest, spack: str) -> str:
    """
    The directory this machine's runs with one kind of Spack environment go
    in

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The settings

    manifest : polaris_update_manifest.Manifest
        The manifest

    spack : str
        ``shared`` or ``test``

    Returns
    -------
    run_dir : str
        The directory
    """
    return os.path.join(config.work_base, manifest.run_name, spack)


def get_row_dir(run_dir: str, row: Row) -> str:
    """The directory a row's runs go in"""
    return os.path.join(run_dir, f'{row.machine}_{row.compiler}_{row.model}')


def _set_up_row(
    config,
    manifest: Manifest,
    row: Row,
    row_dir: str,
    polaris_dir: str,
    polaris_hash: str,
    baseline_checkout: Optional[PolarisCheckout],
    no_baseline: Optional[str],
    environment: Dict[str, str],
    fork: str,
    branch: str,
    submit: bool,
) -> SetupState:
    """Find or set up a row's baseline, and set up its PR suite and CTests"""
    assert row.model is not None
    suite = SUITES[row.model]
    pr_work_dir = os.path.join(row_dir, suite)
    if os.path.exists(os.path.join(pr_work_dir, f'{suite}_results.json')):
        raise SetupError(
            f'The PR suite in {pr_work_dir} has already run.  Remove '
            f'{row_dir} to test this row again.'
        )
    previous = setup_tools.read_submitted_state(row_dir)
    if previous is not None:
        return setup_tools.resume(previous, row.machine, row_dir, submit)

    omega = row.model == 'omega'
    tree = None
    if omega:
        tree = _prepare_omega(config, manifest)

    jobs = []
    baseline: Optional[Baseline] = None
    baseline_build_log = None
    if baseline_checkout is not None:
        assert manifest.baseline is not None
        if omega:
            component = manifest.baseline.omega_commit
            setup_tools.ensure_commit(config.omega_repo, OMEGA_URL, component)
        else:
            component = manifest.baseline.e3sm_commit
        criteria = BaselineCriteria(
            machine=row.machine,
            compiler=baseline_checkout.compiler,
            build_type=BUILD_TYPE if omega else None,
            component_hash=component,
            polaris_hash=baseline_checkout.hash,
            suite=suite,
        )
        roots = [
            os.path.join(config.work_base, 'baselines')
        ] + config.baseline_search_roots
        baseline = setup_tools.get_baseline(
            config, criteria, roots, None, baseline_checkout, row.model
        )
        if baseline.job is not None:
            jobs.append(baseline.job)
        if omega:
            baseline_build_log = setup_tools.get_baseline_build_log(
                criteria, roots, baseline.work_dir
            )

    pr_build_dir = os.path.join(row_dir, 'build')
    setup_tools.polaris_suite(
        polaris_dir,
        suite=suite,
        model=row.model,
        branch=tree,
        build_dir=pr_build_dir,
        work_dir=pr_work_dir,
        baseline_work_dir=None if baseline is None else baseline.work_dir,
    )
    jobs.append(
        Job(
            name='PR suite',
            work_dir=pr_work_dir,
            script=f'job_script.{suite}.sh',
            depends_on_baseline=baseline is not None,
        )
    )
    ctest_dir = None
    if omega:
        ctest_dir = os.path.join(row_dir, 'ctest')
        jobs.append(
            setup_tools.set_up_ctests(
                polaris_dir, row, pr_build_dir, ctest_dir
            )
        )

    state = SetupState(
        fork=fork,
        branch=branch,
        row=row.name,
        polaris_hash=polaris_hash,
        baseline_work_dir=None if baseline is None else baseline.work_dir,
        baseline_reused=baseline is not None and baseline.reused,
        baseline_job=None if baseline is None else baseline.active_job,
        baseline_build_log=baseline_build_log,
        pr_build_dir=pr_build_dir,
        pr_work_dir=pr_work_dir,
        ctest_dir=ctest_dir,
        no_baseline_reason=no_baseline,
        model=row.model,
        suite=suite,
        environment=dict(environment),
    )
    if (
        baseline_checkout is not None
        and baseline_checkout.hash != polaris_hash
    ):
        state.baseline_polaris_hash = baseline_checkout.hash
    state.jobs = [asdict(job) for job in jobs]
    setup_tools.write_state(row_dir, state)
    if submit:
        setup_tools.submit_jobs(state, jobs, row.machine, row_dir)
    return state


def _get_env_rows(manifest: Manifest) -> List[Row]:
    """The manifest's rows for the loaded Polaris environment"""
    machine = os.environ.get('POLARIS_MACHINE')
    compiler = os.environ.get('POLARIS_COMPILER')
    if not machine or not compiler:
        raise SetupError(
            'No Polaris environment is loaded.  Source the load script for '
            'the rows to test first.'
        )
    rows = manifest.get_env_rows(machine, compiler)
    if not rows:
        names = ', '.join(row.name for row in manifest.rows)
        raise SetupError(
            f'There is no row for {machine}/{compiler}; the rows are {names}.'
        )
    mpi = os.environ.get('POLARIS_MPI')
    if mpi and mpi != rows[0].mpi:
        raise SetupError(
            f'The loaded Polaris environment uses {mpi}, but the rows for '
            f'{machine}/{compiler} use {rows[0].mpi}.'
        )
    return rows


def _get_baseline_checkout(manifest, row, load_script, polaris_main):
    """
    Check the Polaris checkout the baseline is found or set up with, given
    by its load script or the settings' ``polaris_main``
    """
    baseline = manifest.baseline
    if load_script is None:
        if polaris_main is None:
            raise SetupError(
                f'The baseline runs with Polaris '
                f'{baseline.polaris_commit[:12]} (Polaris '
                f'{baseline.polaris_version}).  Set "polaris_main" in the '
                f'config file to a Polaris checkout at that commit, or pass '
                f'--baseline-load-script with its load script for '
                f'{row.machine}/{row.compiler}, or --no-baseline with the '
                f'reason if it cannot run.'
            )
        load_script = setup_tools.find_load_script(polaris_main, row)
    directory, compiler = setup_tools.read_load_script(load_script, row)
    polaris_hash = setup_tools.check_checkout(
        directory, baseline.polaris_commit, 'baseline Polaris commit'
    )
    if git_tools.is_ancestor(directory, manifest.pr_head, 'HEAD'):
        raise SetupError(
            f'The baseline Polaris checkout {directory} contains the PR '
            f'head {manifest.pr_head[:12]}.  Use a checkout at '
            f'{baseline.polaris_commit[:12]}.'
        )
    _check_pins(directory, baseline, f'The baseline checkout {directory}')
    return PolarisCheckout(
        directory, polaris_hash, compiler, os.path.abspath(load_script)
    )


def _check_pins(polaris_dir: str, side: PolarisSide, what: str) -> None:
    """Check that a checkout pins the Omega and E3SM commits of a side"""
    for path, expected in [
        (OMEGA_SUBMODULE, side.omega_commit),
        (E3SM_SUBMODULE, side.e3sm_commit),
    ]:
        pin = git_tools.submodule_pin(polaris_dir, 'HEAD', path)
        if pin != expected:
            raise SetupError(
                f'{what} pins {path} at {pin[:12]}, not {expected[:12]} '
                f'like Polaris {side.polaris_commit[:12]}.'
            )


def _prepare_omega(config, manifest: Manifest):
    """
    An Omega worktree of what the PR's Omega rows build, shared with other
    rows and PRs: the Omega the PR pins, or its merge with other Omega PRs,
    from the requester's E3SM fork
    """
    commit = manifest.omega_build_commit
    merge = manifest.omega_merge
    if merge is None:
        setup_tools.ensure_commit(config.omega_repo, OMEGA_URL, commit)
    elif not git_tools.has_commit(config.omega_repo, commit):
        git_tools.fetch(
            config.omega_repo,
            merge.fork,
            [f'refs/heads/{merge.branch}:{REF_PREFIX}/{merge.branch}'],
        )
    tree = os.path.join(config.work_base, 'omega', commit[:12])
    setup_tools.prepare_tree(config.omega_repo, commit, tree)
    return tree
