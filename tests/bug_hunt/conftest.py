import subprocess
import sys
from pathlib import Path

import pytest

UTILS_DIR = Path(__file__).resolve().parents[2] / 'utils'

# the utility's modules and the ones it shares import each other by name, as
# they do when the script runs
UTILITY_DIRS = [UTILS_DIR / 'pr_testing', UTILS_DIR / 'bug_hunt']
for directory in UTILITY_DIRS:
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

#: the saved CDash responses and other fixture files
DATA_DIR = Path(__file__).resolve().parent / 'data'

#: git config the fixture repositories need, as ``GIT_CONFIG_*`` variables
GIT_CONFIG = {
    'user.name': 'Polaris Test',
    'user.email': 'test@example.com',
    'commit.gpgsign': 'false',
    'init.defaultBranch': 'main',
}


@pytest.fixture(autouse=True)
def git_config(monkeypatch):
    """Keep the fixture repositories independent of the developer's config"""
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', '/dev/null')
    monkeypatch.setenv('GIT_CONFIG_COUNT', str(len(GIT_CONFIG)))
    for index, (key, value) in enumerate(GIT_CONFIG.items()):
        monkeypatch.setenv(f'GIT_CONFIG_KEY_{index}', key)
        monkeypatch.setenv(f'GIT_CONFIG_VALUE_{index}', value)


@pytest.fixture
def ledger_dir(tmp_path):
    """An empty ledger repository with no remote"""
    path = tmp_path / 'ledger'
    path.mkdir()
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(
        ['git', '-C', str(path), 'commit', '-q', '--allow-empty', '-m', 'x'],
        check=True,
    )
    return path
