"""
The bug hunter's corpus of real cases: findings with the GitHub searches
and CDash responses they were matched or harvested against, saved, and
what must come of them.

``test_bug_hunt_corpus.py`` replays the saved responses.  ``live.py`` runs
the same cases against live searches, and with ``--save``, saves fresh
responses.  See ``README.md`` for the cases and why each is here.
"""

import contextlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional

import bug_hunt_cdash
import bug_hunt_match
from bug_hunt_cdash import BuildKind, CDash
from bug_hunt_harvest import harvest_cdash
from bug_hunt_ledger import Finding, Ledger, read_finding, write_finding
from ruamel.yaml import YAML

CORPUS_DIR = os.path.dirname(os.path.abspath(__file__))
MATCH_DIR = os.path.join(CORPUS_DIR, 'match')
HARVEST_DIR = os.path.join(CORPUS_DIR, 'harvest')

#: the fields of a GitHub search result the matcher reads, which are all
#: that is saved
ITEM_FIELDS = ('number', 'title', 'state', 'closed_at', 'html_url')


class MissingSearch(Exception):
    """A search the matcher runs has no saved response: refresh the case"""


@dataclass
class MatchOutcome:
    """What matching a case's finding gave, against what was expected"""

    case: str
    needs_ruling: List[str]
    broad: List[str]
    missed: List[str] = field(default_factory=list)
    wrongly_ruled: List[str] = field(default_factory=list)
    noise: int = 0
    max_noise: int = 0
    timing: Dict[str, Optional[str]] = field(default_factory=dict)
    wrong_timing: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missed
            or self.wrongly_ruled
            or self.wrong_timing
            or self.noise > self.max_noise
        )


def match_cases() -> List[str]:
    """The names of the match cases"""
    return sorted(
        name
        for name in os.listdir(MATCH_DIR)
        if os.path.isdir(os.path.join(MATCH_DIR, name))
    )


def harvest_cases() -> List[str]:
    """The names of the harvest cases"""
    return sorted(
        name
        for name in os.listdir(HARVEST_DIR)
        if os.path.isdir(os.path.join(HARVEST_DIR, name))
    )


def load_finding(case: str) -> Finding:
    """A match case's finding"""
    return read_finding(os.path.join(MATCH_DIR, case, 'finding.yaml'))


def load_expected(directory: str) -> Dict[str, Any]:
    """A case's expected outcome"""
    return _read(os.path.join(directory, 'expected.yaml'))


def saved_search(case: str) -> Callable[[str, str], List[Dict[str, Any]]]:
    """
    A stand-in for ``bug_hunt_match.search_items`` that answers from a
    case's saved responses, and refuses a search that was not saved
    """
    saved = _read(os.path.join(MATCH_DIR, case, 'searches.yaml'))
    by_search = {
        (entry['terms'], entry['repo']): entry['items'] or []
        for entry in saved['searches']
    }

    def items(terms: str, repo: str) -> List[Dict[str, Any]]:
        if (terms, repo) not in by_search:
            raise MissingSearch(
                f'Corpus case {case} has no saved search for "{terms}" in '
                f'{repo}.  Refresh it: python tests/bug_hunt/corpus/live.py '
                f'--save {case}'
            )
        return by_search[(terms, repo)]

    return items


def evaluate_match(case: str) -> MatchOutcome:
    """
    Match a case's finding with whatever ``search_items`` is in place, and
    compare with what is expected
    """
    finding = load_finding(case)
    expected = load_expected(os.path.join(MATCH_DIR, case))
    found = bug_hunt_match.candidates(finding, today=str(expected['date']))
    needs = [c.ref for c in found if c.needs_ruling]
    broad = [c.ref for c in found if not c.needs_ruling]
    must = expected.get('must_rule') or []
    must_not = expected.get('must_not_rule') or []
    # worth a ruling though not duplicates, so not counted as noise
    related = expected.get('related') or []
    outcome = MatchOutcome(
        case=case,
        needs_ruling=needs,
        broad=broad,
        missed=[ref for ref in must if ref not in needs],
        wrongly_ruled=[ref for ref in must_not if ref in needs],
        noise=len(
            [ref for ref in needs if ref not in must and ref not in related]
        ),
        max_noise=int(expected.get('max_noise', 0)),
    )
    by_ref = {c.ref: c for c in found}
    for ref, when in (expected.get('timing') or {}).items():
        candidate = by_ref.get(ref)
        got = (
            None
            if candidate is None
            else bug_hunt_match.timing(finding, candidate)
        )
        outcome.timing[ref] = got
        if got != when:
            outcome.wrong_timing.append(ref)
    return outcome


def save_searches(case: str, day: str) -> int:
    """
    Run each search a case's finding needs, live, and save the responses

    Returns
    -------
    count : int
        The number of searches saved
    """
    finding = load_finding(case)
    searches = []
    for terms in bug_hunt_match.search_terms(finding):
        for repo in bug_hunt_match.REPOS:
            items = bug_hunt_match.search_items(terms, repo)
            searches.append(
                {
                    'terms': terms,
                    'repo': repo,
                    'items': [_trim(item) for item in items],
                }
            )
    _write(
        {'saved': day, 'searches': searches},
        os.path.join(MATCH_DIR, case, 'searches.yaml'),
    )
    return len(searches)


