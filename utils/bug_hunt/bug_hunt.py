#!/usr/bin/env python3
"""
Hunt for bugs in Omega and Polaris

See README.md for the workflow and AGENTS.md for the instructions agents
follow.  Run this from a shell with a Polaris load script sourced.
"""

import argparse
import datetime
import io
import os
import re
import subprocess
import sys
from dataclasses import asdict
from typing import Dict, List

# the modules the PR testing utilities share
sys.path.insert(
    1,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'pr_testing',
    ),
)

import bug_hunt_file  # noqa: E402
from bug_hunt_cdash import (  # noqa: E402
    CDash,
    CDashError,
    read_kinds,
    shift_night,
)
from bug_hunt_config import read_config  # noqa: E402
from bug_hunt_digest import build_digest, hold_line  # noqa: E402
from bug_hunt_harvest import (  # noqa: E402
    DEFAULT_LOOKBACK,
    harvest_cdash,
    harvest_local,
)
from bug_hunt_keys import location_key, normalize_message  # noqa: E402
from bug_hunt_ledger import (  # noqa: E402
    ACTIONS,
    CONFIDENCES,
    OPEN_STATUSES,
    OWNERS,
    PRIORITIES,
    SEVERITIES,
    STATUSES,
    Finding,
    Key,
    Ledger,
    LedgerError,
    record_answer,
    rubric_priority,
    set_priority,
    today,
)
from bug_hunt_match import candidates, refresh  # noqa: E402
from bug_hunt_sources import cime_failures, polaris_failures  # noqa: E402
from pr_test_github import GitHubError, get_user  # noqa: E402
from ruamel.yaml import YAML  # noqa: E402

#: the errors that are reported as a message rather than a traceback
EXPECTED_ERRORS = (
    bug_hunt_file.FileError,
    CDashError,
    GitHubError,
    LedgerError,
    ValueError,
)

#: how many nights a first harvest reads, when no hunt has harvested before
FIRST_HARVEST_NIGHTS = 14


def main():
    """Run a subcommand of the bug hunter"""
    args = _parse_args()
    try:
        args.func(args)
    except EXPECTED_ERRORS as exc:
        print(f'\nError: {exc}', file=sys.stderr)
        sys.exit(1)


def _harvest(args):
    config, ledger = _setup(args)
    day = today()
    if not args.no_cdash:
        sources = read_kinds()
        last = args.until or day
        since = args.since
        if since is None:
            covered = ledger.covered('cdash')
            since = (
                shift_night(covered, 1)
                if covered is not None
                else shift_night(last, -FIRST_HARVEST_NIGHTS)
            )
        cdash = CDash(sources['project'], config.cache, sources['kinds'])
        project = sources['project']
        print(f'Harvesting CDash ({project}) from {since} to {last}')
        summary = harvest_cdash(
            ledger,
            cdash,
            sources['kinds'],
            since,
            last,
            omega_repo=config.omega_repo,
            lookback=args.lookback,
            day=day,
        )
        _print_summary(ledger, summary)
    if args.local:
        roots = args.roots or config.harvest_roots
        if not roots:
            raise ValueError(
                'No directories to harvest: set harvest_roots in [bug_hunt] '
                'or pass --roots.'
            )
        print(f'Harvesting runs under {", ".join(roots)}')
        failures = polaris_failures(roots) + cime_failures(roots)
        summary = harvest_local(ledger, failures, day=day)
        _print_summary(ledger, summary)
    ledger.commit(f'Harvest on {day}')


def _park(args):
    config = read_config(args.config_file, ledger=args.ledger)
    test, phase = location_key(args.where)
    message = normalize_message(args.claim)
    key = Key(test, phase, message)
    evidence = _read_text(args.evidence)
    if args.fixing is not None:
        status = 'fixing'
    elif args.source == 'review':
        status = 'new'
    else:
        status = 'parked'

    if config.ledger is None:
        unrecorded = Finding(
            id='F-unrecorded',
            keys=[key],
            created=today(),
            source=args.source,
            owner=args.owner,
            claim=args.claim,
            where=args.where,
            confidence=args.confidence,
            status=status,
            fixing=args.fixing,
            evidence=evidence,
            context=args.context,
        )
        print(
            'No ledger is set up, so this finding is not recorded.  Put it '
            'in your report:\n'
        )
        print(_dump(asdict(unrecorded)))
        return

    ledger = Ledger(config.ledger)
    ledger.sync()
    findings = ledger.findings()
    finding = ledger.find(findings, test, phase, message, 'code')
    day = today()
    if finding is None:
        finding = Finding(
            id=ledger.new_id(key, day),
            keys=[key],
            created=day,
            source=args.source,
            owner=args.owner,
            claim=args.claim,
            where=args.where,
            confidence=args.confidence,
            severity=args.severity,
            expected=args.expected,
            reproduce=args.reproduce,
            status=status,
            fixing=args.fixing,
            evidence=evidence,
            context=args.context,
        )
        outside_v4 = ledger.outside_v4()
        if args.outside_v4 is not None:
            if args.outside_v4 not in outside_v4:
                raise ValueError(
                    f'"{args.outside_v4}" is not in outside_v4.yaml.'
                )
            finding.outside_v4 = args.outside_v4
        set_priority(finding, outside_v4)
        finding.note(f'recorded from {args.source}', day)
        verb = 'Recorded'
    else:
        finding.note(f'seen again from {args.source}: {args.context}', day)
        verb = 'Added to'
    ledger.save(finding)
    hunt = ledger.load_hunt(day)
    if finding.id not in hunt['touched']:
        hunt['touched'].append(finding.id)
    ledger.save_hunt(hunt)
    ledger.commit(f'{verb} {finding.id}')
    print(f'{verb} {finding.id}: {finding.claim}')


