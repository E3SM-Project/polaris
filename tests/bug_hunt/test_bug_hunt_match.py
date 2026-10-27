import bug_hunt_match
import pytest
from bug_hunt_ledger import Finding, Key, Occurrence
from bug_hunt_match import (
    Candidate,
    candidates,
    claim_identifiers,
    closed_upstream,
    search,
    timing,
)
from pr_test_github import GitHubError


@pytest.fixture(autouse=True)
def fresh_search_cache():
    search.cache_clear()
    yield
    search.cache_clear()


def _issue(number, title, repo='E3SM-Project/Omega'):
    return Candidate(
        ref=f'{repo}#{number}',
        title=title,
        state='open',
        kind='issue',
        closed=None,
        url='',
    )


def _code_finding(path, claim):
    return Finding(
        id='F-20261030-test',
        keys=[Key(path, 'code', claim.lower()[:120])],
        created='2026-10-30',
        source='review',
        owner='omega',
        claim=claim,
    )


def test_identifiers_come_from_the_claim_with_their_families():
    claim = (
        'TangentialReconOnEdge ignores the lower layer bound, so KPP and '
        'VertMix compute tangential velocity on the wrong layers wherever '
        'MinLayerEdgeBot is above 0'
    )
    assert claim_identifiers(claim) == [
        'TangentialReconOnEdge',
        'VertMix',
        'MinLayerEdgeBot',
        'MinLayerCell',
    ]
    assert claim_identifiers(
        'A time mean aborts because their `valid_min` is the int literal `0`'
    ) == ['valid_min']


def test_a_search_at_the_rate_limit_waits_then_succeeds(monkeypatch):
    calls = []

    def flaky_search(terms, repo):
        calls.append(terms)
        if len(calls) == 1:
            raise GitHubError('HTTP 403: API rate limit exceeded')
        return (_issue(1, 'found'),)

    waits: list[float] = []
    monkeypatch.setattr(bug_hunt_match, '_search', flaky_search)
    monkeypatch.setattr(bug_hunt_match, 'gh_usable', lambda: False)
    monkeypatch.setattr(
        bug_hunt_match,
        'api_get',
        lambda path: [{'resources': {'search': {'reset': 0}}}],
    )
    monkeypatch.setattr(bug_hunt_match.time, 'sleep', waits.append)

    assert [c.ref for c in search('MinLayerCell', 'E3SM-Project/Omega')] == [
        'E3SM-Project/Omega#1'
    ]
    assert len(waits) == 1


def test_a_search_still_at_the_rate_limit_after_its_wait_fails(monkeypatch):
    def limited(terms, repo):
        raise GitHubError('HTTP 403: API rate limit exceeded')

    monkeypatch.setattr(bug_hunt_match, '_search', limited)
    monkeypatch.setattr(bug_hunt_match, 'gh_usable', lambda: False)
    monkeypatch.setattr(
        bug_hunt_match,
        'api_get',
        lambda path: [{'resources': {'search': {'reset': 0}}}],
    )
    monkeypatch.setattr(bug_hunt_match.time, 'sleep', lambda seconds: None)

    # a failed search must never count as finding nothing
    with pytest.raises(GitHubError, match='rate limit'):
        search('MinLayerCell', 'E3SM-Project/Omega')


def _state(state, closed=None, merged=None, reason=None):
    return {
        'state': state,
        'closed': closed,
        'merged': merged,
        'reason': reason,
    }


def _tracked(last_failed, links):
    finding = Finding(
        id='F-20261027-239b',
        keys=[Key('PEM', 'compare', None)],
        created='2026-10-27',
        source='coupled',
        status='tracked',
        links=list(links),
    )
    finding.occurrences = [
        Occurrence(
            test='PEM',
            row='chrysalis/intel',
            source='coupled',
            last_failed=last_failed,
        )
    ]
    return finding


def test_a_finding_whose_links_all_closed_is_closed_upstream():
    links = ['E3SM-Project/Omega#626', 'E3SM-Project/Omega#640']
    states = {
        links[0]: _state('closed', closed='2026-10-27', reason='completed'),
        links[1]: _state('closed', closed='2026-10-27', merged='2026-10-27'),
    }
    assert closed_upstream(_tracked('2026-10-27', links), states) == (
        '2026-10-27'
    )
    # a failure after the links closed is a change, not closed upstream
    assert closed_upstream(_tracked('2026-10-29', links), states) is None
    # one link still open
    states[links[0]] = _state('open')
    assert closed_upstream(_tracked('2026-10-20', links), states) is None


def _pull(number, merged, title=''):
    return Candidate(
        ref=f'E3SM-Project/Omega#{number}',
        title=title,
        state='closed',
        kind='pull request',
        closed=merged,
        url='',
    )


