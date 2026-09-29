"""Helpers for the Omega PR testing utility's fixture repositories"""

import subprocess
from pathlib import Path


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
