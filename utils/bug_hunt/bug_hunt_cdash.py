"""
Omega's nightly results on CDash: the builds of each night and the tests
that failed in them
"""

import configparser
import datetime
import glob
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ruamel.yaml import YAML

CDASH_URL = 'https://my.cdash.org'

#: the description of the CDash builds that are harvested
SOURCES_FILE = os.path.join(os.path.dirname(__file__), 'cdash.yaml')

#: the cron jobs' machine configs, which give the rows the nightly tasks
#: run on
CRON_MACHINES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'cron-scripts',
    'machines',
)

_GRAPHQL_TESTS = """
query($id: ID, $after: String) {
  build(id: $id) {
    tests(first: 200, after: $after, filters: {eq: {status: FAILED}}) {
      pageInfo { hasNextPage endCursor }
      edges { node { name status details output } }
    }
  }
}
"""


class CDashError(Exception):
    """A request to CDash failed or returned something unexpected"""


@dataclass
class BuildKind:
    """
    A kind of build that is harvested, recognized by its name

    Attributes
    ----------
    pattern : re.Pattern
        A pattern for the build name with a ``compiler`` group

    source : str
        ``ctest``, ``polaris-nightly`` or ``coupled``

    omega : str
        Which Omega the build tests: ``develop`` or ``pin`` (Polaris'
        submodule)

    rows : list of str
        The rows that should report each night
    """

    pattern: 're.Pattern[str]'
    source: str
    omega: str
    rows: List[str]


@dataclass
class Build:
    """
    One build on a CDash dashboard

    Attributes
    ----------
    id : int
        CDash's ID for the build

    night : str
        The dashboard's date, ``yyyy-mm-dd``

    site : str
        The machine

    name : str
        The build name

    source : str
        The kind of build, as in :py:class:`BuildKind`

    compiler : str
        The compiler, from the build name

    start : str, optional
        When the build was submitted, as an ISO 8601 time in UTC

    warnings, errors : int, optional
        The counts of compiler warnings and errors

    failed, passed, notrun : int
        The counts of tests
    """

    id: int
    night: str
    site: str
    name: str
    source: str
    compiler: str
    start: Optional[str]
    warnings: Optional[int]
    errors: Optional[int]
    failed: int
    passed: int
    notrun: int

    @property
    def row(self) -> str:
        """``<machine>/<compiler>``"""
        return f'{self.site}/{self.compiler}'

    @property
    def url(self) -> str:
        """The build's page of tests on CDash"""
        return f'{CDASH_URL}/builds/{self.id}/tests'


@dataclass
class FailedTest:
    """
    A test that failed in a build

    Attributes
    ----------
    name : str
        The test's name as it was reported

    details : str, optional
        CDash's short description, such as ``Completed (FAIL)``

    output : str, optional
        The test's output
    """

    name: str
    details: Optional[str]
    output: Optional[str]


class CDash:
    """
    Read a CDash project's nightly results, keeping past nights in a cache

    Parameters
    ----------
    project : str
        The CDash project, such as ``omega``

    cache_dir : str
        Where responses for past nights are kept

    kinds : list of bug_hunt_cdash.BuildKind
        The kinds of build to harvest; others are ignored
    """

    def __init__(
        self, project: str, cache_dir: str, kinds: List[BuildKind]
    ) -> None:
        self.project = project
        self.cache_dir = os.path.join(cache_dir, 'cdash', project)
        self.kinds = kinds

    def builds(self, night: str) -> List[Build]:
        """
        The builds of the kinds being harvested on one night

        Parameters
        ----------
        night : str
            The dashboard's date, ``yyyy-mm-dd``

        Returns
        -------
        builds : list of bug_hunt_cdash.Build
            The builds
        """
        data = self._cached(
            f'index_{night}.json',
            night,
            lambda: _get_json(
                f'{CDASH_URL}/api/v1/index.php?project={self.project}'
                f'&date={night}'
            ),
        )
        builds = []
        for group in data.get('buildgroups', []):
            for entry in group.get('builds', []):
                build = self._to_build(entry, night)
                if build is not None:
                    builds.append(build)
        return builds

    def failed_tests(self, build: Build) -> List[FailedTest]:
        """
        The tests that failed in a build

        Parameters
        ----------
        build : bug_hunt_cdash.Build
            The build

        Returns
        -------
        tests : list of bug_hunt_cdash.FailedTest
            The failed tests, with their output
        """
        if build.failed == 0:
            return []
        edges = self._cached(
            f'failed_{build.id}.json',
            build.night,
            lambda: _query_failed_tests(build.id),
        )
        return [
            FailedTest(
                name=edge['node']['name'],
                details=edge['node'].get('details'),
                output=edge['node'].get('output'),
            )
            for edge in edges
        ]

    def _to_build(self, entry: Dict[str, Any], night: str) -> Optional[Build]:
        name = entry.get('buildname', '')
        for kind in self.kinds:
            match = kind.pattern.fullmatch(name)
            if match is None:
                continue
            start = entry.get('builddatefull')
            if isinstance(start, (int, float)):
                start = (
                    datetime.datetime.fromtimestamp(
                        start, tz=datetime.timezone.utc
                    )
                    .replace(microsecond=0)
                    .isoformat()
                )
            else:
                start = None
            compilation = entry.get('compilation') or {}
            test = entry.get('test') or {}
            return Build(
                id=int(entry['id']),
                night=night,
                site=entry.get('site', 'unknown'),
                name=name,
                source=kind.source,
                compiler=match.group('compiler'),
                start=start,
                warnings=_count(compilation.get('warning')),
                errors=_count(compilation.get('error')),
                failed=_count(test.get('fail')) or 0,
                passed=_count(test.get('pass')) or 0,
                notrun=_count(test.get('notrun')) or 0,
            )
        return None

    def _cached(self, filename, night, fetch):
        """
        Use a cached response for a night that is over; fetch it otherwise

        Results for the last two nights can still change as late builds
        are submitted, so they are always fetched.
        """
        path = os.path.join(self.cache_dir, filename)
        settled = night < _days_ago(2)
        if settled and os.path.exists(path):
            with open(path) as handle:
                return json.load(handle)
        data = fetch()
        if settled:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(path, 'w') as handle:
                json.dump(data, handle)
        return data