def test_the_sphere_operator_failures_point_to_their_cause_and_fix():
    # HORZOPERATORS_SPHERE_TEST failed on the 2026-11-07 night only, after
    # Omega#639 brought in the PCD mean radius, and #643 updated the
    # expected values
    finding = Finding(
        id='F-20261111-4042',
        keys=[Key('HORZOPERATORS_SPHERE_TEST', 'run', None)],
        created='2026-11-11',
        source='ctest',
        ended='2026-11-08',
    )
    finding.occurrences = [
        Occurrence(
            test='HORZOPERATORS_SPHERE_TEST',
            row='chrysalis/intel',
            source='ctest',
            first_failed='2026-11-07',
            last_failed='2026-11-07',
            last_passed='2026-11-06',
        )
    ]
    assert timing(finding, _pull(643, '2026-11-07')) == (
        'merged before it passed'
    )
    assert timing(finding, _pull(639, '2026-11-06')) == (
        'merged before the first failure'
    )
    assert timing(finding, _pull(600, '2026-10-01')) is None


def _many(start, count, repo='E3SM-Project/Omega'):
    title = 'a pull request tested with the tool'
    return [
        _issue(number, title, repo=repo)
        for number in range(start, start + count)
    ]


def test_a_broad_term_alone_does_not_need_a_ruling(monkeypatch):
    # a tool's name fills a page of results; a file stem finds one issue
    results = {
        ('omega_pr_test', 'E3SM-Project/Omega'): _many(700, 10),
        ('omega_pr_test', 'E3SM-Project/polaris'): _many(
            900, 6, repo='E3SM-Project/polaris'
        ),
        ('omega_pr_coupled', 'E3SM-Project/polaris'): [
            _issue(950, 'Coupled reports hang', repo='E3SM-Project/polaris')
        ],
    }
    monkeypatch.setattr(
        bug_hunt_match,
        '_search',
        lambda terms, repo: tuple(results.get((terms, repo), [])),
    )
    finding = _code_finding(
        'utils/omega/pr_testing/omega_pr_coupled.py',
        'In the Omega PR-testing utility, omega_pr_test.py report never '
        'reads back hand-submitted job IDs',
    )
    by_ref = {c.ref: c for c in candidates(finding)}
    assert by_ref['E3SM-Project/polaris#950'].needs_ruling
    assert not by_ref['E3SM-Project/Omega#700'].needs_ruling
    assert not by_ref['E3SM-Project/polaris#900'].needs_ruling


def test_a_term_finding_fewer_than_a_page_in_total_is_specific(monkeypatch):
    # nine results across both repositories is specific; ten, even if all
    # in one repository, fill a page and are broad
    results = {
        ('FewHits', 'E3SM-Project/Omega'): _many(1, 5),
        ('FewHits', 'E3SM-Project/polaris'): _many(
            20, 4, repo='E3SM-Project/polaris'
        ),
        ('ManyHits', 'E3SM-Project/Omega'): _many(40, 10),
    }
    monkeypatch.setattr(
        bug_hunt_match,
        '_search',
        lambda terms, repo: tuple(results.get((terms, repo), [])),
    )
    few = _code_finding('src/a.cpp', '`FewHits` is wrong')
    many = _code_finding('src/b.cpp', '`ManyHits` is wrong')
    assert all(c.needs_ruling for c in candidates(few))
    assert not any(c.needs_ruling for c in candidates(many))


def test_two_broad_terms_finding_the_same_pull_request_need_no_ruling(
    monkeypatch,
):
    # "deleting an Omega test tree breaks later coupled builds", 2026-11-11:
    # 'E3SM' and 'omega_pr_test' each fill a page, and both find the same
    # recent pull requests, which have nothing to do with the bug
    shared = _many(670, 5)
    results = {
        ('E3SM', 'E3SM-Project/Omega'): shared + _many(680, 5),
        ('E3SM', 'E3SM-Project/polaris'): _many(
            930, 10, repo='E3SM-Project/polaris'
        ),
        ('omega_pr_test', 'E3SM-Project/Omega'): shared + _many(690, 5),
        ('omega_pr_test', 'E3SM-Project/polaris'): _many(
            950, 6, repo='E3SM-Project/polaris'
        ),
    }
    monkeypatch.setattr(
        bug_hunt_match,
        '_search',
        lambda terms, repo: tuple(results.get((terms, repo), [])),
    )
    finding = _code_finding(
        'utils/pr_testing/pr_test_setup.py',
        'In the Omega PR-testing utility, omega_pr_test.py cleanup --delete '
        "leaves the marker, so the rest of E3SM's submodules are skipped",
    )
    found = candidates(finding)
    assert found
    assert not any(c.needs_ruling for c in found)
