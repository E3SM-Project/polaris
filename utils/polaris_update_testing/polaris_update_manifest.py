"""
The manifest that pins what every machine tests for a Polaris version
update, and the rows the new version supports
"""

import io
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pr_test_git as git_tools
from pr_test_git import OMEGA_SUBMODULE, REF_PREFIX
from pr_test_rows import Row
from pr_test_setup import E3SM_SUBMODULE
from ruamel.yaml import YAML

SCHEMA_VERSION = 1

#: the file the initiator commits on top of the PR's head
MANIFEST_FILENAME = 'polaris_update_test.yaml'

#: the repository whose pull requests are tested
UPSTREAM = 'E3SM-Project/polaris'

#: what the utility's Testing comments are marked with
MARKER_PREFIX = 'polaris-update-test'

#: the suite each model's rows run
SUITES = {'omega': 'omega_pr', 'mpas-ocean': 'mpaso_pr'}

#: the table of the machines, compilers and MPI libraries Polaris supports
SUPPORTED_MACHINES = 'docs/developers_guide/supported_machines.yaml'

#: the file that gives the Polaris version
VERSION_FILE = 'polaris/version.py'

#: the models in the table of supported machines, by their names there
_MODELS = {'Omega': 'omega', 'MPAS': 'mpas-ocean'}

_VERSION = re.compile(r"""^__version__ = ['"]([^'"]+)['"]""", re.MULTILINE)


class ManifestError(Exception):
    """A manifest is missing, malformed or of an unknown version"""


@dataclass(frozen=True)
class PolarisSide:
    """
    A Polaris commit and what it pins

    Attributes
    ----------
    polaris_commit : str
        The Polaris commit

    polaris_version : str
        Its version

    omega_commit : str
        The Omega commit it pins

    e3sm_commit : str
        The E3SM commit it pins, which MPAS-Ocean is built from
    """

    polaris_commit: str
    polaris_version: str
    omega_commit: str
    e3sm_commit: str

    def to_dict(self) -> Dict[str, str]:
        """The side as it is written in the manifest"""
        return {
            'polaris_commit': self.polaris_commit,
            'polaris_version': self.polaris_version,
            'omega_commit': self.omega_commit,
            'e3sm_commit': self.e3sm_commit,
        }


@dataclass(frozen=True)
class OmegaMerge:
    """
    The Omega built in place of the one the PR pins: that commit with other
    Omega PRs merged in, such as a fix still in review

    Attributes
    ----------
    commit : str
        The merge, which is built

    pull_requests : dict of int to str
        The head commit of each Omega PR merged in, by number

    fork : str
        The URL of the fork with the merge, the requester's E3SM fork

    branch : str
        The branch on the fork with the merge
    """

    commit: str
    pull_requests: Dict[int, str]
    fork: str
    branch: str

    def to_dict(self) -> Dict[str, Any]:
        """The merge as it is written in the manifest"""
        return {
            'commit': self.commit,
            'pull_requests': [
                {'pull_request': number, 'commit': head}
                for number, head in self.pull_requests.items()
            ],
            'fork': self.fork,
            'branch': self.branch,
        }

    @classmethod
    def from_dict(cls, contents: Dict[str, Any]) -> 'OmegaMerge':
        """Read the merge as it is written in the manifest"""
        return cls(
            commit=str(contents['commit']),
            pull_requests={
                int(merge['pull_request']): str(merge['commit'])
                for merge in contents['pull_requests']
            },
            fork=str(contents['fork']),
            branch=str(contents['branch']),
        )


def read_side(polaris_dir: str, commit: str) -> PolarisSide:
    """
    Read a Polaris commit's version and submodule pins

    Parameters
    ----------
    polaris_dir : str
        A Polaris checkout with the commit

    commit : str
        The commit

    Returns
    -------
    side : polaris_update_manifest.PolarisSide
        The commit and what it pins
    """
    text = git_tools.show_file(polaris_dir, commit, VERSION_FILE)
    match = _VERSION.search(text)
    if match is None:
        raise ManifestError(
            f'{VERSION_FILE} at {commit[:12]} does not give a version.'
        )
    return PolarisSide(
        polaris_commit=commit,
        polaris_version=match.group(1),
        omega_commit=git_tools.submodule_pin(
            polaris_dir, commit, OMEGA_SUBMODULE
        ),
        e3sm_commit=git_tools.submodule_pin(
            polaris_dir, commit, E3SM_SUBMODULE
        ),
    )


def read_rows(polaris_dir: str, commit: str) -> List[Row]:
    """
    The rows a Polaris commit supports, from its table of supported
    machines

    Parameters
    ----------
    polaris_dir : str
        A Polaris checkout with the commit

    commit : str
        The commit

    Returns
    -------
    rows : list of pr_test_rows.Row
        A row for each machine, compiler and model, MPAS-Ocean first on
        each machine, as the table lists them
    """
    text = git_tools.show_file(polaris_dir, commit, SUPPORTED_MACHINES)
    table = _yaml().load(text)
    rows = []
    for machine in table['machines']:
        for entry in machine['models']:
            if entry.get('compiler') is None:
                continue
            rows.append(
                Row(
                    machine=str(machine['name']),
                    compiler=str(entry['compiler']),
                    mpi=str(entry['mpi']),
                    model=_MODELS[str(entry['model'])],
                )
            )
    return rows


