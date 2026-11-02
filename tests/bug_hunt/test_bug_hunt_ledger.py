import subprocess

import pytest
from bug_hunt_ledger import (
    Finding,
    Key,
    Ledger,
    LedgerError,
    Occurrence,
    merge_hunts,
    read_finding,
    record_answer,
    rubric_priority,
    set_priority,
    write_finding,
)


def test_an_answer_fills_in_the_digests_decision():
    hunt = {
        'decisions': [
            {'id': 'F-a', 'answer': None},
            {'id': 'F-b', 'answer': None},
        ]
    }
    record_answer(hunt, 'F-b', 'batch')
    record_answer(hunt, 'F-c', 'file')

    assert hunt['decisions'] == [
        {'id': 'F-a', 'answer': None},
        {'id': 'F-b', 'answer': 'batch'},
        {'id': 'F-c', 'answer': 'file'},
    ]
    with pytest.raises(LedgerError, match='is not one of'):
        record_answer(hunt, 'F-a', 'fix')


def _finding(finding_id='F-20261027-abcd', keys=None, **fields):
    if keys is None:
        keys = [Key('PEM_Vmct.T62_oQU240.COMEGA-IAF', 'compare', 'm')]
    return Finding(
        id=finding_id,
        keys=keys,
        created='2026-10-27',
        source='coupled',
        **fields,
    )


def test_finding_round_trip(tmp_path):
    finding = _finding(
        claim='PEM tests fail their comparison on CPUs',
        evidence='line one\nline two\n',
        links=['E3SM-Project/Omega#626'],
        occurrences=[
            Occurrence(
                test='PEM_Vmct.T62_oQU240.COMEGA-IAF',
                row='chrysalis/intel',
                source='coupled',
                first_failed='2026-10-07',
                last_passed='2026-10-06',
                nights=21,
            )
        ],
    )
    finding.note('harvested from coupled', '2026-10-27')
    filename = tmp_path / 'finding.yaml'
    write_finding(finding, str(filename))

    text = filename.read_text()
    assert 'evidence: |' in text
    assert 'priority' not in text
    assert read_finding(str(filename)) == finding


def test_unknown_fields_are_refused(tmp_path):
    filename = tmp_path / 'finding.yaml'
    write_finding(_finding(), str(filename))
    filename.write_text(filename.read_text() + 'surprise: 1\n')
    with pytest.raises(LedgerError, match='unknown fields'):
        read_finding(str(filename))


