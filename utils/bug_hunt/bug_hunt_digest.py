"""
The digest: the few decisions a hunt asks of a developer
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from bug_hunt_file import PRIORITY_LABELS, REPOS
from bug_hunt_ledger import (
    ACTIONS,
    OPEN_STATUSES,
    Finding,
    rubric_priority,
    split_evidence,
)

#: the order findings are shown in
PRIORITY_ORDER = {'P1': 0, 'P2': 1, 'P3': 2, 'P4': 3}
CONFIDENCE_ORDER = {'measured': 0, 'inferred': 1, 'speculative': 2}

#: what each severity means, from the rubric in AGENTS.md
SEVERITY_MEANINGS = {
    'S1': 'wrong or lost results',
    'S2': 'a failure in regular testing',
    'S3': 'another failure',
    'S4': 'cosmetic',
}

#: the most characters of evidence a decision shows
EVIDENCE_LIMIT = 600

#: the priorities whose findings go to clean-up batches
BATCH_PRIORITIES = ('P3', 'P4')

#: the short names of the repositories, for the heading of a batch
REPO_NAMES = {'E3SM-Project/Omega': 'Omega', 'E3SM-Project/polaris': 'Polaris'}


@dataclass
class Digest:
    """
    A hunt's digest

    Attributes
    ----------
    text : str
        The digest, as Markdown

    decisions : list of str
        The findings asked about one by one, in order

    batched : list of str
        The findings asked about in batches, one decision for each owner
        and theme

    untriaged : list of str
        Open findings with no priority yet, which the digest leaves out
    """

    text: str
    decisions: List[str] = field(default_factory=list)
    batched: List[str] = field(default_factory=list)
    untriaged: List[str] = field(default_factory=list)


def rank(findings: List[Finding]) -> List[Finding]:
    """
    Order findings by priority, then by how many rows they fail on, then by
    age, then by confidence

    Parameters
    ----------
    findings : list of bug_hunt_ledger.Finding
        Findings that have a priority

    Returns
    -------
    ranked : list of bug_hunt_ledger.Finding
        The findings, most pressing first
    """
    return sorted(
        findings,
        key=lambda finding: (
            PRIORITY_ORDER[finding.priority or 'P4'],
            -len(finding.rows),
            finding.created,
            CONFIDENCE_ORDER.get(finding.confidence or '', 3),
            finding.id,
        ),
    )


@dataclass
class Decision:
    """
    One decision in a digest: a finding of its own, or the partners in one
    clean-up batch

    Attributes
    ----------
    findings : list of bug_hunt_ledger.Finding
        The finding, or the batch's findings, most pressing first

    theme : str, optional
        The batch's theme, if it is a batch

    joins : str, optional
        The open batch issue the findings would join, if there is one
    """

    findings: List[Finding]
    theme: Optional[str] = None
    joins: Optional[str] = None

    @property
    def is_batch(self) -> bool:
        """Whether the decision is a batch"""
        return self.theme is not None


def decision_cost(decision: Decision) -> int:
    """
    How many of a digest's decisions a decision counts as

    A batch counts as one decision, however many findings it holds.  The
    rule lives only here, so that it is easy to change.
    """
    return 1


def build_digest(
    findings: Dict[str, Finding],
    limit: int,
    day: str,
    header: List[str],
    outside_v4: Optional[Dict[str, Dict[str, str]]] = None,
    ready_to_close: Optional[List[str]] = None,
) -> Digest:
    """
    Write the digest of the open findings in a ledger

    Every P1 finding is shown.  Other findings are shown up to ``limit``
    decisions in all.  A P3 or P4 finding is never shown apart from its
    partners, the other findings with its owner and theme: together they
    are one decision, ranked by the most pressing of them.  A finding with
    no partner, in the digest or in an open batch, is proposed as an issue
    of its own.  Speculative findings and those with no priority are only
    counted.

    Parameters
    ----------
    findings : dict of str to bug_hunt_ledger.Finding
        Every finding in the ledger

    limit : int
        The most decisions to ask for, besides P1 findings

    day : str
        The date of the hunt

    header : list of str
        Lines saying what the hunt covered, such as the commits and the
        nights harvested

    outside_v4 : dict of str to dict, optional
        The features and options outside E3SM v4, from
        ``Ledger.outside_v4()``, to describe the entry a finding depends on

    ready_to_close : list of str, optional
        Clean-up batches whose every line is done, from ``match --refresh``

    Returns
    -------
    digest : bug_hunt_digest.Digest
        The digest and the findings it asks about
    """
    open_findings = [
        finding
        for finding in findings.values()
        if finding.status in OPEN_STATUSES
    ]
    untriaged = sorted(
        finding.id for finding in open_findings if finding.priority is None
    )
    speculative = [
        finding
        for finding in open_findings
        if finding.priority is not None and finding.confidence == 'speculative'
    ]
    ranked = rank(
        [
            finding
            for finding in open_findings
            if finding.priority is not None
            and finding.confidence != 'speculative'
        ]
    )
    shown: List[Decision] = []
    waiting: List[Finding] = []
    room = limit
    for decision in _decisions(ranked, findings):
        if decision.findings[0].priority == 'P1':
            shown.append(decision)
            room -= decision_cost(decision)
    for decision in _decisions(ranked, findings):
        if decision.findings[0].priority == 'P1':
            continue
        cost = decision_cost(decision)
        if cost <= room:
            shown.append(decision)
            room -= cost
        else:
            waiting.extend(decision.findings)
    changed = sorted(
        (
            finding
            for finding in findings.values()
            if finding.changed and finding.status not in OPEN_STATUSES
        ),
        key=lambda finding: finding.id,
    )
    closed = sorted(
        (
            finding
            for finding in findings.values()
            if finding.status in ('tracked', 'batched')
            and finding.closed_upstream is not None
        ),
        key=lambda finding: finding.id,
    )

    lines = [f'## Bug hunt {day}', ''] + header + ['']
    lines.append('### Decisions')
    lines.append('')
    if shown:
        for index, decision in enumerate(shown, start=1):
            if decision.is_batch:
                lines.extend(_batch_lines(index, decision, outside_v4))
            else:
                lines.extend(
                    _decision_lines(index, decision.findings[0], outside_v4)
                )
    else:
        lines.append('None.')
    lines.append('')
    if changed:
        lines.append('### Changed since the last hunt')
        lines.append('')
        for finding in changed:
            links = f' ({", ".join(finding.links)})' if finding.links else ''
            lines.append(f'- {finding.label}{links}: {finding.changed}.')
        lines.append('')
    if closed:
        lines.append('### Closed upstream, not failing since')
        lines.append('')
        lines.append(
            'Each is set `fixed` once each link, or its line in a batch, is '
            'checked to have been closed by a fix.'
        )
        lines.append('')
        for finding in closed:
            lines.append(
                f'- {finding.label} ({", ".join(finding.links)}): closed by '
                f'{finding.closed_upstream}. ({finding.id})'
            )
        lines.append('')
    if ready_to_close:
        lines.append('### Batches ready to close')
        lines.append('')
        lines.append(
            'Every line is checked off or struck out.  Each is closed once '
            'you say so; a later finding in the same area starts a new '
            'batch.'
        )
        lines.append('')
        lines.extend(f'- {ref}' for ref in ready_to_close)
        lines.append('')
    lines.append('### Not shown')
    lines.append('')
    lines.append(
        _not_shown(waiting, speculative, untriaged, findings, changed + closed)
        + _digging(findings)
    )
    lines.append('')
    return Digest(
        text='\n'.join(lines),
        decisions=[
            decision.findings[0].id
            for decision in shown
            if not decision.is_batch
        ],
        batched=[
            finding.id
            for decision in shown
            if decision.is_batch
            for finding in decision.findings
        ],
        untriaged=untriaged,
    )


def hold_line(holds: Dict[str, Dict[str, str]]) -> str:
    """
    One line saying which rows are on hold, since when and why

    Parameters
    ----------
    holds : dict of str to dict
        The rows on hold, from ``Ledger.holds()``

    Returns
    -------
    line : str
        Such as ``On hold: frontier/craygnu since 2026-10-30, out of
        compute hours.``
    """
    groups: Dict[tuple, List[str]] = {}
    for row in sorted(holds):
        hold = holds[row]
        key = (str(hold['since']), hold['reason'].strip().rstrip('.'))
        groups.setdefault(key, []).append(row)
    parts = [
        f'{", ".join(rows)} since {since}, {reason}'
        for (since, reason), rows in sorted(groups.items())
    ]
    return f'On hold: {"; ".join(parts)}.'


def _decisions(
    ranked: List[Finding], findings: Dict[str, Finding]
) -> List[Decision]:
    """
    The decisions for ranked findings, most pressing first: a P3 or P4
    finding goes with its partners, the others with its owner and theme,
    and with the open batch for them if there is one
    """
    partners: Dict[Tuple[str, str], List[Finding]] = {}
    for finding in ranked:
        key = _batch_key(finding)
        if key is not None:
            partners.setdefault(key, []).append(finding)
    open_batches = _open_batches(findings)
    decisions = []
    done = set()
    for finding in ranked:
        key = _batch_key(finding)
        if key is None or (
            len(partners[key]) == 1 and key not in open_batches
        ):
            decisions.append(Decision([finding]))
        elif key not in done:
            done.add(key)
            decisions.append(
                Decision(
                    partners[key], theme=key[1], joins=open_batches.get(key)
                )
            )
    return decisions


def _batch_key(finding: Finding) -> Optional[Tuple[str, str]]:
    """The owner and theme a finding is batched by, if it goes to a batch"""
    if finding.priority not in BATCH_PRIORITIES or not finding.theme:
        return None
    return (finding.owner or 'unknown', finding.theme)


def _open_batches(findings: Dict[str, Finding]) -> Dict[Tuple[str, str], str]:
    """
    The batch issue each owner and theme has open, from the findings
    already in it
    """
    batches: Dict[Tuple[str, str], str] = {}
    for finding in findings.values():
        if finding.status != 'batched' or not finding.theme:
            continue
        repo = REPOS.get(finding.owner or '')
        refs = [
            link
            for link in finding.links
            if repo is not None and link.startswith(f'{repo}#')
        ]
        if refs:
            batches.setdefault((finding.owner, finding.theme), refs[0])
    return batches


def _batch_lines(
    index: int,
    decision: Decision,
    outside_v4: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[str]:
    """
    The lines of a batch decision: the theme, where the batch goes and what
    its findings share, then each finding as fully as a decision of its own
    """
    first = decision.findings[0]
    repo = REPOS.get(first.owner or '') or 'a repository you name'
    title = f'Clean-up: {decision.theme}'
    where = REPO_NAMES.get(repo, repo)
    if decision.joins is not None:
        goes = f'Joins "{title}", {decision.joins}.'
    else:
        goes = f'Starts "{title}" in {repo}.'
    lines = [f'{index}. **Batch: {decision.theme} in {where}.** {goes}']
    shared = _shared(decision.findings)
    if shared:
        lines[0] = f'{lines[0]} {shared}'
    for finding in decision.findings:
        lines.append(
            f'   - **{_headline(finding)}** {_rating(finding, owner=False)}. '
            f'({finding.id})'
        )
        lines.extend(
            f'     - {detail}' for detail in _details(finding, outside_v4)
        )
    lines.append(
        '   - Proposed: **batch all**. Or: name any to file on its own, '
        'log, dismiss or dig.'
    )
    return lines


def _shared(batch: List[Finding]) -> str:
    """One sentence on the files a batch's findings are in"""
    files = sorted(
        {finding.where.split(':')[0] for finding in batch if finding.where}
    )
    if not files:
        return ''
    count = 'Both are' if len(batch) == 2 else f'All {len(batch)} are'
    listed = ', '.join(f'`{name}`' for name in files)
    return f'{count} in {listed}.'