def _hold(args):
    _, ledger = _setup(args)
    day = today()
    holds = ledger.holds()
    for row in args.rows:
        if '/' not in row:
            raise ValueError(f'"{row}" is not a <machine>/<compiler> row.')
    if args.release:
        unknown = [row for row in args.rows if row not in holds]
        if unknown:
            raise ValueError(f'Not on hold: {", ".join(unknown)}')
        for row in args.rows:
            del holds[row]
        message = f'Take {", ".join(args.rows)} off hold'
    else:
        if args.reason is None:
            raise ValueError('A row on hold needs a --reason.')
        for row in args.rows:
            holds[row] = {'reason': args.reason, 'since': day}
        message = f'Put {", ".join(args.rows)} on hold'
    ledger.save_holds(holds)
    ledger.commit(message)
    print(message)


def _outside_v4(args):
    _, ledger = _setup(args)
    day = today()
    entries = ledger.outside_v4()
    if args.name is None:
        for name, entry in entries.items():
            print(
                f'{name}: {entry["description"]} ({entry["source"]}, '
                f'{entry["since"]})'
            )
        return
    if args.remove:
        if args.name not in entries:
            raise ValueError(f'"{args.name}" is not in outside_v4.yaml.')
        del entries[args.name]
        message = f'Take {args.name} off the list outside E3SM v4'
    else:
        if args.description is None or args.source is None:
            raise ValueError(
                'An entry outside E3SM v4 needs a --description and a '
                '--source.'
            )
        entries[args.name] = {
            'description': args.description,
            'source': args.source,
            'since': day,
        }
        message = f'Put {args.name} on the list outside E3SM v4'
    ledger.save_outside_v4(entries)
    # findings that depend on the entry are ranked again
    for finding in ledger.findings().values():
        if finding.outside_v4 == args.name:
            change = set_priority(finding, entries)
            if change is not None:
                finding.note(f'{change}, after: {message}', day)
                ledger.save(finding)
                print(f'  {finding.id}: {change}')
    ledger.commit(message)
    print(message)


def _match(args):
    _, ledger = _setup(args)
    findings = ledger.findings()
    day = today()
    if args.refresh:
        changed = []
        for finding in findings.values():
            if finding.status not in OPEN_STATUSES and finding.links:
                change = refresh(finding)
                if change is not None and change != finding.changed:
                    finding.changed = change
                    finding.came_back = True
                    raised = set_priority(finding, ledger.outside_v4())
                    if raised is not None:
                        change = f'{change}; {raised}'
                    finding.note(change, day)
                    ledger.save(finding)
                    changed.append(finding.id)
        ledger.commit(f'Refresh links on {day}')
        print(f'{len(changed)} tracked findings changed: {changed}')
        return

    ids = args.ids or [
        finding.id
        for finding in findings.values()
        if finding.status in OPEN_STATUSES and not finding.links
    ]
    for finding_id in ids:
        finding = findings.get(finding_id) or ledger.get(finding_id)
        print(f'\n{finding.id}: {finding.claim}')
        for key in finding.keys:
            print(f'  key: {key.text()}')
        if finding.rows:
            print(f'  rows: {", ".join(finding.rows)}')
        found = candidates(finding)
        finding.matched = day
        ledger.save(finding)
        reasons = {
            entry['ref']: entry['why'] for entry in finding.not_duplicates
        }
        if not found:
            print('  no candidates')
        for candidate in found:
            closed = f', closed {candidate.closed}' if candidate.closed else ''
            if candidate.ref in finding.links:
                closed = f'{closed}; linked'
            elif candidate.ref in reasons:
                closed = f'{closed}; not the same: {reasons[candidate.ref]}'
            print(
                f'  {candidate.ref} ({candidate.kind}, {candidate.state}'
                f'{closed}): {candidate.title}'
            )
    ledger.commit(f'Match {", ".join(ids)}')


