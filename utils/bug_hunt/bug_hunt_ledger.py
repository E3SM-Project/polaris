"""
The ledger: a git repository with one YAML file per finding and a record of
each hunt
"""

import datetime
import fcntl
import hashlib
import io
import os
import re
import subprocess
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import (
    IO,
    Any,
    Container,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
)

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

SCHEMA_VERSION = 1

OWNERS = ('omega', 'polaris', 'e3sm', 'environment', 'unknown')
SEVERITIES = ('S1', 'S2', 'S3', 'S4')
CONFIDENCES = ('measured', 'inferred', 'speculative')
PRIORITIES = ('P1', 'P2', 'P3', 'P4')
STATUSES = (
    'new',
    'parked',
    'fixing',
    'digging',
    'tracked',
    'batched',
    'logged',
    'dismissed',
    'fixed',
)
ACTIONS = ('file', 'batch', 'log', 'dismiss', 'dig')

#: the phase of a row that stopped reporting, whose key is the row itself
MISSING = 'missing'

#: the statuses of findings that still need a decision
OPEN_STATUSES = ('new', 'parked')

FINDINGS_DIR = 'findings'
HUNTS_DIR = 'hunts'

#: the file, in a clone's git directory and so never committed, that names
#: the hunt the clone started last
CURRENT_HUNT_FILE = 'bug_hunt_current'

#: a hunt's name: the day it started and its number that day
_HUNT_NAME = re.compile(r'^(\d{4}-\d{2}-\d{2})(?:-(\d+))?$')

#: the rows on hold, each with a reason and a date
HOLDS_FILE = 'on_hold.yaml'

#: features and options outside E3SM v4, each with its source and a date
OUTSIDE_V4_FILE = 'outside_v4.yaml'

#: the file of terms finding names may use, beyond plain words
NAME_TERMS_FILE = 'name_terms.yaml'

#: how many times a commit tries to push, pulling between tries
PUSH_ATTEMPTS = 3

#: the entries in a hunt's ``covered`` that are dates, merged as the later
COVERED_DATES = ('cdash', 'review_until')


class LedgerError(Exception):
    """The ledger is missing, or a finding cannot be found or written"""


@dataclass
class Key:
    """
    What identifies a failure, apart from where and when it happened

    Attributes
    ----------
    test : str
        The test without its machine and compiler, or for a finding in code,
        the file

    phase : str
        ``setup``, ``build``, ``run``, ``compare``, ``baseline``,
        ``timeout``, ``missing``, ``warnings`` or ``code``

    message : str, optional
        The normalized first error message, or for a finding in code, a
        short form of the claim

    rows : list of str, optional
        The rows the key is limited to, after a finding has been split
        because some rows fail for another reason
    """

    test: str
    phase: str
    message: Optional[str] = None
    rows: Optional[List[str]] = None

    def matches(
        self, test: str, phase: str, message: Optional[str], row: str
    ) -> int:
        """
        How well a failure matches this key

        A row that stopped reporting is keyed by the row itself, so a
        ``missing`` key matches only the rows it lists, whatever the message.

        Returns
        -------
        score : int
            0 for no match, 1 for a match to a key with no rows, and 2 for a
            match to a key limited to rows that include ``row``
        """
        if self.phase == MISSING:
            if (self.test, self.phase) != (test, phase):
                return 0
            return 2 if self.rows is not None and row in self.rows else 0
        if (self.test, self.phase, self.message) != (test, phase, message):
            return 0
        if self.rows is None:
            return 1
        return 2 if row in self.rows else 0

    def text(self) -> str:
        """The key as one line of text"""
        message = '' if self.message is None else f' | {self.message}'
        rows = '' if self.rows is None else f' | {", ".join(self.rows)}'
        return f'{self.test} | {self.phase}{message}{rows}'


@dataclass
class Occurrence:
    """
    Where and when a finding's failure was seen, for one test on one row

    Attributes
    ----------
    test : str
        The test, as in the key

    row : str
        ``<machine>/<compiler>``

    source : str
        ``ctest``, ``polaris-nightly``, ``coupled``, ``polaris`` or
        ``cime``

    first_failed : str, optional
        The first night (or date) of the latest run of failures

    last_failed : str, optional
        The last night it failed

    last_passed : str, optional
        The last night it passed before ``first_failed``

    nights : int
        How many nights it failed on, among those harvested

    intermittent : bool
        Whether it passed and failed in turn with no merge in between

    url : str, optional
        Where the latest failure can be seen

    first_ran : str, optional
        The first night the row ran the test, if it failed that night: the
        night before did not have the test
    """

    test: str
    row: str
    source: str
    first_failed: Optional[str] = None
    last_failed: Optional[str] = None
    last_passed: Optional[str] = None
    nights: int = 0
    intermittent: bool = False
    url: Optional[str] = None
    first_ran: Optional[str] = None