def save_finding(case: str, finding: Finding) -> None:
    """Write a match case's finding"""
    write_finding(finding, os.path.join(MATCH_DIR, case, 'finding.yaml'))


def run_harvest(
    case: str, ledger_path: str, cache_dir: Optional[str] = None
) -> Ledger:
    """
    Harvest a case into an empty ledger

    By default, the CDash responses are the case's saved ones, in its
    ``cdash`` directory, read as cached whatever their age (within
    :py:func:`every_night_settled`).  A response that is not there would
    be fetched, which the caller must prevent, or allow when saving.  With
    ``cache_dir``, an empty directory, every response is fetched live.
    """
    directory = os.path.join(HARVEST_DIR, case)
    expected = load_expected(directory)
    ledger = Ledger(ledger_path)
    harvest_cdash(
        ledger,
        CDash('omega', cache_dir or directory, _kinds(expected)),
        _kinds(expected),
        str(expected['first']),
        str(expected['last']),
        lookback=int(expected['lookback']),
        day=str(expected['date']),
    )
    return ledger


def check_harvest(case: str, ledger: Ledger) -> List[str]:
    """What in a harvested case differs from what is expected"""
    expected = load_expected(os.path.join(HARVEST_DIR, case))
    problems = []
    for want in expected['occurrences']:
        occurrence = None
        for finding in ledger.findings().values():
            occurrence = finding.occurrence(want['test'], want['row'])
            if occurrence is not None:
                break
        if occurrence is None:
            problems.append(f'{want["test"]} on {want["row"]} not found')
            continue
        for name in ('first_failed', 'last_passed', 'first_ran'):
            if name in want and getattr(occurrence, name) != want[name]:
                problems.append(
                    f'{want["test"]} on {want["row"]}: {name} is '
                    f'{getattr(occurrence, name)}, not {want[name]}'
                )
    return problems


def trim_cdash_index(case: str) -> None:
    """
    Keep only the builds a harvest case reads in its saved indexes, and
    the saved responses for those builds
    """
    directory = os.path.join(HARVEST_DIR, case)
    expected = load_expected(directory)
    wanted = {tuple(name.split(':', 1)) for name in expected['builds']}
    cache = os.path.join(directory, 'cdash', 'omega')
    kept: set = set()
    for filename in sorted(os.listdir(cache)):
        if not filename.startswith('index_'):
            continue
        path = os.path.join(cache, filename)
        data = _read_json(path)
        groups = []
        for group in data.get('buildgroups', []):
            builds = [
                build
                for build in group.get('builds', [])
                if (build.get('site'), build.get('buildname')) in wanted
            ]
            if builds:
                groups.append({**group, 'builds': builds})
        _write_json({'buildgroups': groups}, path)
        kept.update(
            str(build['id']) for group in groups for build in group['builds']
        )
    for filename in sorted(os.listdir(cache)):
        prefix, _, rest = filename.partition('_')
        if prefix in ('failed', 'status'):
            build_id = rest.split('_')[0].split('.')[0]
            if build_id not in kept:
                os.remove(os.path.join(cache, filename))


@contextlib.contextmanager
def every_night_settled() -> Iterator[None]:
    """
    Count every night as settled, so that saved CDash responses are read
    and fresh ones saved whatever their age
    """
    original = bug_hunt_cdash._days_ago
    bug_hunt_cdash._days_ago = lambda days: '9999-12-31'
    try:
        yield
    finally:
        bug_hunt_cdash._days_ago = original


def _kinds(expected: Dict[str, Any]) -> List[BuildKind]:
    return [
        BuildKind(
            pattern=re.compile(kind['pattern']),
            source=kind['source'],
            omega=kind['omega'],
            rows=list(kind['rows']),
        )
        for kind in expected['kinds']
    ]


def _trim(item: Dict[str, Any]) -> Dict[str, Any]:
    trimmed = {name: item.get(name) for name in ITEM_FIELDS}
    if 'pull_request' in item:
        merged = (item.get('pull_request') or {}).get('merged_at')
        trimmed['pull_request'] = {'merged_at': merged}
    return trimmed


def _read(path: str) -> Dict[str, Any]:
    with open(path) as handle:
        return YAML(typ='safe').load(handle) or {}


def _write(data: Dict[str, Any], path: str) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 79
    with open(path, 'w') as handle:
        yaml.dump(data, handle)


def _read_json(path: str) -> Dict[str, Any]:
    with open(path) as handle:
        return json.load(handle)


def _write_json(data: Dict[str, Any], path: str) -> None:
    with open(path, 'w') as handle:
        json.dump(data, handle, indent=1)
        handle.write('\n')
