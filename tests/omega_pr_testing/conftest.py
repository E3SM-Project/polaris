import sys
from pathlib import Path

import pytest

UTILITY_DIR = (
    Path(__file__).resolve().parents[2] / 'utils' / 'omega' / 'pr_testing'
)

# the utility's modules import each other by name, as they do when the
# script runs
if str(UTILITY_DIR) not in sys.path:
    sys.path.insert(0, str(UTILITY_DIR))

#: git config the fixture repositories need, as ``GIT_CONFIG_*`` variables
GIT_CONFIG = {
    'protocol.file.allow': 'always',
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