@dataclass
class Manifest:
    """
    What every machine tests

    Attributes
    ----------
    requester : str
        The GitHub user who asked for the testing

    pull_request : int
        The number of the Polaris pull request

    test : polaris_update_manifest.PolarisSide
        The pull request's head and what it pins

    baseline : polaris_update_manifest.PolarisSide, optional
        The Polaris commit to compare against and what it pins, if any

    rows : list of pr_test_rows.Row
        The rows to test

    notes : str, optional
        Notes for the requester, repeated in reports and never acted on

    omega_merge : polaris_update_manifest.OmegaMerge, optional
        Other Omega PRs merged into the Omega the PR pins, if any, which is
        then built in its place
    """

    requester: str
    pull_request: int
    test: PolarisSide
    baseline: Optional[PolarisSide] = None
    rows: List[Row] = field(default_factory=list)
    notes: Optional[str] = None
    omega_merge: Optional[OmegaMerge] = None

    @property
    def omega_build_commit(self) -> str:
        """The Omega commit the PR's Omega rows are built from"""
        if self.omega_merge is not None:
            return self.omega_merge.commit
        return self.test.omega_commit

    @property
    def pr_head(self) -> str:
        """The head commit of the pull request"""
        return self.test.polaris_commit

    @property
    def branch(self) -> str:
        """The name of the test branch on the requester's Polaris fork"""
        return f'polaris-update-test/{self.pull_request}-{self.pr_head[:7]}'

    @property
    def run_name(self) -> str:
        """The directory in the work base that this manifest's runs go in"""
        return f'polaris-pr{self.pull_request}-{self.pr_head[:7]}'

    def get_env_rows(self, machine: str, compiler: str) -> List[Row]:
        """The rows that a machine's load script for a compiler tests"""
        return [
            row
            for row in self.rows
            if row.machine == machine and row.compiler == compiler
        ]

    def to_yaml(self) -> str:
        """The manifest as the YAML that is committed"""
        contents: Dict[str, Any] = {
            'schema_version': SCHEMA_VERSION,
            'requester': self.requester,
            'pull_request': self.pull_request,
            'pr_head': self.pr_head,
            'polaris_version': self.test.polaris_version,
            'omega_commit': self.test.omega_commit,
            'e3sm_commit': self.test.e3sm_commit,
            'omega_merge': (
                None
                if self.omega_merge is None
                else self.omega_merge.to_dict()
            ),
            'baseline': (
                None if self.baseline is None else self.baseline.to_dict()
            ),
            'rows': [
                {
                    'machine': row.machine,
                    'compiler': row.compiler,
                    'mpi': row.mpi,
                    'model': row.model,
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
        manifest : polaris_update_manifest.Manifest
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
            baseline = contents.get('baseline')
            return cls(
                requester=str(contents['requester']),
                pull_request=int(contents['pull_request']),
                test=PolarisSide(
                    polaris_commit=str(contents['pr_head']),
                    polaris_version=str(contents['polaris_version']),
                    omega_commit=str(contents['omega_commit']),
                    e3sm_commit=str(contents['e3sm_commit']),
                ),
                baseline=(
                    None
                    if baseline is None
                    else PolarisSide(
                        **{key: str(value) for key, value in baseline.items()}
                    )
                ),
                rows=[
                    Row(
                        machine=str(row['machine']),
                        compiler=str(row['compiler']),
                        mpi=str(row['mpi']),
                        model=str(row['model']),
                    )
                    for row in contents.get('rows') or []
                ],
                notes=contents.get('notes'),
                omega_merge=(
                    None
                    if contents.get('omega_merge') is None
                    else OmegaMerge.from_dict(contents['omega_merge'])
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(
                f'The manifest is incomplete: {exc!r}'
            ) from exc


def fetch_manifest(polaris_dir: str, fork: str, branch: str) -> Manifest:
    """
    Fetch a test branch into a Polaris checkout, and read and check its
    manifest

    Parameters
    ----------
    polaris_dir : str
        The Polaris checkout to fetch into

    fork : str
        The URL of the requester's Polaris fork

    branch : str
        The test branch

    Returns
    -------
    manifest : polaris_update_manifest.Manifest
        The manifest, whose commits the checkout now has
    """
    local = f'{REF_PREFIX}/{branch}'
    git_tools.fetch(polaris_dir, fork, [f'refs/heads/{branch}:{local}'])
    tip = git_tools.rev_parse(polaris_dir, local)
    try:
        text = git_tools.show_file(polaris_dir, tip, MANIFEST_FILENAME)
    except git_tools.GitError as exc:
        raise ManifestError(
            f'{branch} on {fork} has no {MANIFEST_FILENAME} at its tip.'
        ) from exc
    manifest = Manifest.from_yaml(text)
    if git_tools.rev_parse(polaris_dir, f'{tip}^') != manifest.pr_head:
        raise ManifestError(
            f'The manifest on {branch} does not match its branch: the PR '
            f'head is not the parent of the tip.'
        )
    return manifest


def _yaml():
    # the round-trip loader constructs only plain data, and its dumper keeps
    # the order the fields are written in
    yaml = YAML(typ='rt')
    yaml.default_flow_style = False
    return yaml