@dataclass
class Finding:
    """
    A bug, or a candidate for one, with what is known about it

    See the design of the bug hunter for what each field means.  Fields
    the harvest cannot know, such as the severity, are filled in by the
    agent with ``bug_hunt.py update``.
    """

    id: str
    keys: List[Key]
    created: str
    source: str
    name: str = ''
    owner: str = 'unknown'
    claim: str = ''
    where: Optional[str] = None
    expected: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[str] = None
    priority: Optional[str] = None
    priority_note: Optional[str] = None
    came_back: bool = False
    ended: Optional[str] = None
    closed_upstream: Optional[str] = None
    outside_v4: Optional[str] = None
    matched: Optional[str] = None
    not_duplicates: List[Dict[str, str]] = field(default_factory=list)
    status: str = 'new'
    proposed: Optional[str] = None
    theme: Optional[str] = None
    dig: Optional[str] = None
    waiting_for: Optional[str] = None
    fixing: Optional[str] = None
    links: List[str] = field(default_factory=list)
    merged_between: List[str] = field(default_factory=list)
    caused_by: Optional[str] = None
    ended_between: List[str] = field(default_factory=list)
    occurrences: List[Occurrence] = field(default_factory=list)
    evidence: Optional[str] = None
    reproduce: Optional[str] = None
    context: Optional[str] = None
    changed: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)

    @property
    def label(self) -> str:
        """How the finding is named for people: its name, or its ID"""
        return self.name or self.id

    @property
    def rows(self) -> List[str]:
        """The rows the finding was seen on, sorted"""
        return sorted({occurrence.row for occurrence in self.occurrences})

    def note(self, change: str, day: Optional[str] = None) -> None:
        """
        Add a line to the finding's history

        Parameters
        ----------
        change : str
            What changed

        day : str, optional
            The date of the hunt, today by default
        """
        if day is None:
            day = today()
        self.history.append({'hunt': day, 'change': change})

    def occurrence(self, test: str, row: str) -> Optional[Occurrence]:
        """The occurrence of a test on a row, if there is one"""
        for occurrence in self.occurrences:
            if occurrence.test == test and occurrence.row == row:
                return occurrence
        return None


