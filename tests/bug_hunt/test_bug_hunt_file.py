import bug_hunt_file
import pytest
from bug_hunt_file import (
    FileError,
    add_line,
    add_to_batch,
    batch_done,
    batch_line,
    full_refs,
    handoff,
    line_done,
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
        '[evidence](https://my.cdash.org/builds/1/tests) '
        '<!-- F-20261027-abcd -->'
    )


def test_a_line_is_added_before_the_signature():
    batch = new_batch('E3SM-Project/Omega', 'KPP', ['- [ ] one'], 'sig')
    assert batch.title == 'Clean-up: KPP'
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
    batch = new_batch('E3SM-Project/Omega', 'KPP', ['- [ ] one'], 'sig')
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


def test_each_row_seen_links_to_its_cdash_build():
    finding = _complete()
    finding.occurrences[0].url = 'https://my.cdash.org/builds/4499162/tests'
    body = render_issue(finding, signature='sig').body
    assert (
        '(last passed 2026-10-06) '
        '([CDash](https://my.cdash.org/builds/4499162/tests))'
    ) in body


def test_short_references_are_written_in_full_outside_code():
    text = (
        'Since Omega#673 and polaris#917, not E3SM-Project/Omega#640.\n'
        '```\nOmega#1 stays as logged\n```\n'
    )
    assert full_refs(text) == (
        'Since E3SM-Project/Omega#673 and E3SM-Project/polaris#917, not '
        'E3SM-Project/Omega#640.\n'
        '```\nOmega#1 stays as logged\n```\n'
    )


def test_an_issue_links_the_references_in_its_claim():
    finding = _complete()
    finding.claim = 'Fails since Omega#673'
    body = render_issue(finding, signature='sig').body
    assert body.startswith('Fails since E3SM-Project/Omega#673.')


def test_a_new_test_says_it_failed_from_its_first_night():
    finding = _complete()
    occurrence = finding.occurrences[0]
    occurrence.last_passed = None
    occurrence.first_ran = occurrence.first_failed
    body = render_issue(finding, signature='sig').body
    assert 'since 2026-10-07, the first night it ran' in body
    assert 'last passed' not in body
    assert 'Merged just before the first failure: ' in body


def test_an_issue_names_the_merge_that_introduced_the_failure():
    finding = _complete(caused_by='E3SM-Project/Omega#512')
    body = render_issue(finding, signature='sig').body
    assert 'Introduced by E3SM-Project/Omega#512.' in body
    assert 'Merged between' not in body


def test_posts_say_the_bug_hunter_filed_them_only_once_turned_on(
    monkeypatch,
):
    assert 'bug hunter' not in signature_for('Claude Code', 'xylar')
    monkeypatch.setattr(bug_hunt_file, 'SIGN_AS_HUNTER', True)
    for co_drafted in (False, True):
        signature = signature_for('Claude Code', 'xylar', co_drafted)
        assert signature.endswith(bug_hunt_file.HUNTER_LINE)


def test_a_batch_names_its_area_and_promises_no_single_pull_request():
    issue = new_batch(
        'E3SM-Project/polaris', 'ice shelves', ['- [ ] a line'], 'sig'
    )
    assert issue.body.startswith(
        'Small bugs in ice shelves, likely fixed together.'
    )
    assert 'one pull request' not in issue.body


def _batched(finding_id, claim):
    finding = _complete()
    finding.id = finding_id
    finding.claim = claim
    return finding


def test_a_batch_line_is_found_again_and_read_as_done_or_not():
    first = _batched('F-1', 'The first small bug')
    second = _batched('F-2', 'The second small bug')
    body = new_batch(
        'E3SM-Project/polaris',
        'ice shelves',
        [batch_line(first), batch_line(second)],
        'sig',
    ).body
    assert line_done(body, first) is False
    assert not batch_done(body)

    body = body.replace('- [ ] The first', '- [x] The first')
    assert line_done(body, first) is True
    assert line_done(body, second) is False

    # struck out as not a bug counts as done
    body = body.replace('- [ ] The second', '- [ ] ~~The second')
    assert line_done(body, second) is True
    assert batch_done(body)


def test_a_line_from_before_the_markers_is_found_by_its_claim():
    finding = _batched('F-3', 'An old small bug')
    body = '- [x] An old small bug. (src/a.cpp)\n'
    assert line_done(body, finding) is True
    assert line_done('- [ ] Something else.\n', finding) is None


def test_a_new_batch_links_the_last_closed_one():
    issue = new_batch(
        'E3SM-Project/polaris',
        'ice shelves',
        ['- [ ] a line'],
        'sig',
        follows='E3SM-Project/polaris#964',
    )
    assert issue.body.startswith(
        'Small bugs in ice shelves, likely fixed together. Follows '
        'E3SM-Project/polaris#964.'
    )
