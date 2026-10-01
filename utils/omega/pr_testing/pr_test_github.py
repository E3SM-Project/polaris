"""
GitHub queries for the Omega PR testing utility.  They use the ``gh`` CLI
when it is installed and logged in, and otherwise GitHub's REST API, which
needs no login for a public repository.  Only posting a comment needs
``gh``.
"""

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pr_test_manifest import UPSTREAM

API_URL = 'https://api.github.com'

_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')

_FORK_OWNER = re.compile(r'github\.com[:/]([^/]+)/')


class GitHubError(Exception):
    """A query failed, or a comment cannot be posted without ``gh``"""


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
        raise GitHubError('The GitHub CLI, gh, is not on PATH.')
    result = subprocess.run(['gh'] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitHubError(f'"gh {" ".join(args)}" failed:\n{result.stderr}')
    return result.stdout


@lru_cache(maxsize=None)
def gh_usable() -> bool:
    """Whether ``gh`` is installed and logged in"""
    if shutil.which('gh') is None:
        return False
    result = subprocess.run(
        ['gh', 'auth', 'status'], capture_output=True, text=True
    )
    return result.returncode == 0


def api_get(path: str) -> List[Any]:
    """
    Get a GitHub REST API path without ``gh``, following pages

    A token in ``GH_TOKEN`` or ``GITHUB_TOKEN`` is used if one is set,
    which raises the rate limit; none is needed for a public repository.

    Parameters
    ----------
    path : str
        The path below the API's URL, with any query

    Returns
    -------
    pages : list
        The decoded JSON of each page, in order
    """
    url: Optional[str] = f'{API_URL}/{path}'
    headers = {'Accept': 'application/vnd.github+json'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = f'Bearer {token}'
    pages = []
    while url is not None:
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                pages.append(json.loads(response.read().decode('utf-8')))
                link = response.headers.get('Link', '')
        except urllib.error.HTTPError as exc:
            raise GitHubError(
                f'GitHub API request {url} failed: {exc.code} {exc.reason}.'
                f'  If it is a rate limit, wait or set GH_TOKEN.'
            ) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(
                f'GitHub API request {url} failed: {exc.reason}'
            ) from exc
        match = _NEXT_LINK.search(link)
        url = match.group(1) if match else None
    return pages


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
    if gh_usable():
        fields = 'state,isDraft,title,url,headRefOid,baseRefName'
        output = gh(
            ['pr', 'view', str(number), '-R', UPSTREAM, '--json', fields]
        )
        return json.loads(output)

    (pr,) = api_get(f'repos/{UPSTREAM}/pulls/{number}')
    if pr['state'] == 'open':
        state = 'OPEN'
    elif pr.get('merged_at'):
        state = 'MERGED'
    else:
        state = 'CLOSED'
    return {
        'state': state,
        'isDraft': pr['draft'],
        'title': pr['title'],
        'url': pr['html_url'],
        'headRefOid': pr['head']['sha'],
        'baseRefName': pr['base']['ref'],
    }


def get_user() -> str:
    """The login of the GitHub user ``gh`` is logged in as"""
    return gh(['api', 'user', '--jq', '.login']).strip()


def get_requester(fork: Optional[str]) -> str:
    """
    The requester's GitHub user: the owner of their fork, or the user
    ``gh`` is logged in as

    Parameters
    ----------
    fork : str, optional
        The URL of the requester's fork

    Returns
    -------
    user : str
        The GitHub user
    """
    match = _FORK_OWNER.search(fork or '')
    if match is not None:
        return match.group(1)
    if gh_usable():
        return get_user()
    raise GitHubError(
        'The requester comes from "fork" in the config file, or from gh '
        'when it is logged in, and neither is available.'
    )


def get_comment_bodies(number: int) -> List[str]:
    """The bodies of all comments on an Omega pull request, oldest first"""
    if not gh_usable():
        pages = api_get(
            f'repos/{UPSTREAM}/issues/{number}/comments?per_page=100'
        )
        return [comment['body'] for page in pages for comment in page]
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
    Post a comment on an Omega pull request, which needs ``gh``, logged in

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
    if not gh_usable():
        raise GitHubError(
            f'Posting needs gh, logged in, which is not available here, so '
            f'nothing was posted.  The comment is in {body_file}; post it '
            f'on {UPSTREAM}#{number} by hand.'
        )
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


def get_check_runs(sha: str) -> List[Dict[str, Any]]:
    """
    The check runs on a commit of E3SM-Project/Omega

    Parameters
    ----------
    sha : str
        The commit

    Returns
    -------
    check_runs : list of dict
        Each run's ``name``, ``status``, ``conclusion``, ``id`` and
        ``html_url``
    """
    keys = ['name', 'status', 'conclusion', 'id', 'html_url']
    if not gh_usable():
        pages = api_get(
            f'repos/{UPSTREAM}/commits/{sha}/check-runs?per_page=100'
        )
        return [
            {key: run[key] for key in keys}
            for page in pages
            for run in page['check_runs']
        ]
    output = gh(
        [
            'api',
            '--paginate',
            f'repos/{UPSTREAM}/commits/{sha}/check-runs',
            '--jq',
            '.check_runs[] | {name, status, conclusion, id, html_url} '
            '| @json',
        ]
    )
    return [json.loads(line) for line in output.splitlines() if line]


def get_job_steps(job_id: int) -> List[Dict[str, Any]]:
    """
    The steps of a GitHub Actions job, whose id is that of its check run

    Parameters
    ----------
    job_id : int
        The job

    Returns
    -------
    steps : list of dict
        Each step's ``name`` and ``conclusion``
    """
    if not gh_usable():
        (job,) = api_get(f'repos/{UPSTREAM}/actions/jobs/{job_id}')
        return [
            {'name': step['name'], 'conclusion': step['conclusion']}
            for step in job['steps']
        ]
    output = gh(
        [
            'api',
            f'repos/{UPSTREAM}/actions/jobs/{job_id}',
            '--jq',
            '.steps[] | {name, conclusion} | @json',
        ]
    )
    return [json.loads(line) for line in output.splitlines() if line]