class Ledger:
    """
    A clone of the ledger repository

    Parameters
    ----------
    path : str
        The clone's directory
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock_file: Optional[IO[str]] = None
        #: the hunt commands write to, if one is chosen or started
        self.hunt: Optional[str] = None
        if not os.path.isdir(os.path.join(path, '.git')):
            raise LedgerError(
                f'{path} is not a clone of a ledger repository.  Clone the '
                f'ledger there, or set "ledger" in the [bug_hunt] section '
                f'of your config file.'
            )

    def findings(self) -> Dict[str, Finding]:
        """
        Read every finding

        Returns
        -------
        findings : dict of str to bug_hunt_ledger.Finding
            The findings, by ID
        """
        directory = os.path.join(self.path, FINDINGS_DIR)
        found: Dict[str, Finding] = {}
        if not os.path.isdir(directory):
            return found
        for filename in sorted(os.listdir(directory)):
            if filename.endswith('.yaml'):
                finding = read_finding(os.path.join(directory, filename))
                found[finding.id] = finding
        return found

    def get(self, ref: str) -> Finding:
        """
        Read a finding by its ID or its name, or raise an error if there is
        none
        """
        filename = self._finding_path(ref)
        if os.path.exists(filename):
            return read_finding(filename)
        finding = self.by_name(ref)
        if finding is None:
            raise LedgerError(f'The ledger has no finding "{ref}".')
        return finding

    def by_name(
        self, name: str, findings: Optional[Dict[str, Finding]] = None
    ) -> Optional[Finding]:
        """The finding with a name, ignoring case and spacing, if any"""
        if findings is None:
            findings = self.findings()
        wanted = _name_key(name)
        for finding in findings.values():
            if finding.name and _name_key(finding.name) == wanted:
                return finding
        return None

    def unique_name(
        self, name: str, findings: Optional[Dict[str, Finding]] = None
    ) -> str:
        """
        A name no other finding has: the name itself, or with a number
        after it
        """
        if findings is None:
            findings = self.findings()
        candidate = name
        number = 2
        while self.by_name(candidate, findings) is not None:
            candidate = f'{name} ({number})'
            number += 1
        return candidate

    def save(self, finding: Finding) -> None:
        """Write a finding"""
        os.makedirs(os.path.join(self.path, FINDINGS_DIR), exist_ok=True)
        write_finding(finding, self._finding_path(finding.id))

    def remove(self, finding_id: str) -> None:
        """Remove a finding, which git history keeps"""
        os.remove(self._finding_path(finding_id))

    def find(
        self,
        findings: Dict[str, Finding],
        test: str,
        phase: str,
        message: Optional[str],
        row: str,
    ) -> Optional[Finding]:
        """
        The finding a failure belongs to, if any

        A key limited to rows that include ``row`` wins over a key with no
        rows, so that a finding split off for some rows keeps them.

        Parameters
        ----------
        findings : dict of str to bug_hunt_ledger.Finding
            The findings to look in

        test, phase, message : str
            The parts of the failure's key

        row : str
            The row the failure is on

        Returns
        -------
        finding : bug_hunt_ledger.Finding, optional
            The finding, or ``None`` if no key matches
        """
        best: Tuple[int, Optional[Finding]] = (0, None)
        for finding in findings.values():
            for key in finding.keys:
                score = key.matches(test, phase, message, row)
                if score > best[0]:
                    best = (score, finding)
        return best[1]

    def new_id(self, key: Key, day: Optional[str] = None) -> str:
        """
        A new finding's ID: the date and a hash of its first key

        Parameters
        ----------
        key : bug_hunt_ledger.Key
            The finding's first key

        day : str, optional
            The date, today by default

        Returns
        -------
        finding_id : str
            ``F-<yyyymmdd>-<hash>``, longer if a shorter one is taken
        """
        if day is None:
            day = today()
        digest = hashlib.sha1(key.text().encode('utf-8')).hexdigest()
        stem = f'F-{day.replace("-", "")}'
        for length in (4, 6, 8, 40):
            finding_id = f'{stem}-{digest[:length]}'
            if not os.path.exists(self._finding_path(finding_id)):
                return finding_id
        raise LedgerError(f'Could not make a new ID for {key.text()}.')

    def start_hunt(self, day: Optional[str] = None) -> str:
        """
        Begin a hunt's record, numbered within its day, and make it the
        hunt this clone writes to

        Parameters
        ----------
        day : str, optional
            The date, today by default

        Returns
        -------
        name : str
            ``<yyyy-mm-dd>-<n>``, such as ``2026-11-12-2``
        """
        if day is None:
            day = today()
        name = self._next_hunt_name(day)
        self.save_hunt(_empty_hunt(name, uuid.uuid4().hex))
        self.use_hunt(name)
        return name

    def use_hunt(self, name: Optional[str] = None) -> Optional[str]:
        """
        Choose the hunt commands write to: the one named, or else the one
        this clone started last, if any

        Parameters
        ----------
        name : str, optional
            A hunt's name, as ``start`` printed it

        Returns
        -------
        name : str, optional
            The hunt chosen, or ``None`` if this clone has started none
        """
        if name is not None:
            if not os.path.exists(self._hunt_path(name, '.yaml')):
                raise LedgerError(f'The ledger has no hunt {name}.')
            self.hunt = name
            with open(self._current_hunt_path(), 'w') as handle:
                handle.write(f'{name}\n')
            return name
        path = self._current_hunt_path()
        if os.path.exists(path):
            with open(path) as handle:
                current = handle.read().strip()
            if current and os.path.exists(self._hunt_path(current, '.yaml')):
                self.hunt = current
        return self.hunt

    def load_hunt(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        The record of a hunt

        Parameters
        ----------
        name : str, optional
            The hunt's name; by default, the hunt chosen with
            :py:meth:`use_hunt`, or the one this clone started last, or
            else a new one, started now

        Returns
        -------
        record : dict
            ``name``, ``id``, ``date`` (the day it started), ``covered``
            (what was harvested or reviewed), ``touched`` (finding IDs) and
            ``decisions``, and ``reviewed`` (the files a review read, by
            repository, with the commit each was read at) once a review is
            recorded
        """
        if name is None:
            name = self.hunt or self.use_hunt()
        if name is None:
            name = self.start_hunt()
            print(f'Started hunt {name}, since this clone had none.')
        filename = self._hunt_path(name, '.yaml')
        if not os.path.exists(filename):
            return _empty_hunt(name, uuid.uuid4().hex)
        record = _read_yaml(filename)
        record.setdefault('name', name)
        return record

    def save_hunt(self, record: Dict[str, Any]) -> None:
        """Write the record of a hunt"""
        os.makedirs(os.path.join(self.path, HUNTS_DIR), exist_ok=True)
        name = record.get('name') or record['date']
        _write_yaml(record, self._hunt_path(name, '.yaml'))

    def save_digest(self, name: str, text: str) -> str:
        """
        Write a hunt's digest and return its path

        A digest written again in the same hunt is saved beside the earlier
        ones, as ``<hunt>.2.md`` and so on, so the ledger keeps what the
        developer was shown each time.
        """
        os.makedirs(os.path.join(self.path, HUNTS_DIR), exist_ok=True)
        filename = self._hunt_path(name, '.md')
        revision = 2
        while os.path.exists(filename):
            filename = self._hunt_path(name, f'.{revision}.md')
            revision += 1
        with open(filename, 'w') as handle:
            handle.write(text)
        return filename

    def holds(self) -> Dict[str, Dict[str, str]]:
        """
        The rows on hold

        Returns
        -------
        holds : dict of str to dict
            For each ``<machine>/<compiler>`` row, its ``reason`` and the
            date it was put on hold, ``since``
        """
        filename = os.path.join(self.path, HOLDS_FILE)
        if not os.path.exists(filename):
            return {}
        return dict(_read_yaml(filename).get('rows') or {})

    def save_holds(self, holds: Dict[str, Dict[str, str]]) -> None:
        """Write the rows on hold"""
        _write_yaml(
            {
                'schema_version': SCHEMA_VERSION,
                'rows': {row: holds[row] for row in sorted(holds)},
            },
            os.path.join(self.path, HOLDS_FILE),
        )

    def outside_v4(self) -> Dict[str, Dict[str, str]]:
        """
        The features and options outside E3SM v4

        Returns
        -------
        entries : dict of str to dict
            For each entry's name, its ``description``, its ``source`` and
            the date it was added, ``since``
        """
        filename = os.path.join(self.path, OUTSIDE_V4_FILE)
        if not os.path.exists(filename):
            return {}
        return dict(_read_yaml(filename).get('entries') or {})

    def save_outside_v4(self, entries: Dict[str, Dict[str, str]]) -> None:
        """Write the features and options outside E3SM v4"""
        _write_yaml(
            {
                'schema_version': SCHEMA_VERSION,
                'entries': {name: entries[name] for name in sorted(entries)},
            },
            os.path.join(self.path, OUTSIDE_V4_FILE),
        )

    def name_terms(self) -> List[str]:
        """
        The terms finding names may use beyond plain words: names Omega
        developers know, such as those of components, schemes, machines and
        suites
        """
        filename = os.path.join(self.path, NAME_TERMS_FILE)
        if not os.path.exists(filename):
            return []
        return [str(term) for term in _read_yaml(filename).get('terms') or []]

    def save_name_terms(self, terms: List[str]) -> None:
        """Write the terms finding names may use"""
        _write_yaml(
            {
                'schema_version': SCHEMA_VERSION,
                'terms': sorted(set(terms), key=str.lower),
            },
            os.path.join(self.path, NAME_TERMS_FILE),
        )

    def hunts(self) -> List[Dict[str, Any]]:
        """The records of every hunt, by date and then number"""
        return [
            _read_yaml(self._hunt_path(name, '.yaml'))
            for name in self._hunt_names()
        ]

    def covered(self, what: str) -> Optional[str]:
        """
        What past hunts recorded as covered, such as the last night
        harvested from CDash or the last commit reviewed

        Parameters
        ----------
        what : str
            The entry in ``covered``, such as ``cdash`` or ``review``

        Returns
        -------
        value : str, optional
            The latest date, for an entry that is a date, or else the value
            the latest hunt recorded; ``None`` if no hunt covered it
        """
        values = [
            hunt['covered'][what]
            for hunt in self.hunts()
            if what in hunt.get('covered', {})
        ]
        if not values:
            return None
        if what in COVERED_DATES:
            return max(str(value) for value in values)
        return values[-1]

    def reviewed(self) -> Dict[str, Dict[str, str]]:
        """
        The files past reviews read, and the commit each was last read at

        Returns
        -------
        reviewed : dict of str to dict of str to str
            For each repository (``omega`` or ``polaris``), each file's
            path and the commit a review last read it at
        """
        reviewed: Dict[str, Dict[str, str]] = {}
        for hunt in self.hunts():
            for repo, files in (hunt.get('reviewed') or {}).items():
                reviewed.setdefault(repo, {}).update(files)
        return reviewed

    def sync(self) -> None:
        """
        Take the clone's lock, and pull the ledger's remote if it has one

        Commits not yet pushed are rebased onto the remote.  Concurrent
        changes to a hunt's record are merged; any other conflict aborts
        the rebase, so the clone is never left part way through one.
        """
        self._lock()
        if self._rebasing():
            raise LedgerError(
                f'A rebase is in progress in {self.path}.  Finish it '
                f'("git rebase --continue") or abort it ("git rebase '
                f'--abort") before using the ledger.'
            )
        remote = self._remote()
        if remote is None:
            return
        error = self._pull(remote)
        if error is not None:
            print(f'Warning: could not pull the ledger:\n{error}', flush=True)

    def commit(self, message: str) -> None:
        """
        Commit any changes to findings, hunts and holds, and push them if
        the ledger has a remote

        A push the remote rejects pulls and tries again.  A push that still
        fails leaves the commit in the clone, and the next command that
        commits pushes it.
        """
        paths = [
            path
            for path in (
                FINDINGS_DIR,
                HUNTS_DIR,
                HOLDS_FILE,
                OUTSIDE_V4_FILE,
                NAME_TERMS_FILE,
            )
            if os.path.exists(os.path.join(self.path, path))
            or _git(self.path, ['ls-files', path], check=False).stdout
        ]
        if not paths:
            return
        _git(self.path, ['add', '--all', '--'] + paths, check=True)
        status = _git(
            self.path, ['status', '--porcelain', '--'] + paths, check=True
        )
        if status.stdout.strip():
            _git(self.path, ['commit', '--quiet', '-m', message], check=True)
        remote = self._remote()
        if remote is None:
            return
        error = None
        for _ in range(PUSH_ATTEMPTS):
            # the remote and branch are named, since git's push.default may
            # be "nothing"
            result = _git(
                self.path,
                ['push', '--quiet', remote[0], f'HEAD:{remote[1]}'],
                check=False,
            )
            if result.returncode == 0:
                return
            error = result.stderr
            # another clone pushed since this one pulled
            pull_error = self._pull(remote)
            if pull_error is not None:
                error = pull_error
                break
        print(
            f'Warning: the ledger was committed but not pushed:\n{error}',
            flush=True,
        )

    def _pull(self, remote: Tuple[str, str]) -> Optional[str]:
        """
        Pull with a rebase, merging conflicts in hunts' records

        Returns
        -------
        error : str, optional
            Why the pull failed, or ``None`` if it succeeded.  A failed pull
            leaves the clone as it was.
        """
        result = _git(
            self.path,
            ['pull', '--rebase', '--quiet', remote[0], remote[1]],
            check=False,
        )
        # hunts that took a name another clone pushed first, and the names
        # they take instead
        renamed: Dict[str, str] = {}
        while self._rebasing():
            conflicts = _git(
                self.path,
                ['diff', '--name-only', '--diff-filter=U'],
                check=True,
            ).stdout.split()
            staged = _git(
                self.path, ['diff', '--cached', '--quiet'], check=False
            )
            if not conflicts and staged.returncode == 0:
                # the merge left the replayed commit with nothing to add
                action = 'skip'
            elif conflicts and all(_is_hunt_file(path) for path in conflicts):
                # records first, so a digest follows its record's new name
                for path in sorted(conflicts, key=lambda p: p.endswith('.md')):
                    self._resolve_hunt_file(path, renamed)
                action = 'continue'
            else:
                _git(self.path, ['rebase', '--abort'], check=False)
                return (
                    f'{result.stderr}The rebase conflicted in '
                    f'{", ".join(conflicts) or "an unknown file"} and was '
                    f'aborted, so the commits not yet pushed are still in '
                    f'the clone.  Every pull will conflict the same way '
                    f'until it is resolved by hand: "git -C {self.path} '
                    f'pull --rebase {remote[0]} {remote[1]}", resolve the '
                    f'conflicts, "git add" them and "git rebase --continue".'
                )
            result = _git(
                self.path,
                ['-c', 'core.editor=true', 'rebase', f'--{action}'],
                check=False,
            )
        if result.returncode != 0:
            return result.stderr
        return None

    def _resolve_hunt_file(self, path: str, renamed: Dict[str, str]) -> None:
        """
        Resolve a conflict in a hunt's record or digest, between the
        remote's version (stage 2 in a rebase) and that of the commit being
        replayed (stage 3)

        Two versions of one hunt, written from two clones, are merged.  A
        different hunt that took the same name, started in another clone
        that pushed first, takes the next number, and so does its digest;
        ``renamed`` collects the new names.
        """
        replayed = _git(self.path, ['show', f':3:{path}'], check=True).stdout
        upstream = _git(self.path, ['show', f':2:{path}'], check=True).stdout
        filename = os.path.join(self.path, path)
        # a hunt's name, and what follows it: .yaml, .md or .<n>.md
        name, dot, rest = os.path.basename(path).partition('.')
        suffix = f'{dot}{rest}'
        if path.endswith('.yaml'):
            yaml = YAML(typ='safe')
            theirs, mine = yaml.load(upstream), yaml.load(replayed)
            other_hunt = (
                theirs.get('id') is not None
                and mine.get('id') is not None
                and theirs['id'] != mine['id']
            )
            if name in renamed or other_hunt:
                new = renamed.get(name) or self._next_hunt_name(
                    hunt_order(name)[0], taken=set(renamed.values())
                )
                renamed[name] = new
                mine['name'] = new
                _write_yaml(mine, self._hunt_path(new, '.yaml'))
                self._restore(filename, upstream)
                self._follow_rename(name, new)
                new_path = self._hunt_path(new, '.yaml')
                _git(self.path, ['add', '--', path, new_path], check=True)
                return
            _write_yaml(merge_hunts(theirs, mine), filename)
        elif name in renamed:
            new_path = self._hunt_path(renamed[name], suffix)
            with open(new_path, 'w') as handle:
                handle.write(replayed)
            self._restore(filename, upstream)
            _git(self.path, ['add', '--', path, new_path], check=True)
            return
        else:
            # the digest being replayed was written after the remote's
            with open(filename, 'w') as handle:
                handle.write(replayed)
        _git(self.path, ['add', '--', path], check=True)

    @staticmethod
    def _restore(filename: str, text: str) -> None:
        """Put back the remote's version of a file"""
        with open(filename, 'w') as handle:
            handle.write(text)

    def _follow_rename(self, old: str, new: str) -> None:
        """Point the clone at a hunt's new name, if it was the current one"""
        path = self._current_hunt_path()
        if os.path.exists(path):
            with open(path) as handle:
                current = handle.read().strip()
            if current == old:
                with open(path, 'w') as handle:
                    handle.write(f'{new}\n')
        if self.hunt == old:
            self.hunt = new

    def _hunt_names(self) -> List[str]:
        """The names of the hunts in the clone, by date and then number"""
        directory = os.path.join(self.path, HUNTS_DIR)
        if not os.path.isdir(directory):
            return []
        names = [
            filename[: -len('.yaml')]
            for filename in os.listdir(directory)
            if filename.endswith('.yaml')
        ]
        return sorted(names, key=hunt_order)

    def _next_hunt_name(self, day: str, taken: Container[str] = ()) -> str:
        """The next free number for a hunt starting on a day"""
        numbers = [
            hunt_order(name)[1]
            for name in self._hunt_names()
            if hunt_order(name)[0] == day
        ]
        number = max(numbers, default=0) + 1
        while f'{day}-{number}' in taken:
            number += 1
        return f'{day}-{number}'

    def _hunt_path(self, name: str, suffix: str) -> str:
        return os.path.join(self.path, HUNTS_DIR, f'{name}{suffix}')

    def _current_hunt_path(self) -> str:
        return os.path.join(self.path, '.git', CURRENT_HUNT_FILE)

    def _lock(self) -> None:
        """
        Hold the clone's lock until this process ends, so that two commands
        in one clone cannot change it at the same time
        """
        if self._lock_file is not None:
            return
        filename = _git(
            self.path, ['rev-parse', '--git-path', 'bug_hunt.lock'], check=True
        ).stdout.strip()
        handle = open(os.path.join(self.path, filename), 'a')
        try:
            fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(
                f'Waiting for another bug_hunt.py command using {self.path}',
                flush=True,
            )
            fcntl.lockf(handle, fcntl.LOCK_EX)
        self._lock_file = handle

    def _rebasing(self) -> bool:
        """Whether a rebase is in progress in the clone"""
        for name in ('rebase-merge', 'rebase-apply'):
            directory = _git(
                self.path, ['rev-parse', '--git-path', name], check=True
            ).stdout.strip()
            if os.path.isdir(os.path.join(self.path, directory)):
                return True
        return False

    def _finding_path(self, finding_id: str) -> str:
        return os.path.join(self.path, FINDINGS_DIR, f'{finding_id}.yaml')

    def _remote(self) -> Optional[Tuple[str, str]]:
        """
        The remote and branch the ledger syncs with: the current branch's
        upstream, or else the first remote and a branch of the same name
        """
        remotes = _git(self.path, ['remote'], check=False).stdout.split()
        if not remotes:
            return None
        upstream = _git(
            self.path,
            ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'],
            check=False,
        ).stdout.strip()
        for remote in remotes:
            if upstream.startswith(f'{remote}/'):
                return remote, upstream[len(remote) + 1 :]
        branch = _git(
            self.path, ['rev-parse', '--abbrev-ref', 'HEAD'], check=True
        ).stdout.strip()
        return remotes[0], branch


