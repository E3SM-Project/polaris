"""Helpers for the Omega PR testing utility's fixture repositories"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pr_test_git
import pr_test_github
import pr_test_init
from pr_test_config import PrTestConfig


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

    monkeypatch.setattr(pr_test_git, 'UPSTREAM_URL', str(upstream))
    monkeypatch.setattr(pr_test_init, 'POLARIS_URL', str(polaris_upstream))
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
    def get_pull_request(number):
        return {
            'state': state,
            'isDraft': False,
            'title': 'Add c',
            'url': f'https://github.com/E3SM-Project/Omega/pull/{number}',
            'headRefOid': head,
            'baseRefName': 'develop',
        }

    monkeypatch.setattr(pr_test_github, 'get_pull_request', get_pull_request)
    monkeypatch.setattr(pr_test_github, 'get_user', lambda: 'tester')
