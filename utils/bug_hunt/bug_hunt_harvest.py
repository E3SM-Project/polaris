"""
Harvesting failures into the ledger, from CDash and from Polaris and CIME
runs on disk
"""

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from bug_hunt_cdash import (
    Build,
    BuildKind,
    CDash,
    FailedTest,
    nights_between,
    shift_night,
)
from bug_hunt_keys import (
    cime_phase_and_message,
    first_error_line,
    normalize_message,
    normalize_test,
)
from bug_hunt_ledger import (
    MISSING,
    OPEN_STATUSES,
    Finding,
    Key,
    Ledger,
    Occurrence,
    set_priority,
    today,
)
from bug_hunt_sources import LocalFailure

#: how many nights before the harvested ones are read, to find when a
#: failure began
DEFAULT_LOOKBACK = 21

#: the owner a new finding gets from where it was seen, until the agent
#: decides
DEFAULT_OWNERS = {
    'ctest': 'omega',
    'polaris-nightly': 'unknown',
    'coupled': 'unknown',
    'polaris': 'unknown',
    'cime': 'unknown',
}

#: the most lines of output kept as a finding's evidence
EXCERPT_LINES = 20

_MERGE = re.compile(r'Merge pull request #(\d+)')


@dataclass
class Sighting:
    """
    A failure as harvested, before it is recorded in the ledger

    The fields are those of :py:class:`bug_hunt_ledger.Key` and
    :py:class:`bug_hunt_ledger.Occurrence`, with the output that is kept
    as evidence and the merges between the last pass and the first failure.
    """

    test: str
    phase: str
    message: Optional[str]
    row: str
    source: str
    first_failed: Optional[str] = None
    last_failed: Optional[str] = None
    last_passed: Optional[str] = None
    nights: int = 1
    intermittent: bool = False
    url: Optional[str] = None
    excerpt: Optional[str] = None
    merged_between: List[str] = field(default_factory=list)


@dataclass
class HarvestSummary:
    """
    What a harvest added to the ledger

    Attributes
    ----------
    new : list of str
        Findings the harvest created

    updated : list of str
        Findings that failed again as before

    changed : list of str
        Findings that were decided on before and have changed, so that
        the digest raises them again

    ended : int
        Failures in the harvested nights that have since stopped, and
        did not fail on and off, which are not recorded

    released : list of str
        Rows that were on hold and have reported again, so were taken off
        hold
    """

    new: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    changed: List[str] = field(default_factory=list)
    ended: int = 0
    released: List[str] = field(default_factory=list)


def harvest_cdash(
    ledger: Ledger,
    cdash: CDash,
    kinds: List[BuildKind],
    first: str,
    last: str,
    omega_repo: Optional[str] = None,
    lookback: int = DEFAULT_LOOKBACK,
    day: Optional[str] = None,
) -> HarvestSummary:
    """
    Harvest failures, rows that stopped reporting and rising warning
    counts from CDash

    A row on hold is not reported as stopped.  It is taken off hold once it
    reports again, after the day it was put on hold, since a hold may be
    set on the day the row last reported.

    Parameters
    ----------
    ledger : bug_hunt_ledger.Ledger
        The ledger to record findings in

    cdash : bug_hunt_cdash.CDash
        The CDash project

    kinds : list of bug_hunt_cdash.BuildKind
        The kinds of build to harvest

    first, last : str
        The first and last nights to harvest, ``yyyy-mm-dd``

    omega_repo : str, optional
        A clone of E3SM-Project/Omega, used to list the merges into
        ``develop`` between the last pass and the first failure

    lookback : int, optional
        How many nights before ``first`` to read, to find when a failure
        began

    day : str, optional
        The date of the hunt, today by default

    Returns
    -------
    summary : bug_hunt_harvest.HarvestSummary
        What the harvest added to the ledger
    """
    if day is None:
        day = today()
    if omega_repo is not None:
        subprocess.run(
            ['git', '-C', omega_repo, 'fetch', '--quiet', 'origin', 'develop'],
            capture_output=True,
        )
    builds, failures = _read_nights(cdash, shift_night(first, -lookback), last)
    omega_of = {kind.source: kind.omega for kind in kinds}
    sightings, ended = _failure_sightings(
        builds, failures, first, omega_of, omega_repo
    )
    holds = ledger.holds()
    released = _reported_since_hold(builds, holds)
    for row in released:
        del holds[row]
    if released:
        ledger.save_holds(holds)
    sightings.extend(_missing_rows(builds, kinds, first, last, set(holds)))
    sightings.extend(_warning_rises(builds, first))
    summary = record(ledger, sightings, day)
    summary.ended = ended
    summary.released = released

    hunt = ledger.load_hunt(day)
    hunt['covered']['cdash'] = last
    _touch(hunt, summary)
    ledger.save_hunt(hunt)
    return summary