def _update(args):
    _, ledger = _setup(args)
    day = today()
    finding = ledger.get(args.id)
    changes = []
    for name in (
        'owner',
        'severity',
        'confidence',
        'status',
        'claim',
        'where',
        'expected',
        'reproduce',
        'theme',
        'dig',
        'fixing',
        'context',
    ):
        value = getattr(args, name)
        if value is not None:
            setattr(finding, name, value)
            changes.append(f'{name}={value}')
    if args.propose is not None:
        finding.proposed = args.propose
        changes.append(f'proposed={args.propose}')
    if args.evidence is not None:
        finding.evidence = _read_text(args.evidence)
        changes.append('evidence')
    for ref in args.link:
        if ref not in finding.links:
            finding.links.append(ref)
            changes.append(f'link {ref}')
    if args.seen:
        finding.changed = None
        changes.append('change seen')
    for other_id in args.merge:
        other = ledger.get(other_id)
        finding.keys.extend(
            key for key in other.keys if key not in finding.keys
        )
        finding.occurrences.extend(other.occurrences)
        for ref in other.links:
            if ref not in finding.links:
                finding.links.append(ref)
        ledger.remove(other_id)
        changes.append(f'merged {other_id}')
    if args.split is not None:
        rows = [row.strip() for row in args.split.split(',') if row.strip()]
        split = _split(ledger, finding, rows, day)
        changes.append(f'split {", ".join(rows)} into {split.id}')
        print(f'Split {", ".join(rows)} into {split.id}')
    outside_v4 = ledger.outside_v4()
    changes.extend(_set_outside_v4(finding, args.outside_v4, outside_v4))
    changes.extend(
        _record_not_duplicates(
            finding, _parse_not_duplicates(args.not_duplicate)
        )
    )
    change = _update_priority(finding, args.priority, args.note, outside_v4)
    if change is not None:
        changes.append(change)
    if args.answer is not None:
        changes.append(f'answered {args.answer}')
    if args.note is not None:
        changes.append(args.note)
    if not changes:
        raise ValueError('Nothing to update.')
    finding.note('; '.join(changes), day)
    ledger.save(finding)
    hunt = ledger.load_hunt(day)
    if finding.id not in hunt['touched']:
        hunt['touched'].append(finding.id)
    if args.answer is not None:
        record_answer(hunt, finding.id, args.answer)
    ledger.save_hunt(hunt)
    ledger.commit(f'Update {finding.id}')
    print(f'Updated {finding.id}: {"; ".join(changes)}')


def _digest(args):
    config, ledger = _setup(args)
    day = today()
    findings = ledger.findings()
    hunt = ledger.load_hunt(day)
    header = []
    if args.omega or args.polaris:
        commits = []
        if args.omega:
            commits.append(f'Omega develop {args.omega}')
        if args.polaris:
            commits.append(f'Polaris {args.polaris}')
        header.append(f'{", ".join(commits)}.')
    covered = hunt.get('covered', {})
    if 'cdash' in covered:
        header.append(f'Harvested CDash through {covered["cdash"]}.')
    if 'review' in covered:
        header.append(f'Reviewed {covered["review"]}.')
    holds = ledger.holds()
    if holds:
        header.append(hold_line(holds))
    limit = args.limit if args.limit is not None else config.decisions
    digest = build_digest(
        findings, limit, day, header, outside_v4=ledger.outside_v4()
    )
    path = ledger.save_digest(day, digest.text)
    raised = [
        finding_id
        for finding_id, finding in findings.items()
        if finding.changed and finding.status not in OPEN_STATUSES
    ]
    for finding_id in raised:
        findings[finding_id].changed = None
        findings[finding_id].note('raised in the digest', day)
        ledger.save(findings[finding_id])
    hunt['decisions'] = [
        {'id': finding_id, 'answer': None}
        for finding_id in digest.decisions + digest.batched
    ]
    ledger.save_hunt(hunt)
    ledger.commit(f'Digest on {day}')
    print(digest.text)
    print(f'(saved to {path})')
    if digest.untriaged:
        print(
            f'\nNot in the digest because they have no priority yet: '
            f'{", ".join(digest.untriaged)}'
        )


