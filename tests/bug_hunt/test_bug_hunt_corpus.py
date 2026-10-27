"""
The bug hunter's corpus of real cases, replayed from saved responses.

Each case in ``corpus/match`` must find its duplicates as candidates that
need a ruling, and keep the rest of what needs a ruling, its noise, within
its limit.  Each case in ``corpus/harvest`` must record what its saved
CDash responses show.  Nothing is fetched: a search or response that was
not saved fails the case, which then needs refreshing with
``corpus/live.py --save``.  See ``corpus/README.md``.
"""

import os
import sys

import bug_hunt_cdash
import bug_hunt_match
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'corpus'))

import corpus  # noqa: E402


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Refuse every request, so a response that was not saved fails"""

    def refuse(*args, **kwargs):
        raise corpus.MissingSearch(
            'The corpus asked for a response that was not saved.  Refresh '
            'the case with: python tests/bug_hunt/corpus/live.py --save '
            '<case>'
        )

    monkeypatch.setattr(bug_hunt_cdash, '_get_json', refuse)
    monkeypatch.setattr(bug_hunt_cdash, '_post_json', refuse)
    monkeypatch.setattr(bug_hunt_match, 'gh', refuse)
    monkeypatch.setattr(bug_hunt_match, 'api_get', refuse)
    bug_hunt_match.search.cache_clear()
    yield
    bug_hunt_match.search.cache_clear()


def _replay(case, monkeypatch):
    monkeypatch.setattr(
        bug_hunt_match, 'search_items', corpus.saved_search(case)
    )
    bug_hunt_match.search.cache_clear()
    return corpus.evaluate_match(case)


@pytest.mark.parametrize('case', corpus.match_cases())
def test_a_match_case_finds_its_duplicates_within_its_noise(case, monkeypatch):
    outcome = _replay(case, monkeypatch)
    assert not outcome.missed, (
        f'{case}: duplicates not raised for a ruling: {outcome.missed}'
    )
    assert not outcome.wrongly_ruled, (
        f'{case}: raised for a ruling but should not be: '
        f'{outcome.wrongly_ruled}'
    )
    assert not outcome.wrong_timing, (
        f'{case}: wrong timing for {outcome.wrong_timing}: {outcome.timing}'
    )
    assert outcome.noise <= outcome.max_noise, (
        f'{case}: {outcome.noise} unrelated candidates need a ruling, over '
        f'its limit of {outcome.max_noise}: {outcome.needs_ruling}'
    )


def test_the_corpus_noise_in_total(monkeypatch, capsys):
    outcomes = [_replay(case, monkeypatch) for case in corpus.match_cases()]
    total = sum(outcome.noise for outcome in outcomes)
    limit = sum(outcome.max_noise for outcome in outcomes)
    with capsys.disabled():
        print(
            f'\nBug-hunt corpus: {total} unrelated candidates need a ruling '
            f'across {len(outcomes)} match cases (limit {limit})'
        )
    assert total <= limit


@pytest.mark.parametrize('case', corpus.harvest_cases())
def test_a_harvest_case_records_what_cdash_shows(case, ledger_dir):
    with corpus.every_night_settled():
        ledger = corpus.run_harvest(case, str(ledger_dir))
    assert corpus.check_harvest(case, ledger) == []
