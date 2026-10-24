"""Fixture repositories and stand-ins for the version update utility"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import polaris_update_init
import pr_test_git
import pr_test_github
import pr_test_setup
from pr_test_config import PrTestConfig

#: the shared Spack path in the fixture machine configs
SHARED_SPACK = '/shared/spack'

#: a Spack view in the new version's shared environments
SHARED_VIEW = (
    f'{SHARED_SPACK}/dev_polaris_1.2.0/var/spack/environments/'
    f'dev_polaris_1_2_0_gnu_openmpi/.spack-env/view'
)

#: the E3SM commit both Polaris commits pin
E3SM_PIN = 'e' * 40

OLD_TABLE = """machines:
  - name: chrysalis
    models:
      - model: MPAS
        compiler: gnu
        mpi: openmpi
        mpas_target: gfortran
      - model: Omega
        compiler: gnu
        mpi: openmpi
        mpas_target: null
"""

NEW_TABLE = """machines:
  - name: aurora
    models:
      - model: Omega
        compiler: intel
        mpi: mpich
        mpas_target: null
  - name: chrysalis
    models:
      - model: MPAS
        compiler: gnu
        mpi: openmpi
        mpas_target: gfortran
      - model: Omega
        compiler: intel
        mpi: openmpi
        mpas_target: null
      - model: Omega
        compiler: gnu
        mpi: openmpi
        mpas_target: null
      - model: Omega
        compiler: null
        mpi: openmpi
        mpas_target: null
  - name: pm-cpu
    models:
      - model: Omega
        compiler: gnu
        mpi: mpich
        mpas_target: null
  - name: pm-gpu
    models:
      - model: Omega
        compiler: gnugpu
        mpi: mpich
        mpas_target: null
"""

MACHINE_CONFIGS = {
    'aurora': {'mpi_intel': 'mpich', 'mpi_intelgpu': 'mpich'},
    'chrysalis': {'mpi_intel': 'openmpi', 'mpi_gnu': 'openmpi'},
    'pm-cpu': {'mpi_gnu': 'mpich', 'mpi_intel': 'mpich'},
    'pm-gpu': {'mpi_gnugpu': 'mpich'},
}


def git(path, *args):
    """Run git in a fixture repository and return its output"""
    result = subprocess.run(
        ['git', *args], cwd=path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@dataclass
class Fixture:
    config: PrTestConfig
    polaris_dir: str
    baseline_dir: str
    fork: str
    main: str
    pr_head: str
    old_pin: str
    new_pin: str
    fix_head: str
    e3sm_fork: str


def make_fixture(tmp_path, monkeypatch):
    """
    Local stand-ins for E3SM-Project/polaris with a version update PR,
    E3SM-Project/Omega, the requester's Polaris fork, and Polaris checkouts
    of the PR and of main
    """
    omega = tmp_path / 'omega-work'
    omega.mkdir()
    git(omega, 'init', '-q')
    old_pin = _commit(omega, {'a.txt': 'a\n'}, 'Initial commit')
    new_pin = _commit(omega, {'b.txt': 'b\n'}, 'Merge pull request #3')
    # a fix still in review, made before the PR's Omega
    git(omega, 'checkout', '-q', '-b', 'fix', old_pin)
    fix_head = _commit(omega, {'fix.txt': 'fix\n'}, 'Set MPILIB')
    omega_upstream = tmp_path / 'omega.git'
    git(tmp_path, 'init', '-q', '--bare', str(omega_upstream))
    git(
        omega,
        'push',
        '-q',
        str(omega_upstream),
        f'{new_pin}:refs/heads/develop',
        f'{fix_head}:refs/pull/600/head',
        f'{old_pin}:refs/pull/601/head',
    )
    omega_clone = tmp_path / 'omega'
    git(tmp_path, 'clone', '-q', str(omega_upstream), str(omega_clone))

    work = tmp_path / 'polaris-work'
    work.mkdir()
    git(work, 'init', '-q')
    files = {
        'polaris/version.py': "__version__ = '1.1.0-alpha.7'\n",
        'docs/developers_guide/supported_machines.yaml': OLD_TABLE,
    }
    for machine, options in MACHINE_CONFIGS.items():
        lines = ['[deploy]', f'spack = {SHARED_SPACK}']
        lines += [f'{option} = {value}' for option, value in options.items()]
        files[f'polaris/machines/{machine}.cfg'] = '\n'.join(lines) + '\n'
    main = _commit(work, files, 'Polaris 1.1.0-alpha.7', old_pin)
    pr_head = _commit(
        work,
        {
            'polaris/version.py': "__version__ = '1.2.0-alpha.1'\n",
            'docs/developers_guide/supported_machines.yaml': NEW_TABLE,
        },
        'Update to 1.2.0-alpha.1',
        new_pin,
    )
    upstream = tmp_path / 'polaris.git'
    git(tmp_path, 'init', '-q', '--bare', str(upstream))
    git(
        work,
        'push',
        '-q',
        str(upstream),
        f'{main}:refs/heads/main',
        f'{pr_head}:refs/pull/835/head',
    )

    polaris_dir = tmp_path / 'polaris'
    git(tmp_path, 'clone', '-q', str(upstream), str(polaris_dir))
    git(polaris_dir, 'fetch', '-q', 'origin', 'refs/pull/835/head:update')
    git(polaris_dir, 'checkout', '-q', 'update')
    baseline_dir = tmp_path / 'polaris-main'
    git(tmp_path, 'clone', '-q', str(upstream), str(baseline_dir))

    fork = tmp_path / 'fork.git'
    git(tmp_path, 'init', '-q', '--bare', str(fork))
    e3sm_fork = tmp_path / 'e3sm-fork.git'
    git(tmp_path, 'init', '-q', '--bare', str(e3sm_fork))

    monkeypatch.setattr(pr_test_git, 'OMEGA_URL', str(omega_upstream))
    monkeypatch.setattr(pr_test_git, 'POLARIS_URL', str(upstream))
    mock_github(monkeypatch, pr_head)

    config = PrTestConfig(
        work_base=str(tmp_path / 'work'),
        omega_repo=str(omega_clone),
        fork=str(e3sm_fork),
        polaris_fork=str(fork),
    )
    return Fixture(
        config=config,
        polaris_dir=str(polaris_dir),
        baseline_dir=str(baseline_dir),
        fork=str(fork),
        main=main,
        pr_head=pr_head,
        old_pin=old_pin,
        new_pin=new_pin,
        fix_head=fix_head,
        e3sm_fork=str(e3sm_fork),
    )


def mock_github(monkeypatch, head, state='OPEN'):
    def get_pull_request(repo, number):
        assert repo == 'E3SM-Project/polaris'
        return {
            'state': state,
            'isDraft': False,
            'title': 'Update to 1.2.0-alpha.1',
            'url': f'https://github.com/{repo}/pull/{number}',
            'headRefOid': head,
            'baseRefName': 'main',
        }

    monkeypatch.setattr(pr_test_github, 'get_pull_request', get_pull_request)
    monkeypatch.setattr(pr_test_github, 'get_requester', lambda fork: 'tester')


def make_tester(tmp_path, monkeypatch, baseline='main', merge_omega_prs=()):
    """
    A pushed test branch, a loaded chrysalis/gnu environment with the
    shared Spack environments, and stand-ins for polaris suite, the CTest
    utility and the scheduler
    """
    fixture = make_fixture(tmp_path, monkeypatch)
    manifest = polaris_update_init.initiate(
        config=fixture.config,
        pull_request=835,
        baseline_ref=baseline,
        merge_omega_prs=merge_omega_prs,
        push=True,
        polaris_dir=fixture.polaris_dir,
    ).manifest
    load_env(monkeypatch, fixture, 'chrysalis', 'gnu', 'openmpi')

    calls: dict[str, list] = {'suite': [], 'submit': []}
    monkeypatch.setattr(pr_test_setup, 'polaris_suite', _fake_suite(calls))
    monkeypatch.setattr(pr_test_setup, 'set_up_ctests', _fake_ctests)
    # the fixture repositories have no submodules
    monkeypatch.setattr(pr_test_setup, 'OMEGA_SUBMODULES', [])
    monkeypatch.setattr(pr_test_setup, 'get_system', lambda machine: 'slurm')

    def submit_job(script, work_dir, system, dependency=None, extra_args=None):
        calls['submit'].append((work_dir, script, dependency))
        return str(1000 + len(calls['submit']))

    monkeypatch.setattr(pr_test_setup, 'submit_job', submit_job)
    monkeypatch.setattr(
        pr_test_setup, 'is_job_active', lambda job_id, system: False
    )
    return fixture, manifest, calls


def load_env(monkeypatch, fixture, machine, compiler, mpi, view=SHARED_VIEW):
    """What sourcing a load script of the PR's checkout sets"""
    monkeypatch.setenv('POLARIS_MACHINE', machine)
    monkeypatch.setenv('POLARIS_COMPILER', compiler)
    monkeypatch.setenv('POLARIS_MPI', mpi)
    monkeypatch.setenv('POLARIS_BRANCH', fixture.polaris_dir)
    monkeypatch.setenv('POLARIS_VERSION', '1.2.0-alpha.1')
    monkeypatch.setenv('MACHE_DEPLOY_SPACK_LIBRARY_VIEW', view)


