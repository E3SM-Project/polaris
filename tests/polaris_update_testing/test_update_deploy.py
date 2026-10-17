import shlex
import subprocess
from pathlib import Path

import polaris_update_deploy
import pytest
from pr_test_rows import Row
from update_fixtures import (
    SHARED_SPACK,
    SHARED_VIEW,
    make_tester,
    write_load_script,
)

SHARED_PATH = f'{SHARED_SPACK}/dev_polaris_1.2.0'


@pytest.fixture
def tester(tmp_path, monkeypatch):
    return make_tester(tmp_path, monkeypatch)


def test_deploy_command(tester):
    fixture, manifest, _ = tester
    (deployment,) = _deploy(fixture, manifest, 'aurora')

    # aurora's config also lists intelgpu, which the PR does not support
    assert deployment.command == [
        './deploy.py',
        '--deploy-spack',
        '--machine',
        'aurora',
        '--compiler',
        'intel',
        '--mpi',
        'mpich',
    ]
    assert polaris_update_deploy.get_deploy_command(
        'pm-gpu',
        [Row('pm-gpu', 'gnugpu', 'mpich', model='omega')],
        spack_path='/test/spack',
        recreate=True,
    )[-6:] == [
        'gnugpu',
        '--mpi',
        'mpich',
        '--spack-path',
        '/test/spack',
        '--recreate',
    ]


def test_deploy_command_supported_compilers(tester):
    fixture, manifest, _ = tester

    # chrysalis/gnu has two rows, but is deployed once
    (deployment,) = _deploy(fixture, manifest, 'chrysalis')

    assert deployment.command[4:] == [
        '--compiler',
        'gnu',
        'intel',
        '--mpi',
        'openmpi',
        'openmpi',
    ]


def test_deploy_without_run(tester, monkeypatch):
    fixture, manifest, _ = tester
    ran = _mock_run(monkeypatch)

    (deployment,) = _deploy(fixture, manifest, 'chrysalis')

    assert not deployment.ran
    assert ran == []
    assert deployment.spack_path == SHARED_PATH
    assert deployment.missing == ['chrysalis/gnu', 'chrysalis/intel']
    text = polaris_update_deploy.format_deployments(
        [deployment], fixture.polaris_dir
    )
    assert "With the requester's permission, run deploy again with --run" in (
        text
    )
    assert './deploy.py --deploy-spack --machine chrysalis' in text


def test_deploy_run(tester, monkeypatch):
    fixture, manifest, _ = tester
    ran = _mock_run(monkeypatch)
    write_load_script(
        Path(fixture.polaris_dir) / 'load_polaris_chrysalis_gnu_openmpi.sh',
        fixture.polaris_dir,
    )

    (deployment,) = _deploy(fixture, manifest, 'chrysalis', run=True)

    assert deployment.ran
    assert ran == [
        (
            f'cd {fixture.polaris_dir} && {shlex.join(deployment.command)}',
            fixture.polaris_dir,
        )
    ]
    assert Path(deployment.log).name == 'deploy_chrysalis.log'
    # the intel rows still need a load script that uses the deployment
    assert deployment.missing == ['chrysalis/intel']


def test_deploy_test_environments(tester, monkeypatch):
    fixture, manifest, _ = tester
    _mock_run(monkeypatch)
    # a load script that uses the shared environments is not one for a test
    # deployment
    write_load_script(
        Path(fixture.polaris_dir) / 'load_polaris_chrysalis_gnu_openmpi.sh',
        fixture.polaris_dir,
    )

    (deployment,) = _deploy(
        fixture, manifest, 'chrysalis', spack_path='/test/spack', run=True
    )

    assert deployment.spack_path == '/test/spack'
    assert deployment.command[-2:] == ['--spack-path', '/test/spack']
    assert deployment.missing == ['chrysalis/gnu', 'chrysalis/intel']


def test_deploy_perlmutter(tester, monkeypatch):
    fixture, manifest, _ = tester
    _mock_run(monkeypatch)

    deployments = _deploy(fixture, manifest, 'pm-gpu')

    assert [deployment.machine for deployment in deployments] == [
        'pm-cpu',
        'pm-gpu',
    ]


def test_deploy_failure(tester, monkeypatch):
    fixture, manifest, _ = tester
    _mock_run(monkeypatch, returncode=1)

    with pytest.raises(polaris_update_deploy.DeployError, match='failed'):
        _deploy(fixture, manifest, 'chrysalis', run=True)


def test_spack_kind(tester):
    fixture, _, _ = tester
    polaris_dir = fixture.polaris_dir

    assert (
        polaris_update_deploy.get_spack_kind(
            polaris_dir, 'chrysalis', SHARED_VIEW
        )
        == 'shared'
    )
    assert (
        polaris_update_deploy.get_spack_kind(
            polaris_dir, 'chrysalis', '/test/spack/var/spack/environments/x'
        )
        == 'test'
    )
    assert polaris_update_deploy.get_spack_path(SHARED_VIEW) == SHARED_PATH


def test_read_environment(tester, monkeypatch):
    fixture, _, _ = tester

    environment = polaris_update_deploy.read_environment(
        fixture.polaris_dir, 'chrysalis'
    )

    assert environment['spack'] == 'shared'
    assert environment['spack_path'] == SHARED_PATH
    assert environment['polaris_version'] == '1.2.0-alpha.1'
    assert environment['mache_version']

    monkeypatch.delenv('MACHE_DEPLOY_SPACK_LIBRARY_VIEW')
    with pytest.raises(polaris_update_deploy.DeployError, match='no Spack'):
        polaris_update_deploy.read_environment(
            fixture.polaris_dir, 'chrysalis'
        )


def _deploy(fixture, manifest, machine, **kwargs):
    return polaris_update_deploy.run_deploy(
        config=fixture.config,
        fork=fixture.fork,
        branch=manifest.branch,
        machine=machine,
        polaris_dir=fixture.polaris_dir,
        **kwargs,
    )


def _mock_run(monkeypatch, returncode=0):
    """A stand-in for running ./deploy.py; git still runs"""
    ran = []
    original = subprocess.run

    def run(command, *args, **kwargs):
        if command[:3] != ['/bin/bash', '-l', '-c']:
            return original(command, *args, **kwargs)
        # a clean login shell, with none of the loaded environment
        assert 'POLARIS_MACHINE' not in kwargs['env']
        ran.append((command[3], kwargs['cwd']))
        return subprocess.CompletedProcess(command, returncode)

    monkeypatch.setattr(subprocess, 'run', run)
    return ran