def harvest_local(
    ledger: Ledger, failures: List[LocalFailure], day: Optional[str] = None
) -> HarvestSummary:
    """
    Harvest failures found in Polaris and CIME runs on disk

    Parameters
    ----------
    ledger : bug_hunt_ledger.Ledger
        The ledger to record findings in

    failures : list of bug_hunt_sources.LocalFailure
        The failures

    day : str, optional
        The date of the hunt, today by default

    Returns
    -------
    summary : bug_hunt_harvest.HarvestSummary
        What the harvest added to the ledger
    """
    if day is None:
        day = today()
    sightings = [
        Sighting(
            test=normalize_test(failure.test),
            phase=failure.phase,
            message=(
                None
                if failure.source == 'polaris'
                else normalize_message(failure.message)
            ),
            row=failure.row,
            source=failure.source,
            first_failed=failure.night,
            last_failed=failure.night,
            url=failure.where,
            excerpt=failure.excerpt,
        )
        for failure in failures
    ]
    summary = record(ledger, sightings, day)
    hunt = ledger.load_hunt(day)
    _touch(hunt, summary)
    ledger.save_hunt(hunt)
    return summary


def record(
    ledger: Ledger, sightings: List[Sighting], day: str
) -> HarvestSummary:
    """
    Record sightings in the ledger, as new findings or as occurrences of
    the findings that hold their keys

    A finding that was already decided on is marked as changed if it now
    fails on a new row, or fails again after it was fixed.

    Parameters
    ----------
    ledger : bug_hunt_ledger.Ledger
        The ledger

    sightings : list of bug_hunt_harvest.Sighting
        The sightings

    day : str
        The date of the hunt

    Returns
    -------
    summary : bug_hunt_harvest.HarvestSummary
        What was added to the ledger
    """
    summary = HarvestSummary()
    findings = ledger.findings()
    created = set()
    touched: Dict[str, Finding] = {}
    for sighting in sightings:
        finding = ledger.find(
            findings,
            sighting.test,
            sighting.phase,
            sighting.message,
            sighting.row,
        )
        if finding is None:
            finding = _new_finding(ledger, sighting, day)
            findings[finding.id] = finding
            created.add(finding.id)
            summary.new.append(finding.id)
        change = _add_occurrence(finding, sighting)
        if finding.id not in created:
            if change is not None:
                finding.changed = change
                finding.note(change, day)
                if finding.id not in summary.changed:
                    summary.changed.append(finding.id)
            elif finding.id not in summary.updated:
                summary.updated.append(finding.id)
        touched[finding.id] = finding
    outside_v4 = ledger.outside_v4()
    for finding in touched.values():
        change = set_priority(finding, outside_v4)
        if change is not None:
            finding.note(change, day)
        ledger.save(finding)
    return summary


