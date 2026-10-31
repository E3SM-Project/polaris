"""
The tester's setup: check the environment against the manifest, find or
set up a baseline, set up the PR suite and CTests, and submit or print the
jobs
"""

import os
from dataclasses import asdict
from typing import List, Optional

import pr_test_git as git_tools
import pr_test_setup as setup_tools
from omega_pr_coupled import COUPLED_TESTS, set_up_coupled_tests
from omega_pr_manifest import POLARIS_SUBMODULE, Manifest, fetch_manifest
from pr_test_config import PrTestConfig
from pr_test_git import OMEGA_SUBMODULE, POLARIS_DIR
from pr_test_rows import Row
from pr_test_setup import (
    BUILD_TYPE,
    Baseline,
    Job,
    PolarisCheckout,
    SetupError,
    SetupState,
)

from polaris.baselines import BaselineCriteria

SUITE = 'omega_pr'

MODEL = 'omega'


def run_setup(
    config: PrTestConfig,
    fork: str,
    branch: str,
    submit: bool = False,
    baseline_dir: Optional[str] = None,
    baseline_load_script: Optional[str] = None,
    no_baseline: Optional[str] = None,
    parallel: bool = False,
    coupled_tests: Optional[List[str]] = None,
    polaris_dir: str = POLARIS_DIR,
) -> SetupState:
    """
    Set up the baseline, PR suite, CTests and coupled CIME tests for this
    machine's row

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

    no_baseline : str, optional
        Why the PR suite runs without a baseline, for a row where the
        baseline commit cannot run

    parallel : bool, optional
        Whether the PR suite, and a baseline that is set up here, run their
        steps at the same time with ``polaris parallel``

    coupled_tests : list of str, optional
        The coupled CIME tests to run, without the machine and compiler,
        instead of ``COUPLED_TESTS``

    polaris_dir : str, optional
        The Polaris checkout the loaded environment runs

    Returns
    -------
    state : pr_test_setup.SetupState
        What setup did
    """
    if no_baseline is not None and (
        baseline_dir is not None or baseline_load_script is not None
    ):
        raise SetupError(
            '--no-baseline cannot be used with --baseline-dir or '
            '--baseline-load-script.'
        )
    manifest = fetch_manifest(config.omega_repo, fork, branch)
    setup_tools.check_env_checkout(polaris_dir)
    row = setup_tools.get_env_row(manifest.rows)
    polaris_hash = setup_tools.check_checkout(
        polaris_dir, manifest.polaris_commit, 'Polaris commit'
    )
    baseline_polaris = None
    if no_baseline is None:
        baseline_polaris = _get_baseline_polaris(
            manifest, row, polaris_dir, baseline_load_script, config
        )

    run_dir = get_row_dir(config, manifest, row)
    pr_work_dir = os.path.join(run_dir, SUITE)
    # resume first: a refused job may still need submitting after the
    # suites that were submitted before it have run
    previous = setup_tools.read_submitted_state(run_dir)
    if previous is not None:
        return setup_tools.resume(previous, row.machine, run_dir, submit)
    if os.path.exists(os.path.join(pr_work_dir, f'{SUITE}_results.json')):
        raise SetupError(
            f'The PR suite in {pr_work_dir} has already run.  Remove '
            f'{run_dir} to test this row again.'
        )

    omega_dir = os.path.join(config.work_base, 'omega')
    test_tree = os.path.join(omega_dir, manifest.test_commit[:12])
    setup_tools.prepare_tree(
        config.omega_repo, manifest.test_commit, test_tree
    )

    jobs = []
    baseline: Optional[Baseline] = None
    baseline_build_log = None
    if baseline_polaris is not None:
        criteria = BaselineCriteria(
            machine=row.machine,
            compiler=baseline_polaris.compiler,
            build_type=BUILD_TYPE,
            component_hash=manifest.baseline_commit,
            polaris_hash=baseline_polaris.hash,
            suite=SUITE,
        )
        roots = [
            os.path.join(config.work_base, 'baselines')
        ] + config.baseline_search_roots
        baseline = setup_tools.get_baseline(
            config,
            criteria,
            roots,
            baseline_dir,
            baseline_polaris,
            MODEL,
            parallel=parallel,
        )
        if baseline.job is not None:
            jobs.append(baseline.job)
        baseline_build_log = setup_tools.get_baseline_build_log(
            criteria, roots, baseline.work_dir
        )

    pr_build_dir = os.path.join(run_dir, 'build')
    setup_tools.polaris_suite(
        polaris_dir,
        suite=SUITE,
        model=MODEL,
        branch=test_tree,
        build_dir=pr_build_dir,
        work_dir=pr_work_dir,
        baseline_work_dir=None if baseline is None else baseline.work_dir,
        parallel=parallel,
    )
    jobs.append(
        Job(
            name='PR suite',
            work_dir=pr_work_dir,
            script=f'job_script.{SUITE}.sh',
            depends_on_baseline=baseline is not None,
        )
    )

    ctest_dir = os.path.join(run_dir, 'ctest')
    jobs.append(
        setup_tools.set_up_ctests(polaris_dir, row, pr_build_dir, ctest_dir)
    )

    setup_tools.init_all_submodules(test_tree)
    coupled_cases, coupled_jobs = set_up_coupled_tests(
        row,
        test_tree,
        os.path.join(run_dir, 'coupled'),
        manifest.run_name,
        COUPLED_TESTS if coupled_tests is None else coupled_tests,
    )
    jobs.extend(coupled_jobs)

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
        coupled_cases=coupled_cases,
    )
    if baseline_polaris is not None and baseline_polaris.hash != polaris_hash:
        state.baseline_polaris_hash = baseline_polaris.hash

    state.jobs = [asdict(job) for job in jobs]
    setup_tools.write_state(run_dir, state)
    if submit:
        setup_tools.submit_jobs(state, jobs, row.machine, run_dir)
    return state


def get_run_dir(config: PrTestConfig, manifest: Manifest) -> str:
    """The directory this machine's runs for a manifest go in"""
    return os.path.join(config.work_base, manifest.run_name)


def get_row_dir(config: PrTestConfig, manifest: Manifest, row: Row) -> str:
    """The directory a row's runs go in"""
    return os.path.join(
        get_run_dir(config, manifest), f'{row.machine}_{row.compiler}'
    )


def _get_baseline_polaris(manifest, row, polaris_dir, load_script, config):
    """
    Check the Polaris checkout the baseline is found or set up with: this
    one, or a second one, given by its load script or the settings'
    ``polaris_main``
    """
    separate = manifest.baseline_polaris_commit != manifest.polaris_commit
    if load_script is None and separate:
        if config.polaris_main is None:
            raise SetupError(
                f'The baseline runs with Polaris '
                f'{manifest.baseline_polaris_commit[:12]}, without the '
                f"changes in the manifest's Polaris commit "
                f'{manifest.polaris_commit[:12]}.  Set "polaris_main" in '
                f'the config file to a Polaris checkout at that commit, or '
                f'pass --baseline-load-script with its load script for '
                f'{row.name}.'
            )
        load_script = setup_tools.find_load_script(config.polaris_main, row)
    if load_script is None:
        checkout = PolarisCheckout(
            polaris_dir, git_tools.rev_parse(polaris_dir, 'HEAD'), row.compiler
        )
    else:
        directory, compiler = setup_tools.read_load_script(load_script, row)
        polaris_hash = setup_tools.check_checkout(
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
        checkout = PolarisCheckout(
            directory, polaris_hash, compiler, os.path.abspath(load_script)
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
