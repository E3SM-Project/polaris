import argparse

import bug_hunt
import pytest
from bug_hunt import _check_candidates, _set_outside_v4, _update_priority
from bug_hunt_ledger import Finding, Key
from bug_hunt_match import Candidate


def _finding(**fields):
    return Finding(
        id='F-20261030-abcd',
        keys=[Key('t', 'code', None)],
        created='2026-10-30',
        source='review',
        severity='S1',
        confidence='inferred',
        **fields,
    )


def test_update_sets_the_rubrics_priority():
    finding = _finding()
    assert _update_priority(finding, None, None) == 'priority=P2'
    assert finding.priority_note is None


def test_a_different_priority_needs_a_note():
    finding = _finding()
    with pytest.raises(ValueError, match='rubric gives F-20261030-abcd P2'):
        _update_priority(finding, 'P3', None)

    change = _update_priority(finding, 'P3', 'only with a non-default option')
    assert change == 'priority=P3'
    assert finding.priority_note == 'only with a non-default option'


def test_the_rubrics_priority_clears_a_note():
    finding = _finding(priority='P3', priority_note='an old reason')
    assert _update_priority(finding, 'P2', None) == 'priority=P2'
    assert finding.priority_note is None


def test_an_entry_outside_v4_must_be_on_the_list():
    finding = _finding(owner='omega')
    with pytest.raises(ValueError, match='not in outside_v4.yaml'):
        _set_outside_v4(finding, 'langmuir', {})

    assert _set_outside_v4(finding, 'langmuir', {'langmuir': {}}) == [
        'outside_v4=langmuir'
    ]
    assert _update_priority(finding, None, None, {'langmuir': {}}) == (
        'priority=P3'
    )
    assert _set_outside_v4(finding, '', {}) == ['outside_v4=None']
    assert _set_outside_v4(finding, None, {}) == []


def _file_args(**overrides):
    args: dict = dict(
        post=True, batch=None, all_p4=False, repo=None, not_duplicate=[]
    )
    args.update(overrides)
    return argparse.Namespace(**args)


def _patch_search(monkeypatch, refs):
    found = [
        Candidate(ref, f'title of {ref}', 'open', 'issue', None, '')
        for ref in refs
    ]
    monkeypatch.setattr(bug_hunt, 'candidates', lambda finding: found)


def test_file_post_refuses_a_candidate_not_ruled_out(monkeypatch):
    _patch_search(monkeypatch, ['E3SM-Project/Omega#631'])
    finding = _finding(owner='omega')
    findings = {finding.id: finding}

    with pytest.raises(ValueError, match='E3SM-Project/Omega#631'):
        _check_candidates([finding.id], findings, None, _file_args(), [])


def test_file_post_goes_ahead_once_each_candidate_is_ruled_out(monkeypatch):
    _patch_search(
        monkeypatch, ['E3SM-Project/Omega#631', 'E3SM-Project/Omega#650']
    )
    finding = _finding(owner='omega', links=['E3SM-Project/Omega#650'])
    findings = {finding.id: finding}
    ruled_out = [
        {'ref': 'E3SM-Project/Omega#631', 'why': 'a different kernel'}
    ]

    _check_candidates([finding.id], findings, None, _file_args(), ruled_out)
