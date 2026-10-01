"""
The manifest that pins what every machine tests, and the rows of the Omega
PR template
"""

import configparser
import io
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Dict, List, Optional

import pr_test_git as git_tools
from pr_test_git import REF_PREFIX
from ruamel.yaml import YAML

SCHEMA_VERSION = 1

#: the file the initiator commits on top of the test commit
MANIFEST_FILENAME = 'omega_pr_test.yaml'

#: the repository whose pull requests are tested
UPSTREAM = 'E3SM-Project/Omega'

#: the baseline source that means the Omega commit Polaris pins
POLARIS_SUBMODULE = 'polaris-submodule'


class ManifestError(Exception):
    """A manifest is missing, malformed or of an unknown version"""


@dataclass(frozen=True)
class Row:
    """
    A machine, compiler and MPI library to test on

    Attributes
    ----------
    machine : str
        The Polaris machine

    compiler : str
        The Polaris compiler

    mpi : str
        The MPI library

    template : str, optional
        The row's label in the Omega PR template, if it has one
    """

    machine: str
    compiler: str
    mpi: str
    template: Optional[str] = None

    @property
    def name(self) -> str:
        """The row as ``<machine>/<compiler>``"""
        return f'{self.machine}/{self.compiler}'

    @property
    def label(self) -> str:
        """How reports name the row"""
        polaris = f'{self.machine}, {self.compiler}, {self.mpi}'
        if self.template is None or self.template == polaris:
            return polaris
        return f'{self.template} (Polaris `{self.compiler}`)'


#: the rows of the testing checklist in the Omega PR template.  The
#: template still calls Chrysalis's compiler ``oneapi-ifx``, which Polaris
#: calls ``intel``, until Omega catches up with E3SM's compiler names.
TEMPLATE_ROWS = [
    Row('aurora', 'oneapi-ifx', 'mpich', 'aurora, oneapi-ifx, mpich'),
    Row('chrysalis', 'intel', 'openmpi', 'chrysalis, oneapi-ifx, openmpi'),
    Row('frontier', 'craygnu', 'mpich', 'frontier, craygnu, mpich'),
    Row(
        'frontier',
        'craygnu-mphipcc',
        'mpich',
        'frontier, craygnu-mphipcc, mpich',
    ),
    Row('pm-cpu', 'gnu', 'mpich', 'pm-cpu, gnu, mpich'),
    Row('pm-gpu', 'gnugpu', 'mpich', 'pm-gpu, gnugpu, mpich'),
]


#: machines whose rows are tested from the same login nodes
SHARED_LOGIN_NODES = [{'pm-cpu', 'pm-gpu'}]


def get_machine_rows(rows: List[Row], machine: str) -> List[Row]:
    """
    The rows a tester on a machine runs: those of the machine, and of any
    machine that shares its login nodes

    Parameters
    ----------
    rows : list of pr_test_manifest.Row
        The rows to choose from

    machine : str
        The Polaris machine the tester is on

    Returns
    -------
    machine_rows : list of pr_test_manifest.Row
        The tester's rows, in order
    """
    machines = {machine}
    for group in SHARED_LOGIN_NODES:
        if machine in group:
            machines |= group
    return [row for row in rows if row.machine in machines]


def get_row(name: str) -> Row:
    """
    Get a row by ``<machine>/<compiler>``

    A row from the Omega PR template is returned as it is there.  Any
    other combination Polaris supports gets its MPI library from the
    Polaris machine config.

    Parameters
    ----------
    name : str
        The row as ``<machine>/<compiler>``

    Returns
    -------
    row : pr_test_manifest.Row
        The row
    """
    machine, separator, compiler = name.partition('/')
    if not separator or not machine or not compiler:
        raise ValueError(f'A row is <machine>/<compiler>, not "{name}".')
    for row in TEMPLATE_ROWS:
        if row.machine == machine and row.compiler == compiler:
            return row

    mpi = _get_polaris_mpi(machine, compiler)
    if mpi is None:
        raise ValueError(
            f'Polaris does not support compiler {compiler} on {machine}.'
        )
    return Row(machine, compiler, mpi)


@dataclass(frozen=True)
class ExtraMerge:
    """
    A pull request merged into the test or baseline commit as well

    Attributes
    ----------
    pull_request : int
        The number of the Omega pull request

    commit : str
        The head commit of that pull request that was merged

    sides : list of str
        ``test``, ``baseline`` or both
    """

    pull_request: int
    commit: str
    sides: List[str]


