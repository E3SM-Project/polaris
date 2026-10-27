import argparse
import subprocess

import bug_hunt
import pytest
from bug_hunt import _check_candidates, _set_outside_v4, _update_priority
from bug_hunt_ledger import Finding, Key, Ledger, Occurrence
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
    args: dict = dict(post=True, batch=None, repo=None, not_duplicate=[])
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


def test_update_refuses_a_name_another_finding_has(tmp_path, monkeypatch):
    ledger = _cli_ledger(tmp_path, monkeypatch)
    first = _finding(name='sea ice runs short')
    second = _finding()
    second.id = 'F-20261030-ef01'
    ledger.save(first)
    ledger.save(second)

    with pytest.raises(ValueError, match='already named'):
        bug_hunt._update(_update_args(second.id, name='Sea ice runs short'))
    bug_hunt._update(_update_args('sea ice runs short', note='by name'))
    assert ledger.get(first.id).history[-1]['change'].endswith('by name')


def test_split_rows_are_not_the_finding_coming_back(tmp_path, monkeypatch):
    ledger = _cli_ledger(tmp_path, monkeypatch)
    finding = _finding(
        name="Frontier nightly can't find python",
        status='fixed',
        came_back=True,
        changed='fails again after it was fixed',
    )
    finding.occurrences = [
        Occurrence(test='t', row='frontier/craygnu', source='ctest'),
        Occurrence(test='t', row='frontier/craycray', source='ctest'),
    ]
    ledger.save(finding)

    bug_hunt._update(_update_args(finding.id, split='frontier/craycray'))
    finding = ledger.get(finding.id)
    assert not finding.came_back
    assert finding.changed is None
    assert finding.rows == ['frontier/craygnu']


def _cli_ledger(tmp_path, monkeypatch):
    path = tmp_path / 'ledger'
    path.mkdir()
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(
        ['git', '-C', str(path), 'commit', '-q', '--allow-empty', '-m', 'x'],
        check=True,
    )
    ledger = Ledger(str(path))
    monkeypatch.setattr(
        bug_hunt, '_setup', lambda args: (None, Ledger(str(path)))
    )
    return ledger


def _update_args(finding_id, **overrides):
    args: dict = dict(
        id=finding_id,
        name=None,
        owner=None,
        severity=None,
        confidence=None,
        status=None,
        claim=None,
        where=None,
        expected=None,
        reproduce=None,
        theme=None,
        dig=None,
        fixing=None,
        context=None,
        caused_by=None,
        propose=None,
        evidence=None,
        link=[],
        unlink=[],
        seen=False,
        merge=[],
        split=None,
        outside_v4=None,
        not_duplicate=[],
        priority=None,
        note=None,
        answer=None,
    )
    args.update(overrides)
    return argparse.Namespace(**args)


def test_a_dig_that_waits_says_what_for(tmp_path, monkeypatch):
    ledger = _cli_ledger(tmp_path, monkeypatch)
    finding = _finding(name='pm-gpu stopped sending nightly Polaris results')
    ledger.save(finding)

    with pytest.raises(ValueError, match='what it waits for'):
        bug_hunt._update(_update_args(finding.id, status='digging'))
    bug_hunt._update(
        _update_args(finding.id, status='digging', note='Perlmutter')
    )
    assert ledger.get(finding.id).waiting_for == 'Perlmutter'
    bug_hunt._update(_update_args(finding.id, status='new'))
    assert ledger.get(finding.id).waiting_for is None


def _batch_state(body, state='open'):
    return {
        'state': state,
        'closed': None,
        'merged': None,
        'reason': None,
        'title': 'Clean-up: ice shelves',
        'body': body,
    }


def test_refresh_reads_a_batch_lines_and_whether_all_are_done():
    finding = _finding()
    line = f'- [x] A claim. <!-- {finding.id} -->'
    states = {'E3SM-Project/polaris#964': _batch_state(line + '\n')}
    assert bug_hunt._line_done_on(finding, states, '2026-11-12') == (
        '2026-11-12'
    )
    assert bug_hunt._ready_batches(states) == {'E3SM-Project/polaris#964'}

    open_line = f'- [ ] A claim. <!-- {finding.id} -->\n- [x] Other.\n'
    states = {'E3SM-Project/polaris#964': _batch_state(open_line)}
    assert bug_hunt._line_done_on(finding, states, '2026-11-12') is None
    assert bug_hunt._ready_batches(states) == set()


def test_a_second_digest_keeps_the_answers_recorded():
    recorded = [
        {'id': 'F-a', 'answer': 'file'},
        {'id': 'F-b', 'answer': None},
        {'id': 'F-c', 'answer': 'dismiss'},
    ]
    # the new digest asks about F-a again, F-b and a new F-d, but no
    # longer about F-c, which was dismissed
    assert bug_hunt._digest_decisions(recorded, ['F-a', 'F-b', 'F-d']) == [
        {'id': 'F-a', 'answer': 'file'},
        {'id': 'F-b', 'answer': None},
        {'id': 'F-d', 'answer': None},
        {'id': 'F-c', 'answer': 'dismiss'},
    ]
