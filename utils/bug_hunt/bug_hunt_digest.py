"""
The digest: the few decisions a hunt asks of a developer
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
        The P4 findings asked about together

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


def build_digest(
    findings: Dict[str, Finding],
    limit: int,
    day: str,
    header: List[str],
    outside_v4: Optional[Dict[str, Dict[str, str]]] = None,
) -> Digest:
    """
    Write the digest of the open findings in a ledger

    Every P1 finding is shown.  P2 and P3 findings are shown up to
    ``limit`` decisions in all.  P4 findings that are not speculative are
    listed together, for one decision.  Speculative findings and those with
    no priority are only counted.

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
    first = [finding for finding in ranked if finding.priority == 'P1']
    middle = [
        finding for finding in ranked if finding.priority in ('P2', 'P3')
    ]
    batched = [finding for finding in ranked if finding.priority == 'P4']
    room = max(limit - len(first), 0)
    decisions = first + middle[:room]
    waiting = middle[room:]
    changed = sorted(
        (
            finding
            for finding in findings.values()
            if finding.changed and finding.status not in OPEN_STATUSES
        ),
        key=lambda finding: finding.id,
    )

    lines = [f'## Bug hunt {day}', ''] + header + ['']
    lines.append('### Decisions')
    lines.append('')
    if decisions:
        for index, finding in enumerate(decisions, start=1):
            lines.extend(_decision_lines(index, finding, outside_v4))
    else:
        lines.append('None.')
    lines.append('')
    if batched:
        lines.append('### For clean-up batches, one decision for all')
        lines.append('')
        lines.append(
            '`batch` adds each to the "Clean-up: <theme>" issue of its '
            "owner's repository; name any to leave out."
        )
        lines.append('')
        for finding in batched:
            theme = finding.theme or 'everything else'
            lines.append(
                f'- {finding.owner}, {theme}: **{_sentence(finding.claim)}** '
                f'({finding.id})'
            )
            lines.extend(
                f'  - {detail}' for detail in _details(finding, outside_v4)
            )
        lines.append('')
    if changed:
        lines.append('### Changed since the last hunt')
        lines.append('')
        for finding in changed:
            name = ', '.join(finding.links) if finding.links else finding.id
            lines.append(f'- {name}: {finding.changed}.')
        lines.append('')
    lines.append('### Not shown')
    lines.append('')
    lines.append(
        _not_shown(waiting, speculative, untriaged, findings, changed)
    )
    lines.append('')
    return Digest(
        text='\n'.join(lines),
        decisions=[finding.id for finding in decisions],
        batched=[finding.id for finding in batched],
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


def _decision_lines(
    index: int,
    finding: Finding,
    outside_v4: Optional[Dict[str, Dict[str, str]]] = None,
) -> List[str]:
    """
    The lines of one decision in the digest, with enough to decide on
    without the ledger
    """
    rating = f'{finding.priority}, {finding.owner}, '
    rating = f'{rating}{finding.confidence or "unrated"}'
    if finding.severity in SEVERITY_MEANINGS:
        meaning = SEVERITY_MEANINGS[finding.severity]
        rating = f'{rating}; {finding.severity}, {meaning}'
    lines = [
        f'{index}. **{_sentence(finding.claim)}**',
        f'   {rating}. ({finding.id})',
    ]
    lines.extend(f'   - {detail}' for detail in _details(finding, outside_v4))
    lines.append(f'   - {_answers(finding)}')
    return lines


def _details(
    finding: Finding, outside_v4: Optional[Dict[str, Dict[str, str]]] = None
) -> List[str]:
    """
    Why a priority was set by hand, what outside E3SM v4 the finding
    depends on, where it is seen, the case for it and what was expected
    """
    details = []
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
    if finding.theme:
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
    if finding.merged_between:
        merges = ', '.join(
            merge.replace('E3SM-Project/', '')
            for merge in finding.merged_between
        )
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


def _sentence(text: Optional[str]) -> str:
    """A claim as a sentence, ending in a period"""
    text = (text or '').strip()
    if text and text[-1] not in '.!?':
        text = f'{text}.'
    return text