@dataclass
class Manifest:
    """
    What every machine tests

    Attributes
    ----------
    requester : str
        The GitHub user who asked for the testing

    pull_request : int
        The number of the Omega pull request

    pr_head : str
        The head commit of the pull request

    base_branch : str
        The branch the pull request targets

    base_head : str
        The head of the base branch when the test commit was made

    test_commit : str
        The merge of ``pr_head`` into ``base_head``, with any extra merges

    baseline_commit : str
        The Omega commit to compare against

    baseline_source : str
        :py:data:`POLARIS_SUBMODULE`, or the ref the requester chose instead

    baseline_reason : str, optional
        Why the requester chose a baseline other than the submodule

    polaris_commit : str
        The Polaris commit the pull request is tested with; every tester's
        Polaris must contain it

    baseline_polaris_commit : str
        The Polaris commit the baseline runs with, whose Omega submodule is
        the default baseline.  It is ``polaris_commit`` unless the pull
        request needs Polaris changes that the baseline Omega cannot run.

    extra_merges : list of pr_test_manifest.ExtraMerge
        Other pull requests merged into the test or baseline commit

    rows : list of pr_test_manifest.Row
        The rows to test

    notes : str, optional
        Notes for the requester, repeated in reports and never acted on
    """

    requester: str
    pull_request: int
    pr_head: str
    base_branch: str
    base_head: str
    test_commit: str
    baseline_commit: str
    baseline_source: str
    baseline_reason: Optional[str]
    polaris_commit: str
    baseline_polaris_commit: str
    extra_merges: List[ExtraMerge] = field(default_factory=list)
    rows: List[Row] = field(default_factory=list)
    notes: Optional[str] = None

    @property
    def branch(self) -> str:
        """The name of the test branch on the requester's fork"""
        return f'omega-pr-test/{self.pull_request}-{self.pr_head[:7]}'

    @property
    def baseline_branch(self) -> str:
        """The name of the baseline branch on the requester's fork"""
        return f'{self.branch}-baseline'

    @property
    def run_name(self) -> str:
        """The directory in the work base that this manifest's runs go in"""
        return f'pr{self.pull_request}-{self.pr_head[:7]}'

    def to_yaml(self) -> str:
        """The manifest as the YAML that is committed"""
        contents: Dict[str, Any] = {
            'schema_version': SCHEMA_VERSION,
            'requester': self.requester,
            'pull_request': self.pull_request,
            'pr_head': self.pr_head,
            'base_branch': self.base_branch,
            'base_head': self.base_head,
            'test_commit': self.test_commit,
            'baseline': {
                'commit': self.baseline_commit,
                'source': self.baseline_source,
                'reason': self.baseline_reason,
                'polaris_commit': self.baseline_polaris_commit,
            },
            'polaris_commit': self.polaris_commit,
            'extra_merges': [
                {
                    'pull_request': merge.pull_request,
                    'commit': merge.commit,
                    'sides': list(merge.sides),
                }
                for merge in self.extra_merges
            ],
            'rows': [
                {
                    'machine': row.machine,
                    'compiler': row.compiler,
                    'mpi': row.mpi,
                    'template': row.template,
                }
                for row in self.rows
            ],
            'notes': self.notes,
        }
        stream = io.StringIO()
        _yaml().dump(contents, stream)
        return stream.getvalue()

    @classmethod
    def from_yaml(cls, text: str) -> 'Manifest':
        """
        Read a manifest from the YAML that was committed

        Parameters
        ----------
        text : str
            The contents of the manifest file

        Returns
        -------
        manifest : pr_test_manifest.Manifest
            The manifest
        """
        try:
            contents = _yaml().load(text)
        except Exception as exc:
            raise ManifestError(
                f'The manifest is not valid YAML: {exc}'
            ) from exc
        if not isinstance(contents, dict):
            raise ManifestError('The manifest is not a YAML mapping.')

        version = contents.get('schema_version')
        if version != SCHEMA_VERSION:
            raise ManifestError(
                f'The manifest has schema version {version}, but this '
                f'utility reads version {SCHEMA_VERSION}.  Update Polaris, '
                f'or ask the requester which Polaris made it.'
            )

        try:
            baseline = contents['baseline']
            return cls(
                requester=str(contents['requester']),
                pull_request=int(contents['pull_request']),
                pr_head=str(contents['pr_head']),
                base_branch=str(contents['base_branch']),
                base_head=str(contents['base_head']),
                test_commit=str(contents['test_commit']),
                baseline_commit=str(baseline['commit']),
                baseline_source=str(baseline['source']),
                baseline_reason=baseline.get('reason'),
                polaris_commit=str(contents['polaris_commit']),
                baseline_polaris_commit=str(baseline['polaris_commit']),
                extra_merges=[
                    ExtraMerge(
                        pull_request=int(merge['pull_request']),
                        commit=str(merge['commit']),
                        sides=[str(side) for side in merge['sides']],
                    )
                    for merge in contents.get('extra_merges') or []
                ],
                rows=[
                    Row(
                        machine=str(row['machine']),
                        compiler=str(row['compiler']),
                        mpi=str(row['mpi']),
                        template=row.get('template'),
                    )
                    for row in contents.get('rows') or []
                ],
                notes=contents.get('notes'),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(
                f'The manifest is incomplete: {exc!r}'
            ) from exc

    def get_row(self, machine: str, compiler: str) -> Row:
        """
        Get one of the manifest's rows

        Parameters
        ----------
        machine : str
            The Polaris machine

        compiler : str
            The Polaris compiler

        Returns
        -------
        row : pr_test_manifest.Row
            The row
        """
        for row in self.rows:
            if row.machine == machine and row.compiler == compiler:
                return row
        names = ', '.join(row.name for row in self.rows)
        raise ManifestError(
            f'The manifest has no row for {machine}/{compiler}; its rows '
            f'are {names}.'
        )


def fetch_manifest(repo: str, fork: str, branch: str) -> Manifest:
    """
    Fetch a test branch and its baseline branch, and read and check the
    manifest

    Parameters
    ----------
    repo : str
        The Omega clone to fetch into

    fork : str
        The URL of the requester's fork

    branch : str
        The test branch

    Returns
    -------
    manifest : pr_test_manifest.Manifest
        The manifest, whose commits the clone now has
    """
    local = f'{REF_PREFIX}/{branch}'
    git_tools.fetch(
        repo,
        fork,
        [
            f'refs/heads/{branch}:{local}',
            f'refs/heads/{branch}-baseline:{local}-baseline',
        ],
    )
    tip = git_tools.rev_parse(repo, local)
    try:
        text = git_tools.show_file(repo, tip, MANIFEST_FILENAME)
    except git_tools.GitError as exc:
        raise ManifestError(
            f'{branch} on {fork} has no {MANIFEST_FILENAME} at its tip.'
        ) from exc
    manifest = Manifest.from_yaml(text)

    problems = []
    if git_tools.rev_parse(repo, f'{tip}^') != manifest.test_commit:
        problems.append('the test commit is not the parent of the tip')
    for name, sha in [
        ('PR head', manifest.pr_head),
        ('base branch head', manifest.base_head),
    ]:
        if not git_tools.is_ancestor(repo, sha, manifest.test_commit):
            problems.append(f'the test commit does not contain the {name}')
    baseline = git_tools.rev_parse(repo, f'{local}-baseline')
    if baseline != manifest.baseline_commit:
        problems.append(
            f'{branch}-baseline is at {baseline[:12]}, not the baseline '
            f'commit {manifest.baseline_commit[:12]}'
        )
    if problems:
        raise ManifestError(
            f'The manifest on {branch} does not match its branch: '
            f'{"; ".join(problems)}.'
        )
    return manifest


def _yaml():
    # the round-trip loader constructs only plain data, and its dumper keeps
    # the order the fields are written in
    yaml = YAML(typ='rt')
    yaml.default_flow_style = False
    return yaml


def _get_polaris_mpi(machine, compiler):
    """The MPI library Polaris uses with a compiler on a machine, if any"""
    filename = f'{machine}.cfg'
    try:
        text = (
            resources.files('polaris.machines')
            .joinpath(filename)
            .read_text(encoding='utf-8')
        )
    except (FileNotFoundError, OSError):
        return None
    parser = configparser.ConfigParser()
    parser.read_string(text)
    option = f'mpi_{compiler.replace("-", "_")}'
    value = parser.get('deploy', option, fallback='').strip()
    return value or None
