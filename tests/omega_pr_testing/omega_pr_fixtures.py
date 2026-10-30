"""Helpers for the Omega PR testing utility's fixture repositories"""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import omega_pr_coupled
import omega_pr_init
import pr_test_git
import pr_test_github
import pr_test_setup
from pr_test_config import PrTestConfig

#: the CIME environment script the fixtures use
CIME_ENV = '/cime/load_latest_cime_env.sh'

#: coupled tests whose builds the fake create_test fails
FAILED_BUILDS = ['PEM_D.T62_oQU240.FAIL']


def git(path, *args):
    """Run git in a fixture repository and return its output"""
    result = subprocess.run(
        ['git', *args], cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def commit(path, filename, text, message):
    """Write a file in a fixture repository and commit it"""
    (Path(path) / filename).write_text(text, encoding='utf-8')
    git(path, 'add', filename)
    git(path, 'commit', '-q', '-m', message)
    return git(path, 'rev-parse', 'HEAD')


@dataclass
class Fixture:
    config: PrTestConfig
    polaris_dir: str
    fork: str
    pin: str
    develop: str
    pr_head: str
    extra_head: str
    conflict_head: str


def make_fixture(tmp_path, monkeypatch):
    """
    Local stand-ins for E3SM-Project/Omega, E3SM-Project/polaris, the
    requester's fork and the requester's Omega clone
    """
    omega = tmp_path / 'omega-work'
    (omega / 'components' / 'omega' / 'doc').mkdir(parents=True)
    git(omega, 'init', '-q')
    commit(omega, 'components/omega/doc/index.md', '# Omega\n', 'Add docs')
    pin = commit(omega, 'a.txt', 'a\n', 'Initial commit')
    develop = commit(omega, 'b.txt', 'b\n', 'Merge pull request #3')
    git(omega, 'branch', '-q', 'develop')
    git(omega, 'checkout', '-q', '-b', 'feature', develop)
    pr_head = commit(omega, 'c.txt', 'c\n', 'Add c')
    git(omega, 'checkout', '-q', '-b', 'fix', develop)
    extra_head = commit(omega, 'd.txt', 'd\n', 'Fix the build')
    git(omega, 'checkout', '-q', '-b', 'conflict', pin)
    conflict_head = commit(omega, 'b.txt', 'not b\n', 'Change b')

    upstream = tmp_path / 'omega.git'
    git(tmp_path, 'init', '-q', '--bare', str(upstream))
    git(
        omega,
        'push',
        '-q',
        str(upstream),
        'develop:refs/heads/develop',
        f'{pr_head}:refs/pull/5/head',
        f'{extra_head}:refs/pull/7/head',
        f'{conflict_head}:refs/pull/9/head',
    )

    polaris = tmp_path / 'polaris'
    polaris.mkdir()
    git(polaris, 'init', '-q')
    git(
        polaris,
        'update-index',
        '--add',
        '--cacheinfo',
        f'160000,{pin},e3sm_submodules/Omega',
    )
    git(polaris, 'commit', '-q', '-m', 'Pin Omega')
    polaris_upstream = tmp_path / 'polaris.git'
    git(tmp_path, 'init', '-q', '--bare', str(polaris_upstream))
    git(polaris, 'push', '-q', str(polaris_upstream), 'HEAD:refs/heads/main')

    fork = tmp_path / 'fork.git'
    git(tmp_path, 'init', '-q', '--bare', str(fork))
    clone = tmp_path / 'clone'
    git(tmp_path, 'clone', '-q', str(upstream), str(clone))

    monkeypatch.setattr(pr_test_git, 'OMEGA_URL', str(upstream))
    monkeypatch.setattr(pr_test_git, 'POLARIS_URL', str(polaris_upstream))
    mock_github(monkeypatch, pr_head)

    config = PrTestConfig(
        work_base=str(tmp_path / 'work'),
        omega_repo=str(clone),
        fork=str(fork),
    )
    return Fixture(
        config=config,
        polaris_dir=str(polaris),
        fork=str(fork),
        pin=pin,
        develop=develop,
        pr_head=pr_head,
        extra_head=extra_head,
        conflict_head=conflict_head,
    )


def mock_github(monkeypatch, head, state='OPEN'):
    def get_pull_request(repo, number):
        return {
            'state': state,
            'isDraft': False,
            'title': 'Add c',
            'url': f'https://github.com/E3SM-Project/Omega/pull/{number}',
            'headRefOid': head,
            'baseRefName': 'develop',
        }

    monkeypatch.setattr(pr_test_github, 'get_pull_request', get_pull_request)
    monkeypatch.setattr(pr_test_github, 'get_requester', lambda fork: 'tester')


def make_tester(tmp_path, monkeypatch):
    """
    A pushed test branch, a loaded chrysalis/intel environment, and stand-ins
    for polaris suite, the CTest utility and the scheduler
    """
    fixture = make_fixture(tmp_path, monkeypatch)
    manifest = omega_pr_init.initiate(
        config=fixture.config,
        pull_request=5,
        polaris_dir=fixture.polaris_dir,
        push=True,
    ).manifest
    monkeypatch.setenv('POLARIS_MACHINE', 'chrysalis')
    monkeypatch.setenv('POLARIS_COMPILER', 'intel')
    monkeypatch.setenv('POLARIS_MPI', 'openmpi')
    monkeypatch.setenv('POLARIS_BRANCH', fixture.polaris_dir)

    calls: dict[str, list] = {
        'suite': [],
        'submit': [],
        'extra_args': [],
        'submodules': [],
        'create_test': [],
    }
    monkeypatch.setattr(
        pr_test_setup, 'polaris_suite', _fake_polaris_suite(calls, fixture)
    )
    monkeypatch.setattr(pr_test_setup, 'set_up_ctests', _fake_ctests)
    # the fixture repositories have no submodules
    monkeypatch.setattr(pr_test_setup, 'OMEGA_SUBMODULES', [])
    monkeypatch.setattr(pr_test_setup, 'get_system', lambda machine: 'slurm')

    def submit_job(script, work_dir, system, dependency=None, extra_args=None):
        calls['submit'].append((work_dir, script, dependency))
        calls['extra_args'].append(extra_args)
        return str(1000 + len(calls['submit']))

    monkeypatch.setattr(pr_test_setup, 'submit_job', submit_job)

    def submit_case(job, dependency=None):
        calls['submit'].append((job.work_dir, job.script, dependency))
        calls['extra_args'].append(None)
        return str(1000 + len(calls['submit']))

    monkeypatch.setattr(pr_test_setup, 'submit_case', submit_case)
    monkeypatch.setattr(
        pr_test_setup,
        'init_all_submodules',
        lambda tree: calls['submodules'].append(tree),
    )
    monkeypatch.setattr(
        omega_pr_coupled, 'get_cime_env_script', lambda machine: CIME_ENV
    )
    monkeypatch.setattr(
        omega_pr_coupled, 'run_create_test', _fake_create_test(calls)
    )
    for module in [pr_test_setup, omega_pr_coupled]:
        monkeypatch.setattr(
            module, 'is_job_active', lambda job_id, system: False
        )
    return fixture, manifest, calls


def _fake_polaris_suite(calls, fixture):
    def polaris_suite(
        polaris_dir,
        suite,
        model,
        branch,
        build_dir,
        work_dir,
        baseline_work_dir=None,
        load_script=None,
        parallel=False,
    ):
        calls['suite'].append(
            {
                'polaris_dir': polaris_dir,
                'suite': suite,
                'model': model,
                'branch': branch,
                'build_dir': build_dir,
                'work_dir': work_dir,
                'baseline_work_dir': baseline_work_dir,
                'load_script': load_script,
                'parallel': parallel,
            }
        )
        omega_hash = git(branch, 'rev-parse', 'HEAD')
        polaris_hash = git(polaris_dir, 'rev-parse', 'HEAD')
        _make_build(Path(build_dir), omega_hash)
        _make_run(Path(work_dir), Path(build_dir), omega_hash, polaris_hash)

    return polaris_suite


def _fake_create_test(calls):
    def run_create_test(env_script, scripts_dir, args):
        calls['create_test'].append((env_script, scripts_dir, args))
        options = dict(zip(args[1:], args[2:], strict=False))
        tests = args[1 : args.index('--machine')]
        suffix = (
            f'{options["--machine"]}_{options["--compiler"]}.'
            f'{options["--test-id"]}'
        )
        for test in tests:
            case_dir = Path(options['--test-root']) / f'{test}.{suffix}'
            case_dir.mkdir(parents=True)
            status = 'FAIL' if test in FAILED_BUILDS else 'PASS'
            (case_dir / 'TestStatus').write_text(
                f'PASS {test}.{suffix} CREATE_NEWCASE\n'
                f'PASS {test}.{suffix} SHAREDLIB_BUILD\n'
                f'{status} {test}.{suffix} MODEL_BUILD time=60\n'
            )

    return run_create_test


def finish_coupled_tests(state, status='PASS'):
    """What the coupled tests' jobs add to their TestStatus files"""
    for case_dir in state.coupled_cases:
        path = Path(case_dir) / 'TestStatus'
        name = Path(case_dir).name
        path.write_text(
            f'{path.read_text()}PASS {name} SUBMIT\n'
            f'{status} {name} RUN time=30\n'
        )


def _fake_ctests(polaris_dir, row, build_dir, ctest_dir):
    os.makedirs(ctest_dir, exist_ok=True)
    return pr_test_setup.Job(
        name='CTests',
        work_dir=ctest_dir,
        script='build_omega/job_build_and_ctest_omega_chrysalis_intel.sh',
    )


def make_complete_baseline(work_dir, manifest, polaris_hash):
    build_dir = work_dir.parent / 'build'
    _make_build(build_dir, manifest.baseline_commit)
    _make_run(work_dir, build_dir, manifest.baseline_commit, polaris_hash)
    (work_dir / 'omega_pr_results.json').write_text(
        json.dumps({'complete': True, 'summary': {'failed': 0, 'pending': 0}})
    )
    return work_dir


def _make_build(build_dir, omega_hash):
    (build_dir / 'src').mkdir(parents=True, exist_ok=True)
    (build_dir / 'src' / 'omega.exe').write_bytes(b'')
    (build_dir / 'build_omega.log').write_text('')
    (build_dir / 'CMakeCache.txt').write_text(
        'OMEGA_BUILD_TYPE:UNINITIALIZED=Release\n'
        'OMEGA_CIME_COMPILER:UNINITIALIZED=intel\n'
        'OMEGA_CIME_MACHINE:UNINITIALIZED=chrysalis\n'
    )
    (build_dir / 'omega_source.txt').write_text(
        f'hash: {omega_hash}\ndescribe: omega\nclean_build: true\nlog:\n'
    )


def _make_run(work_dir, build_dir, omega_hash, polaris_hash):
    work_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        'polaris git version: polaris',
        f'polaris git hash: {polaris_hash}',
        'component git version: omega',
        f'component git hash: {omega_hash}',
        f'command: polaris suite -c ocean -t omega_pr -w {work_dir}',
        'machine: chrysalis',
        'compiler: intel',
        f'build directory: {build_dir}',
        'build type: Release',
        'tasks:',
    ]
    (work_dir / 'provenance').write_text('\n\n'.join(lines) + '\n')
    (work_dir / 'omega_pr.pickle').write_bytes(b'')
    (work_dir / 'job_script.omega_pr.sh').write_text('#!/bin/bash\n')
