import bug_hunt_match
import pytest
from bug_hunt_ledger import Finding, Key
from bug_hunt_match import Candidate, candidates, claim_identifiers, search
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


def test_the_two_duplicates_filed_in_the_first_week_are_found(monkeypatch):
    """
    Replays the review findings filed twice: a GPU race already reported in
    Omega#631, and one instance of Omega#434, about loops that ignore the
    minimum layer index.  The searches return what GitHub returned for the
    same terms on 2026-10-30.

    The identifier families were added for this very case, so passing shows
    that these two are found, not that recall is good in general.
    """
    known = {
        'ProvPseudoThickness': [
            _issue(
                631,
                'Per-edge inner loops will race on GPUs once cells '
                'start below the top layer',
            ),
        ],
        'MinLayerCell': [
            _issue(
                434,
                'Ensure that `MinLayerCell` is used for vertical '
                'loop lower limit',
            ),
        ],
    }

    def fake_search(terms, repo):
        if repo != 'E3SM-Project/Omega':
            return ()
        return tuple(known.get(terms, []))

    monkeypatch.setattr(bug_hunt_match, '_search', fake_search)
    race = _code_finding(
        'components/omega/src/ocn/auxiliaryVars/PseudoThicknessAuxVars.h',
        'ProvPseudoThickness can race on GPUs wherever the minimum layer '
        'index is above 0: its scratch array is zeroed, accumulated and '
        'read over different layer ranges with no team barrier',
    )
    instance = _code_finding(
        'components/omega/src/ocn/HorzOperators.h',
        'TangentialReconOnEdge ignores the lower layer bound, so KPP and '
        'VertMix compute tangential velocity on the wrong layers wherever '
        'MinLayerEdgeBot is above 0',
    )

    assert 'E3SM-Project/Omega#631' in [c.ref for c in candidates(race)]
    assert 'E3SM-Project/Omega#434' in [c.ref for c in candidates(instance)]


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
