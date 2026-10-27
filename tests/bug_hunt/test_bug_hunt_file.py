import bug_hunt_file
import pytest
from bug_hunt_file import (
    FileError,
    add_line,
    add_to_batch,
    batch_line,
    handoff,
    new_batch,
    render_issue,
    signature_for,
)
from bug_hunt_ledger import Finding, Key, Occurrence, split_evidence

TEST = 'PEM_Vmct.T62_oQU240.COMEGA-IAF'


def _finding(**fields):
    finding = Finding(
        id='F-20261027-abcd',
        keys=[Key(TEST, 'compare', 'm')],
        created='2026-10-27',
        source='coupled',
        owner='omega',
        claim='PEM tests fail their comparison on CPUs',
        priority='P1',
        **fields,
    )
    finding.occurrences = [
        Occurrence(
            test=TEST,
            row='chrysalis/intel',
            source='coupled',
            first_failed='2026-10-07',
            last_passed='2026-10-06',
            url='https://my.cdash.org/builds/1/tests',
        )
    ]
    return finding


def _complete(**fields):
    return _finding(
        evidence='45 of 367 fields had non-zero differences',
        reproduce='./create_test PEM_Vmct.T62_oQU240.COMEGA-IAF',
        expected='The runs on different task counts match bit for bit.',
        merged_between=['E3SM-Project/Omega#512'],
        **fields,
    )


def test_an_issue_needs_evidence_a_reproduction_and_what_was_expected():
    with pytest.raises(FileError, match='evidence, reproduce, expected'):
        render_issue(_finding(), signature='sig')


def test_render_issue():
    signature = signature_for('Claude Code', 'xylar')
    issue = render_issue(_complete(), signature)

    assert issue.repo == 'E3SM-Project/Omega'
    assert issue.title == 'PEM tests fail their comparison on CPUs'
    assert issue.labels == [
        'bug',
        'priority: high',
        'Coupled',
        'Chrysalis',
        'intel',
    ]
    body = issue.body
    assert body.startswith('PEM tests fail their comparison on CPUs.\n')
    assert (
        f'- `{TEST}` on chrysalis/intel since 2026-10-07 (last passed '
        f'2026-10-06)'
    ) in body
    assert 'E3SM-Project/Omega#512' in body
    assert 'Expected: The runs on different task counts match' in body
    assert body.rstrip().endswith(signature)
    assert "Posted by Claude Code on @xylar's behalf" in signature


def test_a_co_drafted_signature_names_the_developer_first():
    assert signature_for('Claude Code', 'xylar', co_drafted=True) == (
        '*Drafted by @xylar and Claude Code together*'
    )


def test_the_evidence_summary_is_in_the_body_and_excerpts_are_folded():
    finding = _complete()
    finding.evidence = (
        'The counts differ\nafter a restart.\n\nTimeMeanOp.h:402\n'
        '   NumAccum = NumAccumData(0);\n'
    )
    body = render_issue(finding, signature='sig').body

    summary = body.index('The counts differ after a restart.\n')
    assert summary < body.index('Expected:') < body.index('<details>')
    assert '   NumAccum = NumAccumData(0);\n```' in body
    assert 'The counts differ\n' not in body


def test_rows_that_stopped_reporting_say_so():
    finding = _complete()
    finding.keys = [Key('ctest nightly', 'missing', 'stopped reporting')]
    finding.occurrences = [
        Occurrence(
            test='ctest nightly',
            row='frontier/craygnu',
            source='ctest',
            first_failed='2026-10-22',
            last_passed='2026-10-21',
        )
    ]
    body = render_issue(finding, signature='sig').body

    assert (
        '- `ctest nightly` on frontier/craygnu: no results since '
        '2026-10-22 (last on 2026-10-21)'
    ) in body
    assert 'last passed' not in body


def test_evidence_with_no_excerpts_has_nothing_to_fold():
    body = render_issue(_complete(), signature='sig').body

    assert '45 of 367 fields had non-zero differences\n' in body
    assert '<details>' not in body


def test_a_title_can_be_given_and_a_long_claim_is_cut_at_a_word():
    issue = render_issue(_complete(), signature='sig', title='Short title')
    assert issue.title == 'Short title'

    finding = _complete()
    finding.claim = ' '.join(['word'] * 30)
    title = render_issue(finding, signature='sig').title
    assert title.endswith('word ...')
    assert len(title) <= 100


def test_split_evidence():
    assert split_evidence(None) == ('', '')
    assert split_evidence('One\nline.') == ('One line.', '')
    assert split_evidence('A.\n  \nB\n  C\n') == ('A.', 'B\n  C')


def test_an_owner_without_a_repository_needs_one_named():
    finding = _complete()
    finding.owner = 'environment'
    with pytest.raises(FileError, match='Pass --repo'):
        render_issue(finding, signature='sig')
    issue = render_issue(finding, signature='sig', repo='E3SM-Project/mache')
    assert issue.repo == 'E3SM-Project/mache'


def test_batch_line():
    assert batch_line(_finding()) == (
        '- [ ] PEM tests fail their comparison on CPUs. (chrysalis/intel) '
        '[evidence](https://my.cdash.org/builds/1/tests)'
    )


def test_a_line_is_added_before_the_signature():
    batch = new_batch('E3SM-Project/Omega', 'logging', ['- [ ] one'], 'sig')
    assert batch.title == 'Clean-up: logging'
    assert batch.labels == ['clean up', 'priority: low']
    assert '- [ ] one\n\n---\n' in batch.body

    body = add_line(batch.body, '- [ ] two')
    assert body.index('- [ ] two') > body.index('- [ ] one')
    assert body.index('- [ ] two') < body.index('\n---\n')
    assert body.rstrip().endswith('sig')


def test_a_line_is_added_to_a_body_with_no_signature():
    assert add_line('Intro\n\n- [ ] one\n', '- [ ] two') == (
        'Intro\n\n- [ ] one\n- [ ] two\n'
    )


def test_lines_are_added_to_a_batch_in_one_edit(monkeypatch):
    edits = []

    def fake_gh(args):
        with open(args[args.index('--body-file') + 1]) as handle:
            edits.append(handle.read())
        return ''

    monkeypatch.setattr(bug_hunt_file, 'gh', fake_gh)
    batch = new_batch('E3SM-Project/Omega', 'logging', ['- [ ] one'], 'sig')
    issue = {'number': 7, 'body': batch.body}

    ref = add_to_batch('E3SM-Project/Omega', issue, ['- [ ] two', '- [ ] 3'])

    assert ref == 'E3SM-Project/Omega#7'
    assert len(edits) == 1
    assert edits[0].index('- [ ] one') < edits[0].index('- [ ] two')
    assert edits[0].index('- [ ] two') < edits[0].index('- [ ] 3')


def test_handoff():
    prompt = handoff(_complete(), 'E3SM-Project/Omega#700')
    assert prompt.startswith(
        'Fix E3SM-Project/Omega#700 on a new branch from develop,'
    )
    assert f'Done when {TEST} passes on chrysalis/intel.' in prompt