def _file(args):
    _, ledger = _setup(args)
    day = today()
    findings = ledger.findings()
    if args.all_p4:
        ids = [
            finding.id
            for finding in findings.values()
            if finding.status in OPEN_STATUSES
            and finding.priority == 'P4'
            and finding.confidence != 'speculative'
        ]
    else:
        ids = args.ids
    if not ids:
        raise ValueError('Name the findings to file, or pass --all-p4.')
    if args.title is not None and len(ids) > 1:
        raise ValueError('--title names one issue, so file one finding.')
    if args.post and args.agent is None:
        raise ValueError('Pass --agent "<your name>" to sign what is posted.')
    user = get_user() if args.post else '<user>'
    signature = bug_hunt_file.signature_for(
        args.agent or '<agent>', user, co_drafted=args.co_drafted
    )
    ruled_out = _parse_not_duplicates(args.not_duplicate)
    _check_candidates(ids, findings, ledger, args, ruled_out)
    # findings for one batch go in together: GitHub's search may not find a
    # batch posted moments ago, and each edit replaces the whole body
    batches: Dict[tuple, list] = {}
    for finding_id in ids:
        finding = findings[finding_id]
        if args.post:
            changes = _record_not_duplicates(finding, ruled_out)
            if changes:
                finding.note('; '.join(changes), day)
        theme = _theme_for(finding, args)
        if theme is not None:
            repo = bug_hunt_file.repo_for(finding, args.repo)
            batches.setdefault((repo, theme), []).append(finding)
        else:
            _file_issue(finding, args, signature, day)
            ledger.save(finding)
    for (repo, theme), batched in batches.items():
        _file_in_batch(repo, theme, batched, args, signature, day)
        for finding in batched:
            ledger.save(finding)
    if args.post:
        hunt = ledger.load_hunt(day)
        answer = 'batch' if args.batch or args.all_p4 else 'file'
        for finding_id in ids:
            record_answer(hunt, finding_id, answer)
        ledger.save_hunt(hunt)
        ledger.commit(f'File {", ".join(ids)}')


def _handoff(args):
    _, ledger = _setup(args)
    finding = ledger.get(args.id)
    if not finding.links:
        raise ValueError(
            f'{finding.id} has no issue or batch yet.  File it first.'
        )
    print(bug_hunt_file.handoff(finding, args.ref or finding.links[0]))


def _review(args):
    config, ledger = _setup(args)
    repos = _review_repos(config)
    if args.record is not None:
        day = today()
        hunt = ledger.load_hunt(day)
        hunt['covered']['review'] = args.record
        hunt['covered']['review_until'] = day
        through = []
        for name, (path, remote, branch, _) in repos.items():
            tip = getattr(args, name) or _git_tip(path, f'{remote}/{branch}')
            hunt['covered'][f'review_{name}'] = tip
            through.append(f'{name} {tip}')
        ledger.save_hunt(hunt)
        ledger.commit(f'Record the review on {day}')
        print(f'Recorded the review: {args.record} ({", ".join(through)})')
        return
    for name, (path, remote, branch, paths) in repos.items():
        subprocess.run(
            ['git', '-C', path, 'fetch', '--quiet', remote, branch],
            capture_output=True,
        )
        ref = f'{remote}/{branch}'
        base = None if args.since else ledger.covered(f'review_{name}')
        if base is not None:
            selection = [f'{base}..{ref}']
            since = f'{base[:10]}, the last commit reviewed'
        else:
            # a date alone means that date at the current time of day
            day = args.since or ledger.covered('review_until')
            if day is None:
                day = (
                    datetime.date.today() - datetime.timedelta(days=30)
                ).isoformat()
            selection = [f'--since={day} 00:00', ref]
            since = day
        result = subprocess.run(
            ['git', '-C', path, 'log', '--first-parent', '--merges']
            + ['--oneline']
            + selection
            + ['--']
            + paths,
            capture_output=True,
            text=True,
        )
        lines = result.stdout.strip().splitlines()
        tip = _git_tip(path, ref)
        print(
            f'{name.capitalize()} merges into {branch} since {since}: '
            f'{len(lines)} (through {tip[:10]})'
        )
        for line in lines:
            print(f'  {line}')


def _review_repos(config):
    """
    The repositories a review reads, by name: each one's clone, remote,
    branch and the paths whose merges count
    """
    repos = {}
    if config.omega_repo is not None:
        repos['omega'] = (
            config.omega_repo,
            'origin',
            'develop',
            ['components/omega'],
        )
    polaris = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    repos['polaris'] = (polaris, _upstream_remote(polaris), 'main', [])
    return repos


