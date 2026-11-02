"""
Matching findings against what is already known: open issues and pull
requests in Omega and Polaris, and issues closed lately
"""

import datetime
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from bug_hunt_keys import is_cime_name
from bug_hunt_ledger import Finding, Key
from pr_test_github import GitHubError, api_get, gh, gh_usable

#: the repositories searched for issues and pull requests
REPOS = ('E3SM-Project/Omega', 'E3SM-Project/polaris')

#: how far back closed issues are searched, since a match means the bug is
#: back
CLOSED_DAYS = 90

#: the most results kept from each search
MAX_RESULTS = 10

#: the most identifiers from a claim that are searched for
MAX_IDENTIFIERS = 6

#: the longest a search waits for GitHub's search rate limit to reset, in
#: seconds
MAX_RATE_LIMIT_WAIT = 120

#: identifiers that stand for a family, which issues name by its best-known
#: member: an issue about loops that ignore the minimum layer index names
#: ``MinLayerCell``, whichever of the edge or vertex variants a finding
#: names.  Keep this short, and add a family only when a missed duplicate
#: shows one: the defense against general issues is a review that starts
#: from the open issues, and the agent's judgment, not this list
IDENTIFIER_FAMILIES = (
    (re.compile(r'^MinLayer\w+$'), 'MinLayerCell'),
    (re.compile(r'^MaxLayer\w+$'), 'MaxLayerCell'),
)

#: an identifier in a claim: a name in backticks, a CamelCase name with a
#: lower-case letter after its first, or a name with an underscore
_IDENTIFIER = re.compile(
    r'`([^`\s]+)`|\b([A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+)\b'
    r'|\b([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b'
)


@dataclass
class Candidate:
    """
    An issue or pull request that may already track a finding

    Attributes
    ----------
    ref : str
        ``<owner>/<repo>#<number>``

    title : str
        Its title

    state : str
        ``open`` or ``closed``

    kind : str
        ``issue`` or ``pull request``

    closed : str, optional
        When it was closed, as ``yyyy-mm-dd``

    url : str
        Its page on GitHub
    """

    ref: str
    title: str
    state: str
    kind: str
    closed: Optional[str]
    url: str


def candidates(finding: Finding) -> List[Candidate]:
    """
    Issues and pull requests that may already track a finding

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    Returns
    -------
    candidates : list of bug_hunt_match.Candidate
        Open issues and pull requests, and issues closed in the last
        :py:data:`CLOSED_DAYS` days, from searches built from the
        finding's keys
    """
    since = (
        datetime.date.today() - datetime.timedelta(days=CLOSED_DAYS)
    ).isoformat()
    found: Dict[str, Candidate] = {}
    for terms in search_terms(finding):
        for repo in REPOS:
            for candidate in search(terms, repo):
                closed = candidate.closed
                recent = closed is not None and closed >= since
                if candidate.state == 'open' or recent:
                    found.setdefault(candidate.ref, candidate)
    return list(found.values())


def search_terms(finding: Finding) -> List[str]:
    """
    The searches to run for a finding, from its keys and the identifiers in
    its claim

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    Returns
    -------
    terms : list of str
        Search terms, one search each, without duplicates
    """
    terms: List[str] = []
    for key in finding.keys:
        for term in _key_terms(key):
            if term and term not in terms:
                terms.append(term)
    for term in claim_identifiers(finding.claim):
        if term not in terms:
            terms.append(term)
    return terms


def claim_identifiers(claim: Optional[str]) -> List[str]:
    """
    The code identifiers in a claim, each followed by the name of its
    family if it has one

    Parameters
    ----------
    claim : str, optional
        The claim

    Returns
    -------
    identifiers : list of str
        At most :py:data:`MAX_IDENTIFIERS` names from the claim, in order,
        plus their families
    """
    names: List[str] = []
    for match in _IDENTIFIER.finditer(claim or ''):
        name = next(group for group in match.groups() if group)
        name = name.strip('.,;:()')
        if len(name) < 4 or name in names:
            continue
        names.append(name)
    names = names[:MAX_IDENTIFIERS]
    identifiers: List[str] = []
    for name in names:
        for family_name in [name] + [
            family
            for pattern, family in IDENTIFIER_FAMILIES
            if pattern.match(name)
        ]:
            if family_name not in identifiers:
                identifiers.append(family_name)
    return identifiers


@lru_cache(maxsize=None)
def search(terms: str, repo: str) -> Tuple[Candidate, ...]:
    """
    Search a repository's issues and pull requests

    Parameters
    ----------
    terms : str
        The search terms

    repo : str
        The repository, such as ``E3SM-Project/Omega``

    Returns
    -------
    candidates : tuple of bug_hunt_match.Candidate
        At most :py:data:`MAX_RESULTS` results, most recently updated
        first; the same search is run only once

    Raises
    ------
    pr_test_github.GitHubError
        If the search fails, including one still held back by GitHub's
        rate limit after waiting for it to reset, since a search that
        failed must never count as finding nothing
    """
    try:
        return _search(terms, repo)
    except GitHubError as exc:
        if not _rate_limited(exc):
            raise
        _wait_for_search_limit()
    return _search(terms, repo)


