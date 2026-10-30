from bug_hunt_digest import build_digest, hold_line, rank
from bug_hunt_ledger import Finding, Key, Occurrence


def _finding(
    finding_id,
    priority,
    rows=(),
    created='2026-10-20',
    confidence='measured',
    **fields,
):
    finding = Finding(
        id=finding_id,
        keys=[Key(f'test-{finding_id}', 'run', None)],
        created=created,
        source='coupled',
        owner='omega',
        claim=f'Claim of {finding_id}',
        priority=priority,
        confidence=confidence,
        **fields,
    )
    finding.occurrences = [
        Occurrence(
            test=f'test-{finding_id}',
            row=row,
            source='coupled',
            first_failed='2026-10-07',
        )
        for row in rows
    ]
    return finding


def _findings(*items):
    return {item.id: item for item in items}


def test_rank_by_priority_then_rows_then_age():
    old = _finding('old', 'P2', rows=['a/x'], created='2026-10-01')
    wide = _finding('wide', 'P2', rows=['a/x', 'b/y'], created='2026-10-20')
    young = _finding('young', 'P2', rows=['a/x'], created='2026-10-21')
    urgent = _finding('urgent', 'P1', created='2026-10-25')

    assert [item.id for item in rank([young, old, wide, urgent])] == [
        'urgent',
        'wide',
        'old',
        'young',
    ]


def test_confidence_breaks_ties_before_the_id():
    # findings from one hunt share their age, so their IDs used to decide
    inferred = _finding('a-inferred', 'P3', confidence='inferred')
    measured = _finding('b-measured', 'P3', confidence='measured')

    assert [item.id for item in rank([inferred, measured])] == [
        'b-measured',
        'a-inferred',
    ]


def test_the_limit_holds_but_every_p1_is_shown():
    findings = _findings(
        *[_finding(f'p1-{index}', 'P1') for index in range(3)],
        *[_finding(f'p2-{index}', 'P2') for index in range(4)],
    )
    digest = build_digest(findings, limit=4, day='2026-10-27', header=[])

    assert digest.decisions == ['p1-0', 'p1-1', 'p1-2', 'p2-0']
    assert '3 more at P2' in digest.text


def test_p1_findings_beyond_the_limit_are_still_shown():
    p1 = [_finding(f'p1-{index}', 'P1') for index in range(7)]
    findings = _findings(*p1)
    digest = build_digest(findings, limit=5, day='2026-10-27', header=[])

    assert len(digest.decisions) == 7


def test_p4_findings_share_one_decision():
    findings = _findings(
        _finding('a', 'P2'),
        _finding('b', 'P4', theme='compiler warnings'),
        _finding('c', 'P4'),
        _finding('d', 'P4', confidence='speculative'),
    )
    digest = build_digest(findings, limit=5, day='2026-10-27', header=[])

    assert digest.decisions == ['a']
    assert digest.batched == ['b', 'c']
    assert 'one decision for all' in digest.text
    assert '- omega, compiler warnings: **Claim of b.** (b)' in digest.text
    assert '- omega, everything else: **Claim of c.** (c)' in digest.text
    assert '1 speculative' in digest.text


def test_untriaged_and_decided_findings_are_left_out():
    findings = _findings(
        _finding('new', None),
        _finding('filed', 'P1', status='tracked'),
        _finding('open', 'P3', proposed='batch', theme='logging'),
    )
    digest = build_digest(findings, limit=5, day='2026-10-27', header=['H.'])

    assert digest.decisions == ['open']
    assert digest.untriaged == ['new']
    assert digest.text.startswith('## Bug hunt 2026-10-27\n\nH.\n')
    assert 'Proposed: **batch (with logging)**.' in digest.text
    assert '1 not yet triaged; 1 tracked bugs unchanged.' in digest.text


def test_a_decision_says_where_and_since_when():
    finding = _finding(
        'x',
        'P1',
        rows=['chrysalis/intel', 'pm-cpu/gnu'],
        merged_between=['E3SM-Project/Omega#512'],
        dig='a debug build, about a node-hour',
        severity='S1',
    )
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    assert (
        '1. **Claim of x.**\n'
        '   P1, omega, measured; S1, wrong or lost results. (x)\n'
        '   - Fails on chrysalis/intel, pm-cpu/gnu since 2026-10-07. Merged '
        'in between: Omega#512.\n'
        '   - Proposed: **file (an issue in E3SM-Project/Omega, `priority: '
        'high`)**. Or: batch, log, dismiss, dig (a debug build, about a '
        'node-hour).\n'
    ) in digest.text