def merges_between(
    omega_repo: str, since: Optional[str], until: Optional[str]
) -> List[str]:
    """
    The pull requests merged into Omega ``develop`` between two times

    Parameters
    ----------
    omega_repo : str
        A clone of E3SM-Project/Omega with ``origin/develop`` fetched

    since, until : str, optional
        ISO 8601 times, such as the starts of the last passing build and of
        the first failing one

    Returns
    -------
    merges : list of str
        ``E3SM-Project/Omega#<n>`` for each merge, oldest first
    """
    if since is None or until is None:
        return []
    result = subprocess.run(
        [
            'git',
            '-C',
            omega_repo,
            'log',
            '--first-parent',
            '--merges',
            '--format=%s',
            f'--since={since}',
            f'--until={until}',
            'origin/develop',
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    numbers = _MERGE.findall(result.stdout)
    return [f'E3SM-Project/Omega#{number}' for number in reversed(numbers)]


def _read_nights(cdash: CDash, first: str, last: str):
    """The builds of each row on each night, and the failed tests"""
    builds: Dict[Tuple[str, str], Dict[str, Build]] = {}
    for night in nights_between(first, last):
        for build in cdash.builds(night):
            by_night = builds.setdefault((build.source, build.row), {})
            earlier = by_night.get(night)
            if earlier is None or (build.start or '') > (earlier.start or ''):
                by_night[night] = build
    failures: Dict[Tuple[str, str, str], Dict[str, tuple]] = {}
    for (source, row), by_night in builds.items():
        for night, build in by_night.items():
            for test in cdash.failed_tests(build):
                phase, message, excerpt = _classify(test, source)
                key = (source, row, normalize_test(test.name))
                failures.setdefault(key, {})[night] = (
                    phase,
                    normalize_message(message),
                    excerpt,
                    build,
                )
    return builds, failures


def _failure_sightings(builds, failures, first, omega_of, omega_repo):
    """
    A sighting for each test that failed on a row in the window and still
    fails at the row's latest build, or fails on and off, and the count of
    the other failures, which have ended
    """
    sightings = []
    ended = 0
    for (source, row, test), by_night in sorted(failures.items()):
        in_window = sorted(night for night in by_night if night >= first)
        if not in_window:
            continue
        timeline = sorted(builds[(source, row)])
        last_failed = in_window[-1]
        index = timeline.index(last_failed)
        while index > 0 and timeline[index - 1] in by_night:
            index -= 1
        first_failed = timeline[index]
        last_passed = timeline[index - 1] if index > 0 else None
        intermittent = _failure_runs(timeline, by_night) > 1
        if last_failed != timeline[-1] and not intermittent:
            ended += 1
            continue
        phase, message, excerpt, build = by_night[last_failed]
        merged: List[str] = []
        if (
            omega_repo is not None
            and last_passed is not None
            and omega_of.get(source) == 'develop'
        ):
            merged = merges_between(
                omega_repo,
                builds[(source, row)][last_passed].start,
                builds[(source, row)][first_failed].start,
            )
        sightings.append(
            Sighting(
                test=test,
                phase=phase,
                message=message,
                row=row,
                source=source,
                first_failed=first_failed,
                last_failed=last_failed,
                last_passed=last_passed,
                nights=sum(1 for night in timeline if night in by_night),
                intermittent=intermittent,
                url=build.url,
                excerpt=excerpt,
                merged_between=merged,
            )
        )
    return sightings, ended


def _failure_runs(timeline, by_night):
    """How many separate runs of failing nights a timeline has"""
    runs = 0
    previous = False
    for night in timeline:
        failed = night in by_night
        if failed and not previous:
            runs += 1
        previous = failed
    return runs


def _reported_since_hold(builds, holds):
    """The rows on hold with a build after the day they were held"""
    return sorted(
        row
        for row, hold in holds.items()
        if any(
            night > str(hold['since'])
            for (_, built_row), nights in builds.items()
            if built_row == row
            for night in nights
        )
    )


def _missing_rows(builds, kinds, first, last, held):
    """A sighting for each row with no results lately, except rows on hold"""
    sightings = []
    for kind in kinds:
        for row in kind.rows:
            if row in held:
                continue
            # the nights read before the window count too, so that a row
            # that reported the night before a short window is not missing
            nights = sorted(builds.get((kind.source, row), {}))
            if nights and nights[-1] >= shift_night(last, -1):
                continue
            if nights:
                message = 'stopped reporting'
                last_passed: Optional[str] = nights[-1]
            else:
                message = 'no results'
                last_passed = None
            sightings.append(
                Sighting(
                    test=f'{kind.source} nightly',
                    phase=MISSING,
                    message=message,
                    row=row,
                    source=kind.source,
                    first_failed=(
                        first
                        if last_passed is None
                        else shift_night(last_passed, 1)
                    ),
                    last_failed=last,
                    last_passed=last_passed,
                )
            )
    return sightings


def _warning_rises(builds, first):
    """A sighting for each row whose count of build warnings rose"""
    sightings = []
    for (source, row), by_night in sorted(builds.items()):
        counted = [
            by_night[night]
            for night in sorted(by_night)
            if night >= first and by_night[night].warnings is not None
        ]
        if len(counted) < 2:
            continue
        start, end = counted[0], counted[-1]
        if end.warnings <= start.warnings:
            continue
        rise = next(
            index
            for index, build in enumerate(counted)
            if build.warnings > start.warnings
        )
        sightings.append(
            Sighting(
                test=f'{source} build',
                phase='warnings',
                message='warning count rose',
                row=row,
                source=source,
                first_failed=counted[rise].night,
                last_failed=end.night,
                last_passed=counted[rise - 1].night,
                url=end.url.replace('/tests', ''),
                excerpt=(
                    f'{start.warnings} warnings on {start.night}, '
                    f'{end.warnings} on {end.night}'
                ),
            )
        )
    return sightings


def _classify(test: FailedTest, source: str):
    """The phase, message and an excerpt of output for a failed test"""
    output = test.output or ''
    if source == 'coupled':
        phase, message = cime_phase_and_message(output)
        return phase, message, _cime_excerpt(output)
    # the first error line of a CTest or Polaris task differs by machine
    # for the same cause (MPI and launcher messages), so it goes in the
    # evidence rather than the key
    details = test.details or ''
    phase = 'timeout' if 'timeout' in details.lower() else 'run'
    line = first_error_line(output)
    return phase, None, _excerpt_from(output, line)


def _cime_excerpt(output: str) -> Optional[str]:
    """The lines of a CIME log that say which phase failed and how"""
    lines = output.splitlines()
    for marker in (
        'FAILED for test',
        'did NOT match',
        'Could not find all inputdata',
        'ERROR:',
    ):
        for index, line in enumerate(lines):
            if marker in line:
                excerpt = lines[index : index + EXCERPT_LINES]
                summary = [
                    line
                    for line in lines
                    if 'were compared' in line
                    or 'non-zero differences' in line
                ]
                return '\n'.join(excerpt + summary)
    return None


def _excerpt_from(output: str, line: Optional[str]) -> Optional[str]:
    """Up to :py:data:`EXCERPT_LINES` lines from the first error on"""
    if not output or line is None:
        return None
    lines = output.splitlines()
    for index, candidate in enumerate(lines):
        if candidate.strip().startswith(line[:60]):
            return '\n'.join(lines[index : index + EXCERPT_LINES])
    return None


def _new_finding(ledger: Ledger, sighting: Sighting, day: str) -> Finding:
    if sighting.phase == MISSING:
        # rows stop reporting for different reasons, so each is its own key
        key = Key(sighting.test, MISSING, rows=[sighting.row])
    else:
        key = Key(sighting.test, sighting.phase, sighting.message)
    finding = Finding(
        id=ledger.new_id(key, day),
        keys=[key],
        created=day,
        source=sighting.source,
        owner=DEFAULT_OWNERS.get(sighting.source, 'unknown'),
        claim=_default_claim(sighting),
        evidence=sighting.excerpt,
        reproduce=None if sighting.url is None else f'See {sighting.url}',
    )
    finding.note(f'harvested from {sighting.source}', day)
    return finding


def _default_claim(sighting: Sighting) -> str:
    """A claim for a new finding, which the agent rewrites"""
    if sighting.phase == MISSING:
        if sighting.message == 'stopped reporting':
            return f'The {sighting.source} nightly stopped reporting'
        return f'The {sighting.source} nightly has no results'
    if sighting.phase == 'warnings':
        return f'Compiler warnings rose in the {sighting.source} build'
    return f'{sighting.test} fails in its {sighting.phase} phase'


def _add_occurrence(finding: Finding, sighting: Sighting) -> Optional[str]:
    """
    Add or update the occurrence of a sighting

    Returns
    -------
    change : str, optional
        What changed in a finding that was decided on before, if anything
    """
    occurrence = finding.occurrence(sighting.test, sighting.row)
    new_row = sighting.row not in finding.rows
    previous_last = None
    if occurrence is None:
        occurrence = Occurrence(
            test=sighting.test, row=sighting.row, source=sighting.source
        )
        finding.occurrences.append(occurrence)
    else:
        previous_last = occurrence.last_failed
    if sighting.first_failed is not None:
        occurrence.first_failed = sighting.first_failed
    if sighting.last_failed is not None:
        occurrence.last_failed = max(
            sighting.last_failed, occurrence.last_failed or ''
        )
    if sighting.last_passed is not None:
        occurrence.last_passed = sighting.last_passed
    occurrence.nights = max(occurrence.nights, sighting.nights)
    occurrence.intermittent = occurrence.intermittent or sighting.intermittent
    if sighting.url is not None:
        occurrence.url = sighting.url
    for merge in sighting.merged_between:
        if merge not in finding.merged_between:
            finding.merged_between.append(merge)
    if finding.evidence is None and sighting.excerpt is not None:
        finding.evidence = sighting.excerpt

    if finding.status in OPEN_STATUSES:
        return None
    if new_row:
        return f'now fails on {sighting.row} too'
    later = (sighting.last_failed or '') > (previous_last or '')
    if finding.status == 'fixed' and later:
        finding.came_back = True
        return 'fails again after it was fixed'
    return None


def _touch(hunt, summary: HarvestSummary) -> None:
    for finding_id in summary.new + summary.updated + summary.changed:
        if finding_id not in hunt['touched']:
            hunt['touched'].append(finding_id)