def _upstream_remote(path):
    """The remote of a Polaris clone that is E3SM-Project/polaris"""
    remotes = subprocess.run(
        ['git', '-C', path, 'remote', '-v'], capture_output=True, text=True
    ).stdout.splitlines()
    for line in remotes:
        name, url = line.split()[:2]
        if 'E3SM-Project/polaris' in url:
            return name
    return 'origin'


def _git_tip(path, ref):
    """The commit a ref points to"""
    return subprocess.run(
        ['git', '-C', path, 'rev-parse', ref],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _status(args):
    config, ledger = _setup(args)
    findings = ledger.findings()
    by_status: Dict[str, int] = {}
    for finding in findings.values():
        by_status[finding.status] = by_status.get(finding.status, 0) + 1
    print(f'Ledger: {ledger.path}')
    print(
        'Findings: '
        + ', '.join(
            f'{by_status[status]} {status}'
            for status in STATUSES
            if status in by_status
        )
    )
    untriaged = sorted(
        finding.id
        for finding in findings.values()
        if finding.status in OPEN_STATUSES and finding.priority is None
    )
    if untriaged:
        print(f'Not yet triaged: {", ".join(untriaged)}')
    print(f'CDash harvested through: {ledger.covered("cdash") or "never"}')
    print(f'Last review: {ledger.covered("review") or "never"}')
    holds = ledger.holds()
    if holds:
        print(hold_line(holds))
    outside = ledger.outside_v4()
    if outside:
        print(f'Outside E3SM v4: {", ".join(outside)}')


def _setup(args):
    config = read_config(args.config_file, ledger=args.ledger)
    if config.ledger is None:
        raise LedgerError(
            'No ledger is set up.  Set "ledger" in the [bug_hunt] section of '
            '~/.config/polaris_pr_test.cfg, or pass --ledger.'
        )
    ledger = Ledger(config.ledger)
    ledger.sync()
    return config, ledger


def _set_outside_v4(finding, entry, outside_v4):
    """
    Name the entry outside E3SM v4 a finding depends on, or none if
    ``entry`` is empty, and return the change, if any
    """
    if entry is None:
        return []
    entry = entry or None
    if entry is not None and entry not in outside_v4:
        raise ValueError(
            f'"{entry}" is not in outside_v4.yaml; add it with '
            f'"bug_hunt.py outside-v4 {entry} --description ... '
            f'--source ...".'
        )
    finding.outside_v4 = entry
    return [f'outside_v4={entry}']


def _update_priority(finding, priority, note, outside_v4=None):
    """
    Set a finding's priority from the rubric, or to the one given, which
    needs a note if it is not the rubric's
    """
    rubric = rubric_priority(finding, outside_v4)
    if priority is None:
        return set_priority(finding, outside_v4)
    if rubric is not None and priority != rubric:
        if note is None:
            raise ValueError(
                f'The rubric gives {finding.id} {rubric}.  A different '
                f'priority needs a --note saying why.'
            )
        finding.priority_note = note
    else:
        finding.priority_note = None
    if priority == finding.priority:
        return None
    finding.priority = priority
    return f'priority={priority}'


def _split(ledger, finding, rows, day):
    """Move some rows of a finding to a new finding of their own"""
    keys = [
        Key(key.test, key.phase, key.message, rows=list(rows))
        for key in finding.keys
    ]
    split = Finding(
        id=ledger.new_id(Key(keys[0].test, keys[0].phase, f'{rows}'), day),
        keys=keys,
        created=day,
        source=finding.source,
        owner=finding.owner,
        claim=finding.claim,
        evidence=finding.evidence,
        reproduce=finding.reproduce,
    )
    split.occurrences = [
        occurrence
        for occurrence in finding.occurrences
        if occurrence.row in rows
    ]
    finding.occurrences = [
        occurrence
        for occurrence in finding.occurrences
        if occurrence.row not in rows
    ]
    split.note(f'split from {finding.id}', day)
    ledger.save(split)
    return split


def _theme_for(finding, args):
    """The clean-up batch a finding is filed in, if it goes in one"""
    if args.batch is None and args.all_p4:
        return finding.theme or 'everything else'
    return args.batch


def _check_candidates(ids, findings, ledger, args, ruled_out):
    """
    Search for each finding again, and refuse to post while any has a
    candidate that is neither its own nor ruled out; without ``--post``,
    list the candidates above the drafts
    """
    blocked: List[str] = []
    for finding_id in ids:
        finding = findings.get(finding_id) or ledger.get(finding_id)
        findings[finding.id] = finding
        expected = set(finding.links)
        theme = _theme_for(finding, args)
        if theme is not None:
            repo = bug_hunt_file.repo_for(finding, args.repo)
            batch = bug_hunt_file.find_batch(repo, theme)
            if batch is not None:
                expected.add(f'{repo}#{batch["number"]}')
        found = candidates(finding)
        if not args.post:
            _print_candidates(finding, found, expected, ruled_out)
            continue
        blocked.extend(
            f'  {finding.id}: {candidate.ref} ({candidate.kind}, '
            f'{candidate.state}): {candidate.title}'
            for candidate in _unresolved(finding, found, expected, ruled_out)
        )
    if blocked:
        raise ValueError(
            'Not posted: these may already track the findings.  Read each.  '
            'If one is the same bug, or the general issue the finding is '
            'one instance of, link it ("update <id> --link <ref> --status '
            'tracked") and do not file; otherwise pass --not-duplicate '
            '"<ref>: <why it is a different bug>".\n' + '\n'.join(blocked)
        )


def _parse_not_duplicates(values):
    """
    Parse ``--not-duplicate "<owner>/<repo>#<n>: <why>"`` values into
    ``ref`` and ``why``
    """
    parsed = []
    for value in values or []:
        ref, _, why = value.partition(':')
        ref = ref.strip()
        why = why.strip()
        if not re.fullmatch(r'[\w.-]+/[\w.-]+#\d+', ref) or not why:
            raise ValueError(
                f'--not-duplicate takes "<owner>/<repo>#<n>: <why it is a '
                f'different bug>", not "{value}".'
            )
        parsed.append({'ref': ref, 'why': why})
    return parsed


def _record_not_duplicates(finding, entries):
    """Record the candidates ruled out as different bugs"""
    known = {entry['ref'] for entry in finding.not_duplicates}
    added = [entry for entry in entries if entry['ref'] not in known]
    if not added:
        return []
    finding.not_duplicates.extend(added)
    return [
        f'not the same as {entry["ref"]}: {entry["why"]}' for entry in added
    ]


def _unresolved(finding, found, expected, ruled_out=()):
    """The candidates that are neither the finding's own nor ruled out"""
    ruled = {entry['ref'] for entry in finding.not_duplicates}
    ruled.update(entry['ref'] for entry in ruled_out)
    return [
        candidate
        for candidate in found
        if candidate.ref not in expected and candidate.ref not in ruled
    ]


def _print_candidates(finding, found, expected=(), ruled_out=()):
    """List a finding's candidates, and what has been decided about each"""
    reasons = {entry['ref']: entry['why'] for entry in finding.not_duplicates}
    reasons.update({entry['ref']: entry['why'] for entry in ruled_out})
    print(f'Candidates for {finding.id} (open, or closed lately):')
    if not found:
        print('  none')
    for candidate in found:
        closed = f', closed {candidate.closed}' if candidate.closed else ''
        if candidate.ref in expected:
            decided = ' [its own]'
        elif candidate.ref in reasons:
            decided = f' [not the same: {reasons[candidate.ref]}]'
        else:
            decided = ' [NOT YET RULED OUT]'
        print(
            f'  {candidate.ref} ({candidate.kind}, {candidate.state}'
            f'{closed}): {candidate.title}{decided}'
        )
    print()


def _file_issue(finding, args, signature, day):
    issue = bug_hunt_file.render_issue(
        finding, signature, repo=args.repo, title=args.title
    )
    if not args.post:
        print(f'Would file in {issue.repo} with labels {issue.labels}:\n')
        print(f'# {issue.title}\n')
        print(issue.body)
        return
    ref = bug_hunt_file.post_issue(issue)
    finding.links.append(ref)
    finding.status = 'tracked'
    finding.note(f'filed as {ref}', day)
    print(f'Filed {finding.id} as {ref}')


def _file_in_batch(repo, theme, findings, args, signature, day):
    lines = [bug_hunt_file.batch_line(finding) for finding in findings]
    if not args.post:
        title = bug_hunt_file.batch_title(theme)
        print(f'Would add to "{title}" in {repo}:')
        for line in lines:
            print(f'  {line}')
        return
    batch = bug_hunt_file.find_batch(repo, theme)
    if batch is None:
        issue = bug_hunt_file.new_batch(repo, theme, lines, signature)
        ref = bug_hunt_file.post_issue(issue)
    else:
        ref = bug_hunt_file.add_to_batch(repo, batch, lines)
    for finding in findings:
        if ref not in finding.links:
            finding.links.append(ref)
        finding.status = 'batched'
        finding.theme = theme
        finding.note(f'batched in {ref}', day)
        print(f'Batched {finding.id} in {ref}')


def _print_summary(ledger, summary):
    findings = ledger.findings()
    print(
        f'  {len(summary.new)} new, {len(summary.changed)} changed, '
        f'{len(summary.updated)} failing as before, {summary.ended} '
        f'ended and not recorded'
    )
    for label, ids in (('new', summary.new), ('changed', summary.changed)):
        for finding_id in ids:
            print(f'  {label}: {finding_id}: {findings[finding_id].claim}')
    for row in summary.released:
        print(f'  {row} reported again, so it is no longer on hold')


def _read_text(value):
    """Text given directly, or the contents of the file it names"""
    if value is None:
        return None
    if os.path.isfile(value):
        with open(value) as handle:
            return handle.read()
    return value


def _dump(data):
    yaml = YAML()
    yaml.default_flow_style = False
    stream = io.StringIO()
    yaml.dump(
        {
            name: value
            for name, value in data.items()
            if value not in (None, [])
        },
        stream,
    )
    return stream.getvalue()


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Hunt for bugs in Omega and Polaris'
    )
    parser.add_argument(
        '-f',
        '--config_file',
        help='The config file (default: ~/.config/polaris_pr_test.cfg)',
    )
    parser.add_argument(
        '--ledger', help='A ledger clone, in place of the one in the config'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    harvest = subparsers.add_parser(
        'harvest', help='Read testing results into the ledger'
    )
    harvest.add_argument(
        '--since', help='The first night to harvest (default: after the last)'
    )
    harvest.add_argument(
        '--until', help='The last night to harvest (default: today)'
    )
    harvest.add_argument(
        '--lookback',
        type=int,
        default=DEFAULT_LOOKBACK,
        help='Nights before --since to read, to find when failures began',
    )
    harvest.add_argument(
        '--no-cdash',
        dest='no_cdash',
        action='store_true',
        help='Do not harvest CDash',
    )
    harvest.add_argument(
        '--local',
        action='store_true',
        help='Harvest Polaris and CIME runs under the harvest roots',
    )
    harvest.add_argument(
        '--roots', nargs='+', help='Directories to harvest with --local'
    )
    harvest.set_defaults(func=_harvest)

    park = subparsers.add_parser(
        'park', help='Record a bug found outside the work at hand'
    )
    park.add_argument('--claim', required=True, help='The bug, in one line')
    park.add_argument(
        '--where', required=True, help='<file>:<line>, or a test or task'
    )
    park.add_argument('--owner', choices=OWNERS, default='unknown')
    park.add_argument('--confidence', choices=CONFIDENCES, required=True)
    park.add_argument('--severity', choices=SEVERITIES)
    park.add_argument('--expected', help='What should happen instead')
    park.add_argument('--reproduce', help='How to reproduce it, if known')
    park.add_argument(
        '--evidence', help='The evidence in hand, or a file holding it'
    )
    park.add_argument('--context', help='The work at hand when it was found')
    park.add_argument(
        '--fixing',
        help='A blocker being fixed as part of the work: where (branch or PR)',
    )
    park.add_argument(
        '--outside-v4',
        dest='outside_v4',
        help='The entry in outside_v4.yaml the bug depends on, if any',
    )
    park.add_argument(
        '--source',
        choices=('parked', 'review'),
        default='parked',
        help='"review" for a finding from a hunt\'s code review',
    )
    park.set_defaults(func=_park)

    hold = subparsers.add_parser(
        'hold',
        help='Put rows on hold, so a harvest does not report them as stopped',
    )
    hold.add_argument('rows', nargs='+', help='<machine>/<compiler> rows')
    hold.add_argument('--reason', help='Why, such as "out of compute hours"')
    hold.add_argument(
        '--release',
        action='store_true',
        help='Take the rows off hold before they report again',
    )
    hold.set_defaults(func=_hold)

    outside = subparsers.add_parser(
        'outside-v4',
        help='List, add or remove the features and options outside E3SM v4',
    )
    outside.add_argument(
        'name', nargs='?', help='The entry, such as langmuir-turbulence'
    )
    outside.add_argument('--description', help='What is outside v4')
    outside.add_argument(
        '--source', help='Who or what says so, such as an issue or a page'
    )
    outside.add_argument(
        '--remove', action='store_true', help='Take the entry off the list'
    )
    outside.set_defaults(func=_outside_v4)

    match = subparsers.add_parser(
        'match', help='Look for issues and pull requests that track findings'
    )
    match.add_argument(
        'ids', nargs='*', help='Findings (default: open, unlinked ones)'
    )
    match.add_argument(
        '--refresh',
        action='store_true',
        help='Check the links of tracked findings for closed issues',
    )
    match.set_defaults(func=_match)

    update = subparsers.add_parser(
        'update', help='Record what the agent decided about a finding'
    )
    update.add_argument('id')
    update.add_argument('--owner', choices=OWNERS)
    update.add_argument('--severity', choices=SEVERITIES)
    update.add_argument('--confidence', choices=CONFIDENCES)
    update.add_argument('--priority', choices=PRIORITIES)
    update.add_argument('--status', choices=STATUSES)
    update.add_argument('--claim')
    update.add_argument('--where')
    update.add_argument('--expected')
    update.add_argument('--reproduce')
    update.add_argument('--evidence', help='Text, or a file holding it')
    update.add_argument('--propose', choices=ACTIONS)
    update.add_argument('--theme', help='The clean-up batch it belongs in')
    update.add_argument('--dig', help='What digging further would take')
    update.add_argument(
        '--fixing', help='Who or what is fixing it, outside the hunt'
    )
    update.add_argument('--context')
    update.add_argument(
        '--not-duplicate',
        dest='not_duplicate',
        action='append',
        default=[],
        help='A candidate read and ruled out, as "<owner>/<repo>#<n>: <why '
        'it is a different bug>"',
    )
    update.add_argument(
        '--outside-v4',
        dest='outside_v4',
        help='The entry in outside_v4.yaml the bug depends on ("" for none)',
    )
    update.add_argument(
        '--link',
        action='append',
        default=[],
        help='An issue or PR that tracks it, as <owner>/<repo>#<n>',
    )
    update.add_argument(
        '--merge',
        action='append',
        default=[],
        help='Another finding with the same cause, to merge into this one',
    )
    update.add_argument(
        '--split',
        help='Rows that fail for another reason, comma-separated, to move '
        'to a finding of their own',
    )
    update.add_argument(
        '--seen',
        action='store_true',
        help='Mark a change as seen, so it is not raised again',
    )
    update.add_argument('--note', help="A line for the finding's history")
    update.add_argument(
        '--answer',
        choices=ACTIONS,
        help="The developer's answer to the digest's decision",
    )
    update.set_defaults(func=_update)

    digest = subparsers.add_parser(
        'digest', help='Write the decisions for the developer'
    )
    digest.add_argument(
        '--limit', type=int, help='The most decisions, besides P1 findings'
    )
    digest.add_argument('--omega', help='The Omega commit hunted')
    digest.add_argument('--polaris', help='The Polaris commit hunted')
    digest.set_defaults(func=_digest)

    file_parser = subparsers.add_parser(
        'file', help='File findings as issues or in clean-up batches'
    )
    file_parser.add_argument('ids', nargs='*')
    file_parser.add_argument(
        '--batch', help='Add to the clean-up batch with this theme'
    )
    file_parser.add_argument(
        '--all-p4',
        dest='all_p4',
        action='store_true',
        help='Batch every open P4 finding in its theme',
    )
    file_parser.add_argument(
        '--repo', help="The repository, if not the owner's"
    )
    file_parser.add_argument(
        '--title', help='The issue title, if not the claim cut short'
    )
    file_parser.add_argument(
        '--not-duplicate',
        dest='not_duplicate',
        action='append',
        default=[],
        help='A candidate read and ruled out, as "<owner>/<repo>#<n>: <why '
        'it is a different bug>"; posting refuses while any is left',
    )
    file_parser.add_argument(
        '--post',
        action='store_true',
        help='Post, rather than print what would be posted',
    )
    file_parser.add_argument(
        '--agent', help='The agent posting, for the signature'
    )
    file_parser.add_argument(
        '--co-drafted',
        dest='co_drafted',
        action='store_true',
        help='Sign as drafted with the developer, who directed the content',
    )
    file_parser.set_defaults(func=_file)

    handoff = subparsers.add_parser(
        'handoff', help='Print the prompt for a session that fixes a finding'
    )
    handoff.add_argument('id')
    handoff.add_argument(
        '--ref', help='The issue to fix, if not the first link'
    )
    handoff.set_defaults(func=_handoff)

    review = subparsers.add_parser(
        'review',
        help='List the Omega and Polaris merges since the last review, or '
        'record one',
    )
    review.add_argument(
        '--since',
        help='List merges since this date (default: the last commits '
        'reviewed)',
    )
    review.add_argument(
        '--record', help='Record what a finished review covered'
    )
    review.add_argument(
        '--omega',
        help='With --record, the Omega commit reviewed through (default: '
        'the tip of develop)',
    )
    review.add_argument(
        '--polaris',
        help='With --record, the Polaris commit reviewed through (default: '
        'the tip of main)',
    )
    review.set_defaults(func=_review)

    status = subparsers.add_parser('status', help='Summarize the ledger')
    status.set_defaults(func=_status)

    return parser.parse_args()


if __name__ == '__main__':
    main()