def test_a_decision_shows_the_case_for_it():
    evidence = (
        'The count is restored as the fill value,\n'
        'so the mean is wrong.\n'
        '\n'
        'TimeMeanOp.h:402\n'
        '   NumAccum = NumAccumData(0);\n'
    )
    finding = _finding(
        'x',
        'P2',
        where='TimeMeanOp.h:402',
        evidence=evidence,
        expected='A fresh averaging period',
    )
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    assert (
        '   - In `TimeMeanOp.h:402`.\n'
        '   - Evidence: The count is restored as the fill value, so the mean '
        'is wrong.\n'
        '   - Expected: A fresh averaging period.\n'
    ) in digest.text
    assert 'NumAccumData' not in digest.text


def test_long_evidence_is_cut_short():
    finding = _finding('x', 'P2', evidence=' '.join(['word'] * 400))
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    line = next(
        line for line in digest.text.splitlines() if 'Evidence:' in line
    )
    assert line.endswith('word ...')
    assert len(line) < 650


def test_a_proposed_dig_states_its_cost():
    finding = _finding('x', 'P2', proposed='dig', dig='one debug build')
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    assert (
        'Proposed: **dig (one debug build)**. Or: file (an issue in '
        'E3SM-Project/Omega, `priority: medium`), batch,'
    ) in digest.text


def test_an_owner_without_a_repository_is_asked_for_one():
    finding = _finding('x', 'P2')
    finding.owner = 'environment'
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    assert 'Proposed: **file (in a repository you name)**.' in digest.text


def test_missing_rows_name_the_rows():
    finding = _finding('x', 'P2', rows=['pm-gpu/gnugpu'])
    finding.keys = [Key('ctest nightly', 'missing', 'stopped reporting')]
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    assert '   - Rows: pm-gpu/gnugpu.\n' in digest.text


def test_changes_to_tracked_bugs_are_listed_once():
    finding = _finding(
        'x',
        'P1',
        status='tracked',
        links=['E3SM-Project/Omega#626'],
        changed='now fails on pm-cpu/gnu too',
    )
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-27', header=[]
    )

    assert (
        '- E3SM-Project/Omega#626: now fails on pm-cpu/gnu too.' in digest.text
    )
    assert '0 tracked bugs unchanged' in digest.text


def test_a_priority_set_by_hand_shows_its_note():
    finding = _finding(
        'hand',
        'P3',
        severity='S1',
        confidence='inferred',
        priority_note='only with a non-default option',
    )
    digest = build_digest(
        _findings(finding), limit=5, day='2026-10-30', header=[]
    )

    assert (
        'Priority set by hand (the rubric gives P2): only with a '
        'non-default option.'
    ) in digest.text


def test_rows_on_hold_are_noted_in_one_line():
    holds = {
        'frontier/craygnu': {'reason': 'out of hours.', 'since': '2026-10-30'},
        'frontier/craycray': {'reason': 'out of hours', 'since': '2026-10-30'},
        'pm-gpu/gnugpu': {'reason': 'a new driver', 'since': '2026-10-29'},
    }

    assert hold_line(holds) == (
        'On hold: pm-gpu/gnugpu since 2026-10-29, a new driver; '
        'frontier/craycray, frontier/craygnu since 2026-10-30, out of hours.'
    )


def test_a_finding_outside_v4_says_what_it_depends_on():
    finding = _finding(
        'langmuir',
        'P3',
        severity='S1',
        confidence='inferred',
        outside_v4='langmuir',
    )
    entries = {
        'langmuir': {
            'description': 'Langmuir turbulence',
            'source': 'E3SM-Project/Omega#652',
            'since': '2026-10-30',
        }
    }
    digest = build_digest(
        _findings(finding),
        limit=5,
        day='2026-10-30',
        header=[],
        outside_v4=entries,
    )

    assert (
        'Outside E3SM v4: Langmuir turbulence (E3SM-Project/Omega#652).'
    ) in digest.text