def test_a_key_limited_to_a_row_wins(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    test = 'PEM_Vmct.T62_oQU240.COMEGA-IAF'
    cpu = _finding('F-cpu', keys=[Key(test, 'compare', 'm')])
    gpu = _finding(
        'F-gpu', keys=[Key(test, 'compare', 'm', rows=['pm-gpu/gnugpu'])]
    )
    findings = {'F-cpu': cpu, 'F-gpu': gpu}

    assert ledger.find(findings, test, 'compare', 'm', 'pm-gpu/gnugpu') is gpu
    assert ledger.find(findings, test, 'compare', 'm', 'pm-cpu/gnu') is cpu
    assert ledger.find(findings, test, 'run', 'm', 'pm-cpu/gnu') is None


def test_new_ids_do_not_collide(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    key = Key('test', 'run', None)
    first = ledger.new_id(key, '2026-10-27')
    ledger.save(_finding(first))
    second = ledger.new_id(key, '2026-10-27')

    assert first.startswith('F-20261027-')
    assert second != first
    assert second.startswith(first)


def test_save_commit_and_read_back(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    ledger.save(_finding())
    hunt = ledger.load_hunt('2026-10-27')
    hunt['covered']['cdash'] = '2026-10-27'
    ledger.save_hunt(hunt)
    ledger.commit('Harvest on 2026-10-27')

    log = subprocess.run(
        ['git', '-C', str(ledger_dir), 'log', '--oneline'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert 'Harvest on 2026-10-27' in log
    assert list(ledger.findings()) == ['F-20261027-abcd']
    assert ledger.covered('cdash') == '2026-10-27'
    assert ledger.covered('review') is None


def test_a_ledger_must_be_a_clone(tmp_path):
    with pytest.raises(LedgerError, match='not a clone'):
        Ledger(str(tmp_path))


def test_commit_pushes_even_when_push_default_is_nothing(tmp_path, ledger_dir):
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
    for args in (
        ['remote', 'add', 'origin', str(remote)],
        ['push', '-q', '-u', 'origin', 'HEAD:main'],
        ['config', 'push.default', 'nothing'],
    ):
        subprocess.run(['git', '-C', str(ledger_dir)] + args, check=True)
    ledger = Ledger(str(ledger_dir))
    ledger.save(_finding())
    ledger.commit('Add a finding')

    log = subprocess.run(
        ['git', '-C', str(remote), 'log', '--oneline', 'main'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert 'Add a finding' in log


def _git(path, *args):
    return subprocess.run(
        ['git', '-C', str(path)] + list(args),
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _two_clones(tmp_path, ledger_dir):
    """Two clones of one remote, as two machines or two agents have"""
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
    _git(ledger_dir, 'remote', 'add', 'origin', str(remote))
    _git(ledger_dir, 'push', '-q', '-u', 'origin', 'HEAD:main')
    other = tmp_path / 'other'
    subprocess.run(['git', 'clone', '-q', str(remote), str(other)], check=True)
    return remote, Ledger(str(ledger_dir)), Ledger(str(other))


def _touch(ledger, finding, day='2026-10-30'):
    """Save a finding and note it in the day's hunt, as park does"""
    ledger.save(finding)
    hunt = ledger.load_hunt(day)
    hunt['touched'].append(finding.id)
    ledger.save_hunt(hunt)


def test_merging_hunts_keeps_what_both_clones_wrote():
    upstream = {
        'date': '2026-10-30',
        'covered': {
            'cdash': '2026-10-29',
            'review': 'merges through abc',
            'review_until': '2026-10-30',
        },
        'touched': ['F-a', 'F-b'],
        'decisions': [{'id': 'F-a', 'answer': None}],
    }
    replayed = {
        'date': '2026-10-30',
        'covered': {
            'cdash': '2026-10-30',
            'review': 'merges through older',
            'review_until': '2026-10-29',
        },
        'touched': ['F-a', 'F-c'],
        'decisions': [
            {'id': 'F-a', 'answer': 'file'},
            {'id': 'F-c', 'answer': None},
        ],
    }

    merged = merge_hunts(upstream, replayed)

    assert merged['covered'] == {
        'cdash': '2026-10-30',
        'review': 'merges through abc',
        'review_until': '2026-10-30',
    }
    assert merged['touched'] == ['F-a', 'F-b', 'F-c']
    assert merged['decisions'] == [
        {'id': 'F-a', 'answer': 'file'},
        {'id': 'F-c', 'answer': None},
    ]


def test_a_rejected_push_merges_the_days_hunt_and_pushes(tmp_path, ledger_dir):
    remote, first, second = _two_clones(tmp_path, ledger_dir)
    _touch(first, _finding('F-20261030-aaaa'))
    first.commit('Recorded F-20261030-aaaa')
    # the second clone has not pulled since the first pushed
    _touch(second, _finding('F-20261030-bbbb'))
    second.commit('Recorded F-20261030-bbbb')

    log = _git(remote, 'log', '--format=%s', 'main')
    assert 'Recorded F-20261030-aaaa' in log
    assert 'Recorded F-20261030-bbbb' in log
    assert not second._rebasing()
    assert second.load_hunt('2026-10-30')['touched'] == [
        'F-20261030-aaaa',
        'F-20261030-bbbb',
    ]
    assert sorted(second.findings()) == ['F-20261030-aaaa', 'F-20261030-bbbb']


def test_a_conflict_in_a_finding_is_undone_and_waits(
    tmp_path, ledger_dir, capsys
):
    remote, first, second = _two_clones(tmp_path, ledger_dir)
    first.save(_finding(claim='one claim'))
    first.commit('Update F-20261027-abcd')
    second.save(_finding(claim='another claim'))
    second.commit('Update F-20261027-abcd')

    out = capsys.readouterr().out
    assert 'committed but not pushed' in out
    assert 'findings/F-20261027-abcd.yaml' in out
    assert not second._rebasing()
    assert _git(second.path, 'log', '-1', '--format=%s').strip() == (
        'Update F-20261027-abcd'
    )
    assert second.get('F-20261027-abcd').claim == 'another claim'
    assert first.get('F-20261027-abcd').claim == 'one claim'

    # the next command warns again rather than leaving a rebase behind
    second.sync()
    assert 'could not pull' in capsys.readouterr().out
    assert not second._rebasing()


def test_a_rebase_left_in_progress_stops_the_next_command(
    tmp_path, ledger_dir
):
    _, first, second = _two_clones(tmp_path, ledger_dir)
    first.save(_finding(claim='one claim'))
    first.commit('Update F-20261027-abcd')
    second.save(_finding(claim='another claim'))
    _git(second.path, 'add', '--all')
    _git(second.path, 'commit', '-q', '-m', 'by hand')
    subprocess.run(
        ['git', '-C', second.path, 'pull', '-q', '--rebase', 'origin', 'main'],
        capture_output=True,
    )
    assert second._rebasing()

    with pytest.raises(LedgerError, match='rebase is in progress'):
        Ledger(second.path).sync()


def _rated(severity, confidence, rows=('a/x',), came_back=False):
    finding = _finding(
        severity=severity, confidence=confidence, came_back=came_back
    )
    finding.occurrences = [
        Occurrence(test='t', row=row, source='coupled') for row in rows
    ]
    return finding


@pytest.mark.parametrize(
    ('severity', 'confidence', 'rows', 'priority'),
    [
        ('S1', 'measured', ['a/x'], 'P1'),
        ('S1', 'inferred', [], 'P2'),
        ('S2', 'measured', ['a/x', 'b/y'], 'P1'),
        ('S2', 'measured', ['a/x'], 'P2'),
        ('S2', 'inferred', ['a/x', 'b/y'], 'P3'),
        ('S3', 'measured', ['a/x', 'b/y'], 'P2'),
        ('S3', 'measured', ['a/x'], 'P3'),
        ('S3', 'speculative', ['a/x'], 'P3'),
        ('S4', 'measured', ['a/x', 'b/y'], 'P4'),
    ],
)
def test_the_rubric_ranks_by_severity_confidence_and_rows(
    severity, confidence, rows, priority
):
    assert rubric_priority(_rated(severity, confidence, rows)) == priority


def test_a_bug_that_came_back_moves_up_one_level():
    assert rubric_priority(_rated('S3', 'inferred', came_back=True)) == 'P2'
    assert rubric_priority(_rated('S1', 'measured', came_back=True)) == 'P1'


def test_no_priority_until_severity_and_confidence_are_set():
    assert rubric_priority(_rated(None, 'measured')) is None
    assert rubric_priority(_rated('S2', None)) is None


def test_a_priority_set_by_hand_sticks():
    finding = _rated('S1', 'inferred')
    assert set_priority(finding) == 'priority=P2'
    assert set_priority(finding) is None

    finding.priority = 'P3'
    finding.priority_note = 'only with a non-default option'
    finding.occurrences.append(
        Occurrence(test='t', row='b/y', source='coupled')
    )
    finding.confidence = 'measured'
    assert set_priority(finding) is None
    assert finding.priority == 'P3'


def test_covered_gives_the_latest_date_or_the_latest_hunts_value(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    for day, cdash, sha in (
        ('2026-10-27', '2026-10-27', 'f368d66830'),
        ('2026-10-30', '2026-10-26', '27765dd1f5'),
    ):
        hunt = ledger.load_hunt(day)
        hunt['covered']['cdash'] = cdash
        hunt['covered']['review_omega'] = sha
        ledger.save_hunt(hunt)

    assert ledger.covered('cdash') == '2026-10-27'
    # a commit is not ordered by its hash
    assert ledger.covered('review_omega') == '27765dd1f5'


def _outside(severity, confidence, owner='omega', entry='langmuir'):
    finding = _rated(severity, confidence)
    finding.owner = owner
    finding.outside_v4 = entry
    return finding


@pytest.mark.parametrize(
    ('severity', 'confidence', 'priority'),
    [
        ('S1', 'measured', 'P2'),
        ('S1', 'inferred', 'P3'),
        ('S3', 'inferred', 'P3'),
        ('S4', 'measured', 'P4'),
    ],
)
def test_an_omega_bug_outside_v4_moves_down_but_not_below_p3(
    severity, confidence, priority
):
    finding = _outside(severity, confidence)
    assert rubric_priority(finding, {'langmuir'}) == priority


def test_outside_v4_counts_only_for_omega_and_listed_entries():
    assert rubric_priority(_outside('S1', 'inferred', owner='polaris')) == (
        'P2'
    )
    # an entry taken off the list no longer lowers the priority
    assert rubric_priority(_outside('S1', 'inferred'), set()) == 'P2'


def test_the_list_outside_v4_is_committed(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    entries = {
        'langmuir': {
            'description': 'Langmuir turbulence',
            'source': 'E3SM-Project/Omega#652',
            'since': '2026-10-30',
        }
    }
    ledger.save_outside_v4(entries)
    ledger.commit('Put langmuir on the list outside E3SM v4')

    assert ledger.outside_v4() == entries
    assert 'outside_v4.yaml' in _git(ledger_dir, 'ls-files')