def write_load_script(
    path, polaris_dir, machine='chrysalis', compiler='gnu', mpi='openmpi'
):
    """The exports of a load script for a checkout"""
    path.write_text(
        f'export POLARIS_MACHINE="{machine}"\n'
        f'export POLARIS_BRANCH="{polaris_dir}"\n'
        f'export POLARIS_COMPILER="{compiler}"\n'
        f'export POLARIS_MPI="{mpi}"\n'
        f'export MACHE_DEPLOY_SPACK_LIBRARY_VIEW="{SHARED_VIEW}"\n'
    )
    return str(path)


def _commit(path, files, message, omega_pin=None):
    """Write files in a fixture repository, pin submodules and commit"""
    for filename, text in files.items():
        (Path(path) / filename).parent.mkdir(parents=True, exist_ok=True)
        (Path(path) / filename).write_text(text, encoding='utf-8')
        git(path, 'add', filename)
    if omega_pin is not None:
        for submodule, pin in [
            ('e3sm_submodules/Omega', omega_pin),
            ('e3sm_submodules/E3SM-Project', E3SM_PIN),
        ]:
            git(
                path,
                'update-index',
                '--add',
                '--cacheinfo',
                f'160000,{pin},{submodule}',
            )
    git(path, 'commit', '-q', '-m', message)
    return git(path, 'rev-parse', 'HEAD')


def _fake_suite(calls):
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
        os.makedirs(work_dir, exist_ok=True)
        Path(work_dir, f'{suite}.pickle').write_bytes(b'')
        os.makedirs(build_dir, exist_ok=True)

    return polaris_suite


def _fake_ctests(polaris_dir, row, build_dir, ctest_dir):
    os.makedirs(ctest_dir, exist_ok=True)
    return pr_test_setup.Job(
        name='CTests',
        work_dir=ctest_dir,
        script=f'build_omega/job_build_and_ctest_omega_{row.machine}_'
        f'{row.compiler}.sh',
    )