def read_kinds(filename: str = SOURCES_FILE) -> Dict[str, Any]:
    """
    Read the description of the CDash builds that are harvested

    Parameters
    ----------
    filename : str, optional
        The YAML file, ``cdash.yaml`` beside this module by default

    Returns
    -------
    sources : dict
        ``project`` and ``kinds``, a list of
        :py:class:`bug_hunt_cdash.BuildKind`
    """
    with open(filename) as handle:
        data = YAML(typ='safe').load(handle)
    cron_rows = read_cron_rows()
    kinds = []
    for entry in data['builds']:
        rows = entry['rows']
        if rows == 'cron':
            rows = cron_rows
        kinds.append(
            BuildKind(
                pattern=re.compile(entry['name']),
                source=entry['source'],
                omega=entry['omega'],
                rows=list(rows),
            )
        )
    return {'project': data['project'], 'kinds': kinds}


def read_cron_rows(directory: str = CRON_MACHINES) -> List[str]:
    """
    The rows the nightly cron jobs are configured to run

    Parameters
    ----------
    directory : str, optional
        The cron jobs' machine configs

    Returns
    -------
    rows : list of str
        ``<machine>/<compiler>`` for each compiler of each machine, sorted
    """
    rows = []
    for filename in glob.glob(os.path.join(directory, '*.cfg')):
        machine = os.path.basename(filename)[: -len('.cfg')]
        parser = configparser.ConfigParser()
        parser.read(filename)
        compilers = parser.get('cron', 'compilers', fallback='')
        for compiler in compilers.replace(',', ' ').split():
            rows.append(f'{machine}/{compiler}')
    return sorted(rows)


def nights_between(first: str, last: str) -> List[str]:
    """
    The dashboard dates from ``first`` to ``last``, inclusive

    Parameters
    ----------
    first, last : str
        Dates as ``yyyy-mm-dd``

    Returns
    -------
    nights : list of str
        The dates, in order
    """
    start = datetime.date.fromisoformat(first)
    end = datetime.date.fromisoformat(last)
    count = (end - start).days + 1
    return [
        (start + datetime.timedelta(days=day)).isoformat()
        for day in range(max(count, 0))
    ]


def shift_night(night: str, days: int) -> str:
    """A date ``days`` after ``night`` (before, if negative)"""
    date = datetime.date.fromisoformat(night)
    return (date + datetime.timedelta(days=days)).isoformat()


def _query_failed_tests(build_id: int) -> List[Dict[str, Any]]:
    """Every failed test of a build, following GraphQL pages"""
    edges: List[Dict[str, Any]] = []
    after = None
    while True:
        data = _post_json(
            f'{CDASH_URL}/graphql',
            {
                'query': _GRAPHQL_TESTS,
                'variables': {'id': str(build_id), 'after': after},
            },
        )
        if data.get('errors'):
            raise CDashError(
                f'CDash GraphQL query for build {build_id} failed: '
                f'{data["errors"]}'
            )
        tests = data['data']['build']['tests']
        edges.extend(tests['edges'])
        if not tests['pageInfo']['hasNextPage']:
            return edges
        after = tests['pageInfo']['endCursor']


def _get_json(url: str) -> Dict[str, Any]:
    return _request(urllib.request.Request(url))


def _post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    return _request(request)


def _request(request: urllib.request.Request) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.URLError as exc:
        raise CDashError(
            f'CDash request {request.full_url} failed: {exc}'
        ) from exc


def _count(value: Any) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _days_ago(days: int) -> str:
    date = datetime.date.today() - datetime.timedelta(days=days)
    return date.isoformat()