def hunt_order(name: str) -> Tuple[str, int]:
    """
    A hunt's date and number, to sort hunts by; a record from before hunts
    were numbered counts as number 0 of its day

    Parameters
    ----------
    name : str
        The hunt's name, such as ``2026-11-12-2``

    Returns
    -------
    order : tuple of str and int
        The date and the number
    """
    match = _HUNT_NAME.match(name)
    if match is None:
        return (name, 0)
    return (match[1], int(match[2] or 0))


def _empty_hunt(name: str, hunt_id: str) -> Dict[str, Any]:
    """A new hunt's record"""
    return {
        'schema_version': SCHEMA_VERSION,
        'name': name,
        'id': hunt_id,
        'date': hunt_order(name)[0],
        'covered': {},
        'touched': [],
        'decisions': [],
    }


def today() -> str:
    """Today's date as ``yyyy-mm-dd``"""
    return datetime.date.today().isoformat()


def record_answer(hunt: Dict[str, Any], finding_id: str, answer: str) -> None:
    """
    Record the developer's answer to a decision in a hunt's record

    The answer fills in the decision the digest asked for, or is added if
    the digest did not ask about the finding.

    Parameters
    ----------
    hunt : dict
        The hunt's record, from ``Ledger.load_hunt()``

    finding_id : str
        The finding answered about

    answer : str
        One of ``ACTIONS``
    """
    if answer not in ACTIONS:
        raise LedgerError(f'"{answer}" is not one of {", ".join(ACTIONS)}.')
    for decision in hunt['decisions']:
        if decision['id'] == finding_id and decision['answer'] is None:
            decision['answer'] = answer
            return
    hunt['decisions'].append({'id': finding_id, 'answer': answer})


