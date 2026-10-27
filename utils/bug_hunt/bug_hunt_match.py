"""
Matching findings against what is already known: open issues and pull
requests in Omega and Polaris, and issues closed lately
"""

import datetime
import json
import re
import time
import urllib.parse
from dataclasses import dataclass, replace
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

#: the most results a search asks for, enough that a term's are rarely
#: cut short; GitHub's search limit counts requests, not results
MAX_RESULTS = 100

#: a term that finds fewer issues than this in both repositories together,
#: or fewer pull requests, is specific enough that what it finds of that
#: kind needs a ruling
FEW_RESULTS = 10

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

    found_by : tuple of str
        The search terms that found it

    needs_ruling : bool
        Whether the agent must link it or rule it out before filing.  An
        issue does if a term that finds few issues found it.  A pull
        request does if it merged when the failure began or ended, or if it
        is open and a term that finds few pull requests found it.  The rest
        were found only by broad terms, such as a tool's name that every
        pull request tested with it mentions.
    """

    ref: str
    title: str
    state: str
    kind: str
    closed: Optional[str]
    url: str
    found_by: Tuple[str, ...] = ()
    needs_ruling: bool = True


#: what :py:func:`timing` says of a pull request that may have fixed or
#: caused a finding
FIXED_WHEN = 'merged before it passed'
CAUSED_WHEN = 'merged before the first failure'


def candidates(
    finding: Finding, today: Optional[str] = None
) -> List[Candidate]:
    """
    Issues and pull requests that may already track a finding

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    today : str, optional
        The date the closed issues are counted back from, ``yyyy-mm-dd``;
        today's by default.  Saved searches replay with the date they were
        saved on.

    Returns
    -------
    candidates : list of bug_hunt_match.Candidate
        Open issues and pull requests, and issues closed in the last
        :py:data:`CLOSED_DAYS` days, from searches built from the
        finding's keys
    """
    day = (
        datetime.date.fromisoformat(today)
        if today is not None
        else datetime.date.today()
    )
    since = (day - datetime.timedelta(days=CLOSED_DAYS)).isoformat()
    found: Dict[str, Candidate] = {}
    found_by: Dict[str, List[str]] = {}
    # the terms that find few issues, and those that find few pull requests
    specific: Dict[str, set] = {'issue': set(), 'pull request': set()}
    for terms in search_terms(finding):
        results = [
            candidate for repo in REPOS for candidate in search(terms, repo)
        ]
        for kind, few in specific.items():
            if sum(1 for c in results if c.kind == kind) < FEW_RESULTS:
                few.add(terms)
        for candidate in results:
            closed = candidate.closed
            recent = closed is not None and closed >= since
            if candidate.state == 'open' or recent:
                found.setdefault(candidate.ref, candidate)
                by = found_by.setdefault(candidate.ref, [])
                if terms not in by:
                    by.append(terms)
    ranked = []
    for ref, candidate in found.items():
        by = found_by[ref]
        few = specific[candidate.kind]
        if candidate.kind == 'pull request':
            # a pull request matters when it may have caused or fixed the
            # failure, or, while open, when it may be fixing it
            needs_ruling = timing(finding, candidate) is not None or (
                candidate.state == 'open' and any(term in few for term in by)
            )
        else:
            needs_ruling = any(term in few for term in by)
        ranked.append(
            replace(candidate, found_by=tuple(by), needs_ruling=needs_ruling)
        )
    # those that need a ruling first, each group in the order found
    ranked.sort(key=lambda candidate: not candidate.needs_ruling)
    return ranked


def timing(finding: Finding, candidate: Candidate) -> Optional[str]:
    """
    Whether a pull request was merged when a finding began or ended to
    fail, so it may have caused or fixed it

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    candidate : bug_hunt_match.Candidate
        An issue or pull request from :py:func:`candidates`

    Returns
    -------
    when : str, optional
        ``merged before it passed`` or ``merged before the first
        failure``, or ``None``
    """
    if candidate.ref in finding.ended_between:
        return FIXED_WHEN
    if candidate.ref in finding.merged_between:
        return CAUSED_WHEN
    if candidate.kind != 'pull request' or candidate.closed is None:
        return None
    merged = candidate.closed
    for occurrence in finding.occurrences:
        if (
            finding.ended is not None
            and occurrence.last_failed is not None
            and occurrence.last_failed <= merged <= finding.ended
        ):
            return FIXED_WHEN
    for occurrence in finding.occurrences:
        if (
            occurrence.last_passed is not None
            and occurrence.first_failed is not None
            and occurrence.last_passed <= merged <= occurrence.first_failed
        ):
            return CAUSED_WHEN
    return None


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
        At most :py:data:`MAX_RESULTS` results, best matches
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
    return tuple(
        _to_candidate(item, repo) for item in search_items(terms, repo)
    )


def search_items(terms: str, repo: str) -> List[Dict[str, Any]]:
    """
    The issues and pull requests a GitHub search returns, as GitHub gives
    them, at most :py:data:`MAX_RESULTS`, best matches first

    Parameters
    ----------
    terms : str
        The search terms

    repo : str
        The repository, such as ``E3SM-Project/Omega``

    Returns
    -------
    items : list of dict
        GitHub's search results
    """
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
                f'per_page={MAX_RESULTS}',
            ]
        )
        items = json.loads(output).get('items', [])
    else:
        quoted = urllib.parse.quote(query)
        pages = api_get(f'search/issues?q={quoted}&per_page={MAX_RESULTS}')
        items = pages[0].get('items', []) if pages else []
    return items[:MAX_RESULTS]


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
        (dates, or ``None``), ``reason`` (GitHub's ``state_reason``,
        such as ``completed`` or ``duplicate``, or ``None``), and
        ``title`` and ``body``
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
        'reason': item.get('state_reason'),
        'title': item.get('title') or '',
        'body': item.get('body') or '',
    }


def refresh(
    finding: Finding, states: Optional[Dict[str, Dict[str, Any]]] = None
) -> Optional[str]:
    """
    Check a tracked finding's links, and say whether it should be raised
    again

    A finding is raised again if it failed after its issue was closed or
    after a linked pull request was merged.

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    states : dict, optional
        The state of each link, from :py:func:`link_state`, if already
        looked up

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
        state = states[ref] if states is not None else link_state(ref)
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


def closed_upstream(
    finding: Finding, states: Dict[str, Dict[str, Any]]
) -> Optional[str]:
    """
    When a finding's links all closed, if they have and it has not failed
    since

    Whether each link was closed by a fix is for the agent to check: an
    issue closed as a duplicate is replaced by the issue it duplicates.

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    states : dict
        The state of each link, from :py:func:`link_state`

    Returns
    -------
    closed : str, optional
        The date the last link closed, or ``None``
    """
    if not finding.links:
        return None
    dates = []
    for ref in finding.links:
        state = states[ref]
        if state['state'] != 'closed' or state['closed'] is None:
            return None
        dates.append(state['merged'] or state['closed'])
    closed = max(dates)
    last_failed = max(
        (occurrence.last_failed or '' for occurrence in finding.occurrences),
        default='',
    )
    if last_failed > closed:
        return None
    return closed


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
