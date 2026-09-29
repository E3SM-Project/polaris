"""
GitHub queries for the Omega PR testing utility, made with the ``gh`` CLI
"""

import json
import shutil
import subprocess
from typing import Any, Dict, List

from pr_test_manifest import UPSTREAM


class GitHubError(Exception):
    """``gh`` is missing or a query failed"""


def gh(args: List[str]) -> str:
    """
    Run a ``gh`` command and return its output

    Parameters
    ----------
    args : list of str
        The arguments to ``gh``

    Returns
    -------
    output : str
        The command's standard output
    """
    if shutil.which('gh') is None:
        raise GitHubError(
            'This step needs the GitHub CLI, gh, which is not on PATH.  '
            'Install it and run "gh auth login", or ask the requester to '
            'run this step.'
        )
    result = subprocess.run(['gh'] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitHubError(f'"gh {" ".join(args)}" failed:\n{result.stderr}')
    return result.stdout


def get_pull_request(number: int) -> Dict[str, Any]:
    """
    Get an Omega pull request's state, head and base

    Parameters
    ----------
    number : int
        The pull request number

    Returns
    -------
    pull_request : dict
        ``state``, ``isDraft``, ``title``, ``url``, ``headRefOid`` and
        ``baseRefName``
    """
    fields = 'state,isDraft,title,url,headRefOid,baseRefName'
    output = gh(
        ['pr', 'view', str(number), '-R', UPSTREAM, '--json', fields]
    )
    return json.loads(output)


def get_user() -> str:
    """The login of the authenticated GitHub user"""
    return gh(['api', 'user', '--jq', '.login']).strip()


def get_comment_bodies(number: int) -> List[str]:
    """The bodies of all comments on an Omega pull request, oldest first"""
    output = gh(
        [
            'api',
            '--paginate',
            f'repos/{UPSTREAM}/issues/{number}/comments',
            '--jq',
            '.[].body | @json',
        ]
    )
    return [json.loads(line) for line in output.splitlines() if line]


def post_comment(number: int, body_file: str) -> str:
    """
    Post a comment on an Omega pull request

    Parameters
    ----------
    number : int
        The pull request number

    body_file : str
        A file with the comment's body

    Returns
    -------
    url : str
        The URL of the new comment
    """
    output = gh(
        [
            'pr',
            'comment',
            str(number),
            '-R',
            UPSTREAM,
            '--body-file',
            body_file,
        ]
    )
    return output.strip()