def rubric_priority(
    finding: Finding, outside_v4: Optional[Container[str]] = None
) -> Optional[str]:
    """
    The priority the rubric in ``AGENTS.md`` gives a finding

    A speculative finding is ranked as an inferred one; the digest holds it
    back until it is confirmed.  An Omega finding that matters only outside
    E3SM v4 moves down one level, but no lower than P3.  A finding that came
    back after its issue was closed, or after it was fixed, moves up one
    level.  A failure that has ended moves down one level, but no lower
    than P3.

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    outside_v4 : container of str, optional
        The entries outside v4, from ``Ledger.outside_v4()``.  A finding's
        entry counts only if it is still among them; if this is not given,
        the finding's entry is taken as it is.

    Returns
    -------
    priority : str, optional
        The priority, or ``None`` until the finding has a severity and a
        confidence
    """
    if finding.severity is None or finding.confidence is None:
        return None
    measured = finding.confidence == 'measured'
    several_rows = len(finding.rows) > 1
    if finding.severity == 'S1':
        level = 1 if measured else 2
    elif finding.severity == 'S2':
        if measured:
            level = 1 if several_rows else 2
        else:
            level = 3
    elif finding.severity == 'S3':
        level = 2 if measured and several_rows else 3
    else:
        level = 4
    if (
        finding.owner == 'omega'
        and finding.outside_v4 is not None
        and (outside_v4 is None or finding.outside_v4 in outside_v4)
    ):
        level = max(level, min(level + 1, 3))
    if finding.ended is not None:
        level = max(level, min(level + 1, 3))
    if finding.came_back:
        level = max(1, level - 1)
    return f'P{level}'