def _rating(finding: Finding, owner: bool = True) -> str:
    """A finding's priority, owner, confidence and severity"""
    rating = f'{finding.priority}, '
    if owner:
        rating = f'{rating}{finding.owner}, '
    rating = f'{rating}{finding.confidence or "unrated"}'
    if finding.severity in SEVERITY_MEANINGS:
        meaning = SEVERITY_MEANINGS[finding.severity]
        rating = f'{rating}; {finding.severity}, {meaning}'
    return rating


def _decision_lines(
    index: int,
    finding: Finding,
    outside_v4: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[str]:
    """
    The lines of one decision in the digest, with enough to decide on
    without the ledger
    """
    lines = [
        f'{index}. **{_headline(finding)}**',
        f'   {_rating(finding)}. ({finding.id})',
    ]
    lines.extend(f'   - {detail}' for detail in _details(finding, outside_v4))
    lines.append(f'   - {_answers(finding)}')
    return lines


def _details(
    finding: Finding, outside_v4: Optional[Dict[str, Dict[str, str]]] = None
) -> List[str]:
    """
    Whether the failure has ended, why a priority was set by hand, what
    outside E3SM v4 the finding depends on, where it is seen, the case for
    it and what was expected
    """
    details = []
    if finding.ended is not None:
        merges = ''
        if finding.ended_between:
            listed = ', '.join(merge for merge in finding.ended_between)
            merges = f' Merged before it passed: {listed}.'
        details.append(
            f'Ended: it passes since {finding.ended}, and nothing found '
            f'explains why, so it ranks one level lower.{merges}'
        )
    if finding.outside_v4 is not None:
        entry = (outside_v4 or {}).get(finding.outside_v4)
        if entry is None:
            details.append(f'Outside E3SM v4: {finding.outside_v4}.')
        else:
            details.append(
                f'Outside E3SM v4: {entry["description"].rstrip(".")} '
                f'({entry["source"]}).'
            )
    if finding.proposed == 'file':
        if finding.not_duplicates:
            checked = '; '.join(
                f'{entry["ref"]}, {entry["why"].rstrip(".")}'
                for entry in finding.not_duplicates
            )
            details.append(f'Not the same as: {checked}.')
        elif finding.matched is None:
            details.append('Not yet matched against the open issues.')
    if finding.priority_note is not None:
        rubric = rubric_priority(finding, outside_v4)
        gives = f' (the rubric gives {rubric})' if rubric else ''
        details.append(
            f'Priority set by hand{gives}: {_sentence(finding.priority_note)}'
        )
    seen = _seen(finding)
    if seen:
        details.append(seen)
    evidence = _opening(finding.evidence)
    if evidence:
        details.append(f'Evidence: {evidence}')
    if finding.expected:
        details.append(f'Expected: {_sentence(finding.expected)}')
    return details


def _answers(finding: Finding) -> str:
    """The proposed answer and the others, saying what each would do"""
    proposed = finding.proposed or 'file'
    described = {action: action for action in ACTIONS}
    repo = REPOS.get(finding.owner)
    label = PRIORITY_LABELS.get(finding.priority or '')
    if repo is None:
        described['file'] = 'file (in a repository you name)'
    elif label is not None:
        described['file'] = f'file (an issue in {repo}, `{label}`)'
    if finding.theme and finding.priority in BATCH_PRIORITIES:
        # shown alone, so nothing else is waiting for its batch
        if proposed == 'batch':
            proposed = 'file'
        described['file'] = (
            f'{described["file"]}, since nothing else in {finding.theme} '
            f'is waiting'
        )
    elif finding.theme:
        described['batch'] = f'batch (with {finding.theme})'
    if finding.dig:
        described['dig'] = f'dig ({finding.dig})'
    others = ', '.join(
        described[action] for action in ACTIONS if action != proposed
    )
    return f'Proposed: **{described[proposed]}**. Or: {others}.'


def _opening(text: Optional[str]) -> str:
    """
    The first paragraph of the evidence, on one line, cut short if it is
    long
    """
    paragraph, _ = split_evidence(text)
    if len(paragraph) > EVIDENCE_LIMIT:
        paragraph = f'{paragraph[:EVIDENCE_LIMIT].rsplit(" ", 1)[0]} ...'
    return paragraph


def _seen(finding: Finding) -> str:
    """Where and since when a finding fails, in one sentence"""
    if not finding.occurrences:
        if finding.where:
            return f'In `{finding.where}`.'
        return ''
    rows = ', '.join(finding.rows)
    if all(key.phase == 'missing' for key in finding.keys):
        return f'Rows: {rows}.'
    firsts = [
        occurrence.first_failed
        for occurrence in finding.occurrences
        if occurrence.first_failed
    ]
    sentence = f'Fails on {rows}'
    if firsts:
        sentence = f'{sentence} since {min(firsts)}'
    if any(occurrence.intermittent for occurrence in finding.occurrences):
        sentence = f'{sentence}, intermittently'
    sentence = f'{sentence}.'
    if finding.caused_by:
        sentence = f'{sentence} Introduced by {finding.caused_by}.'
    elif finding.merged_between:
        merges = ', '.join(finding.merged_between)
        sentence = f'{sentence} Merged in between: {merges}.'
    if finding.links:
        sentence = f'{sentence} See {", ".join(finding.links)}.'
    return sentence


def _not_shown(waiting, speculative, untriaged, findings, changed) -> str:
    """The counts of findings the digest does not ask about"""
    tracked = [
        finding
        for finding in findings.values()
        if finding.status == 'tracked' and finding not in changed
    ]
    parts = []
    by_priority: Dict[str, int] = {}
    for finding in waiting:
        priority = finding.priority or 'P4'
        by_priority[priority] = by_priority.get(priority, 0) + 1
    for priority in sorted(by_priority):
        parts.append(f'{by_priority[priority]} more at {priority}')
    if speculative:
        parts.append(f'{len(speculative)} speculative')
    if untriaged:
        parts.append(f'{len(untriaged)} not yet triaged')
    parts.append(f'{len(tracked)} tracked bugs unchanged')
    return '; '.join(parts) + '.'


def _headline(finding: Finding) -> str:
    """A finding's name and claim, as one sentence"""
    claim = _sentence(finding.claim)
    if not finding.name:
        return claim
    return f'{finding.name}: {claim}'


def _digging(findings: Dict[str, Finding]) -> str:
    """One sentence counting the digs that wait, by what they wait for"""
    by_reason: Dict[str, int] = {}
    for finding in findings.values():
        if finding.status == 'digging':
            reason = (finding.waiting_for or 'something').strip().rstrip('.')
            by_reason[reason] = by_reason.get(reason, 0) + 1
    if not by_reason:
        return ''
    parts = [
        f'{count} dig{"s" if count > 1 else ""} waiting for {reason}'
        for reason, count in sorted(by_reason.items())
    ]
    return f' {"; ".join(parts)}.'


def _sentence(text: Optional[str]) -> str:
    """A claim as a sentence, ending in a period"""
    text = (text or '').strip()
    if text and text[-1] not in '.!?':
        text = f'{text}.'
    return text