def _search(terms: str, repo: str) -> Tuple[Candidate, ...]:
    query = f'repo:{repo} {terms}'
    if gh_usable():
        output = gh(
            [
                'api',
                '-X',
                'GET',
                'search/issues',
                '-f',
                f'q={query}',
                '-f',
                'sort=updated',
                '-f',
                f'per_page={MAX_RESULTS}',
            ]
        )
        items = json.loads(output).get('items', [])
    else:
        quoted = urllib.parse.quote(query)
        pages = api_get(
            f'search/issues?q={quoted}&sort=updated&per_page={MAX_RESULTS}'
        )
        items = pages[0].get('items', []) if pages else []
    return tuple(_to_candidate(item, repo) for item in items[:MAX_RESULTS])


def link_state(ref: str) -> Dict[str, Optional[str]]:
    """
    The state of a linked issue or pull request

    Parameters
    ----------
    ref : str
        ``<owner>/<repo>#<number>``

    Returns
    -------
    state : dict
        ``state`` (``open`` or ``closed``), ``closed`` and ``merged``
        (dates, or ``None``)
    """
    repo, _, number = ref.partition('#')
    if not number.isdigit():
        raise GitHubError(f'{ref} is not <owner>/<repo>#<number>.')
    path = f'repos/{repo}/issues/{number}'
    if gh_usable():
        item = json.loads(gh(['api', path]))
    else:
        item = api_get(path)[0]
    merged = None
    pull = item.get('pull_request') or {}
    if pull.get('merged_at'):
        merged = pull['merged_at'][:10]
    closed = item.get('closed_at')
    return {
        'state': item.get('state'),
        'closed': closed[:10] if closed else None,
        'merged': merged,
    }


def refresh(finding: Finding) -> Optional[str]:
    """
    Check a tracked finding's links, and say whether it should be raised
    again

    A finding is raised again if it failed after its issue was closed or
    after a linked pull request was merged.

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    Returns
    -------
    change : str, optional
        What changed, or ``None``
    """
    last_failed = max(
        (occurrence.last_failed or '' for occurrence in finding.occurrences),
        default='',
    )
    if not last_failed:
        return None
    for ref in finding.links:
        state = link_state(ref)
        if state['merged'] is not None and last_failed > state['merged']:
            return f'fails after {ref} was merged'
        if (
            state['merged'] is None
            and state['state'] == 'closed'
            and state['closed'] is not None
            and last_failed > state['closed']
        ):
            return f'fails after {ref} was closed'
    return None


def _key_terms(key: Key) -> List[str]:
    """Search terms for one key, most specific first"""
    if key.phase == 'code':
        stem = key.test.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        return [stem]
    if key.phase == 'missing':
        return ['nightly CDash']
    if key.phase == 'warnings':
        return ['compiler warnings']
    if is_cime_name(key.test):
        test_type = key.test.split('.')[0].split('_')[0]
        return [test_type]
    if '/' in key.test:
        parts = key.test.split('/')
        groups = ('planar', 'spherical', 'column')
        grouped = len(parts) > 2 and parts[1] in groups
        family = parts[2] if grouped else parts[1]
        return [family]
    words = [word for word in key.test.split('_') if word != 'TEST']
    return [' '.join(words[:2])]


def _rate_limited(exc: Exception) -> bool:
    """Whether a GitHub error is the rate limit"""
    message = str(exc).lower()
    return 'rate limit' in message or 'http 403' in message


def _wait_for_search_limit() -> None:
    """
    Wait for GitHub's search rate limit to reset, for at most
    :py:data:`MAX_RATE_LIMIT_WAIT` seconds
    """
    wait = float(MAX_RATE_LIMIT_WAIT)
    try:
        if gh_usable():
            limits = json.loads(gh(['api', 'rate_limit']))
        else:
            limits = api_get('rate_limit')[0]
        reset = limits['resources']['search']['reset']
        wait = min(wait, max(1.0, reset - time.time() + 1))
    except (GitHubError, KeyError, ValueError):
        pass
    print(
        f"GitHub's search rate limit was reached; waiting {wait:.0f} s",
        flush=True,
    )
    time.sleep(wait)


def _to_candidate(item: Dict[str, Any], repo: str) -> Candidate:
    closed = item.get('closed_at')
    return Candidate(
        ref=f'{repo}#{item["number"]}',
        title=item.get('title', ''),
        state=item.get('state', ''),
        kind='pull request' if 'pull_request' in item else 'issue',
        closed=closed[:10] if closed else None,
        url=item.get('html_url', ''),
    )