def set_priority(
    finding: Finding, outside_v4: Optional[Container[str]] = None
) -> Optional[str]:
    """
    Set a finding's priority from the rubric, unless it was set by hand

    ``outside_v4`` is as for :py:func:`rubric_priority`.

    Returns
    -------
    change : str, optional
        The change, such as ``priority=P2``, or ``None`` if there was none
    """
    if finding.priority_note is not None:
        return None
    priority = rubric_priority(finding, outside_v4)
    if priority is None or priority == finding.priority:
        return None
    finding.priority = priority
    return f'priority={priority}'


def merge_hunts(
    upstream: Dict[str, Any], replayed: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Merge two versions of a hunt's record, written by different clones

    Parameters
    ----------
    upstream : dict
        The remote's version

    replayed : dict
        The version in the commit being rebased onto it

    Returns
    -------
    record : dict
        The findings either touched, every decision either asked for with
        the answers either recorded, the later of each date covered, and
        every file either reviewed
    """
    record = dict(upstream)
    mine = replayed.get('covered', {})
    covered = dict(upstream.get('covered', {}))
    for what, value in mine.items():
        if what == 'review':
            continue
        if what not in COVERED_DATES or str(value) > str(
            covered.get(what, '')
        ):
            covered[what] = value
    # the description of a review goes with the later of its dates
    if 'review' in mine and covered.get('review_until') == mine.get(
        'review_until'
    ):
        covered['review'] = mine['review']
    record['covered'] = covered
    reviewed = {
        repo: dict(files)
        for repo, files in (upstream.get('reviewed') or {}).items()
    }
    for repo, files in (replayed.get('reviewed') or {}).items():
        reviewed.setdefault(repo, {}).update(files)
    if reviewed:
        record['reviewed'] = reviewed
    ready = set(upstream.get('ready_to_close') or [])
    ready.update(replayed.get('ready_to_close') or [])
    if ready:
        record['ready_to_close'] = sorted(ready)
    touched = list(upstream.get('touched', []))
    for finding_id in replayed.get('touched', []):
        if finding_id not in touched:
            touched.append(finding_id)
    record['touched'] = touched
    decisions = [dict(decision) for decision in upstream.get('decisions', [])]
    for decision in replayed.get('decisions', []):
        if decision in decisions:
            continue
        same = [entry for entry in decisions if entry['id'] == decision['id']]
        if decision['answer'] is None:
            if not same:
                decisions.append(dict(decision))
            continue
        unanswered = [entry for entry in same if entry['answer'] is None]
        if unanswered:
            unanswered[0]['answer'] = decision['answer']
        else:
            decisions.append(dict(decision))
    record['decisions'] = decisions
    return record


def split_evidence(evidence: Optional[str]) -> Tuple[str, str]:
    """
    Split a finding's evidence into its opening paragraph, which summarizes
    the case for the finding, and the excerpts that follow it

    Parameters
    ----------
    evidence : str, optional
        The evidence

    Returns
    -------
    opening : str
        The first paragraph, on one line

    rest : str
        Everything after the first blank line, as it was written
    """
    text = (evidence or '').strip()
    if not text:
        return '', ''
    parts = re.split(r'\n\s*\n', text, maxsplit=1)
    opening = ' '.join(parts[0].split())
    rest = parts[1].rstrip() if len(parts) > 1 else ''
    return opening, rest


def read_finding(filename: str) -> Finding:
    """
    Read a finding from a YAML file

    Parameters
    ----------
    filename : str
        The file

    Returns
    -------
    finding : bug_hunt_ledger.Finding
        The finding
    """
    data = _read_yaml(filename)
    version = data.pop('schema_version', SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise LedgerError(
            f'{filename} has schema version {version}, but this utility '
            f'reads version {SCHEMA_VERSION}.'
        )
    known = {item.name for item in fields(Finding)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise LedgerError(f'{filename} has unknown fields: {unknown}')
    data['keys'] = [Key(**key) for key in data.get('keys', [])]
    data['occurrences'] = [
        Occurrence(**occurrence) for occurrence in data.get('occurrences', [])
    ]
    return Finding(**data)


def write_finding(finding: Finding, filename: str) -> None:
    """
    Write a finding to a YAML file, leaving out empty fields

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    filename : str
        The file
    """
    data: Dict[str, Any] = {'schema_version': SCHEMA_VERSION}
    values = asdict(finding)
    # the name goes just after the ID, where a person reading the file
    # looks for it
    ordered = {'id': values.pop('id'), 'name': values.pop('name')}
    ordered.update(values)
    for name, value in ordered.items():
        if value is None or value in ([], '') or value is False:
            continue
        if name == 'keys':
            value = [_drop_none(key) for key in value]
        elif name == 'occurrences':
            value = [_drop_none(occurrence) for occurrence in value]
        data[name] = value
    _write_yaml(data, filename)


def unlisted_terms(name: str, terms: Iterable[str]) -> List[str]:
    """
    The words in a name that look like jargon (with an underscore, digits
    among letters, or more than one capital letter) and are not among the
    terms names may use

    Parameters
    ----------
    name : str
        A finding's name

    terms : iterable of str
        The terms names may use, from ``Ledger.name_terms()``

    Returns
    -------
    words : list of str
        The words to reword or, if the developer used them, add to the
        terms
    """
    allowed = {term.lower() for term in terms}
    words = []
    for word in name.split():
        word = word.strip('.,;:()"\'').removesuffix("'s")
        # plain numbers, as in dates, are words like any other
        if not word or word.lower() in allowed or word.isdigit():
            continue
        capitals = sum(1 for char in word if char.isupper())
        if '_' in word or any(char.isdigit() for char in word) or capitals > 1:
            words.append(word)
    return words


def _name_key(name: str) -> str:
    """A name as compared with others: lower case, single spaces"""
    return ' '.join(name.lower().split())


def _drop_none(item: Dict[str, Any]) -> Dict[str, Any]:
    return {name: value for name, value in item.items() if value is not None}


def _read_yaml(filename: str) -> Dict[str, Any]:
    yaml = YAML(typ='safe')
    with open(filename) as handle:
        data = yaml.load(handle)
    if not isinstance(data, dict):
        raise LedgerError(f'{filename} does not hold a YAML mapping.')
    return data


def _write_yaml(data: Dict[str, Any], filename: str) -> None:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.width = 79
    stream = io.StringIO()
    yaml.dump(_literal_blocks(data), stream)
    tmp_filename = f'{filename}.tmp'
    with open(tmp_filename, 'w') as handle:
        handle.write(stream.getvalue())
    os.replace(tmp_filename, filename)


def _literal_blocks(value: Any) -> Any:
    """Write strings with line breaks as YAML literal blocks"""
    if isinstance(value, dict):
        return {key: _literal_blocks(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_literal_blocks(item) for item in value]
    if isinstance(value, str) and '\n' in value:
        return LiteralScalarString(value)
    return value


def _is_hunt_file(path: str) -> bool:
    """Whether a path in the clone is a hunt's record or digest"""
    directory, filename = os.path.split(path)
    return directory == HUNTS_DIR and filename.endswith(('.yaml', '.md'))


def _git(
    path: str, args: List[str], check: bool
) -> 'subprocess.CompletedProcess[str]':
    result = subprocess.run(
        ['git', '-C', path] + args, capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise LedgerError(
            f'"git {" ".join(args)}" failed in {path}:\n{result.stderr}'
        )
    return result
