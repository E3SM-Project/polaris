import pytest
from bug_hunt import _update_priority
from bug_hunt_ledger import Finding, Key


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
