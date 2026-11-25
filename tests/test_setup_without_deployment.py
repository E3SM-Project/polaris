"""
Tests for setting up tasks outside a polaris deployment.

A deployed environment's load script exports ``POLARIS_LOAD_SCRIPT``,
``POLARIS_COMPILER`` and ``POLARIS_MPI``.  Polaris installed from
conda-forge has no load script, so setting up a task must not depend on
them, and building a model, which does, must say so.
"""

import pytest

from polaris import Component
from polaris.config import PolarisConfigParser
from polaris.setup import _check_build_environment, _get_compiler_and_mpi


@pytest.fixture
def no_deployment(monkeypatch):
    monkeypatch.delenv('POLARIS_COMPILER', raising=False)
    monkeypatch.delenv('POLARIS_MPI', raising=False)
    monkeypatch.delenv('POLARIS_LOAD_SCRIPT', raising=False)


def _config(**deploy):
    config = PolarisConfigParser()
    if deploy:
        config.add_section('deploy')
        for option, value in deploy.items():
            config.set('deploy', option, value)
    return config


def test_a_deployment_chooses_the_compiler_and_mpi(monkeypatch):
    monkeypatch.setenv('POLARIS_COMPILER', 'intel')
    monkeypatch.setenv('POLARIS_MPI', 'impi')
    config = _config(compiler='gnu', mpi_gnu='openmpi')

    assert _get_compiler_and_mpi(config) == ('intel', 'impi')


def test_without_a_deployment_the_machine_chooses(no_deployment):
    config = _config(compiler='gnu', mpi_gnu='openmpi', mpi_intel='impi')

    assert _get_compiler_and_mpi(config) == ('gnu', 'openmpi')


def test_without_a_deployment_or_a_machine_neither_is_chosen(no_deployment):
    assert _get_compiler_and_mpi(_config()) == (None, None)


def test_a_deployment_can_build_a_model(monkeypatch):
    monkeypatch.setenv('POLARIS_LOAD_SCRIPT', '/path/to/load_polaris.sh')

    _check_build_environment(Component(name='ocean'), _component_config())


def test_without_a_deployment_building_says_to_point_at_a_model(
    no_deployment,
):
    with pytest.raises(ValueError, match='--component_path'):
        _check_build_environment(Component(name='ocean'), _component_config())


def _component_config():
    config = PolarisConfigParser()
    config.add_section('paths')
    config.set('paths', 'component_path', '/no/model/here')
    return config
