import os
import re
import subprocess

from bug_hunt_cdash import Build, BuildKind, CDash, FailedTest, nights_between
from bug_hunt_harvest import harvest_cdash, harvest_local, merges_between
from bug_hunt_ledger import Key, Ledger
from bug_hunt_sources import LocalFailure

PEM = 'PEM_Vmct.T62_oQU240.COMEGA-IAF'

COMPARE_OUTPUT = (
    'cpl.hi.nc.base did NOT match cpl.hi.nc.modpes\nFAIL\n'
    "compared suffixes suffix1 'base' suffix2 'modpes'\n"
)

KINDS = [
    BuildKind(
        pattern=re.compile(r'e3sm_omega_developer_develop_(?P<compiler>\w+)'),
        source='coupled',
        omega='develop',
        rows=['chrysalis/intel', 'pm-cpu/gnu', 'pm-gpu/gnugpu'],
    ),
    BuildKind(
        pattern=re.compile(r'unitest-develop-(?P<compiler>\w+)'),
        source='ctest',
        omega='develop',
        rows=['chrysalis/gnu'],
    ),
]


class FakeCDash(CDash):
    """
    Ten nights in October: PEM fails on pm-gpu every night and on
    chrysalis/intel from the 7th; pm-cpu never reports; the CTest build's
    warnings rise on the 9th
    """

    def __init__(self, cpu_from='2026-10-07', pm_cpu_from=None):
        self.cpu_from = cpu_from
        self.cpu_until = '2026-12-31'
        self.cpu_again = None
        self.cpu_until_again = None
        self.pm_cpu_from = pm_cpu_from

    def _cpu_fails(self, night):
        if self.cpu_from <= night <= self.cpu_until:
            return True
        if self.cpu_again is None:
            return False
        return self.cpu_again <= night <= self.cpu_until_again

    def builds(self, night):
        if night > '2026-10-10':
            return []
        day = int(night[-2:])
        builds = [
            self._coupled(day, night, 'pm-gpu', 'gnugpu', failed=1),
            self._coupled(
                day,
                night,
                'chrysalis',
                'intel',
                failed=int(self._cpu_fails(night)),
            ),
            Build(
                id=3000 + day,
                night=night,
                site='chrysalis',
                name='unitest-develop-gnu',
                source='ctest',
                compiler='gnu',
                start=f'{night}T05:00:00+00:00',
                warnings=12 if night >= '2026-10-09' else 9,
                errors=0,
                failed=0,
                passed=61,
                notrun=0,
            ),
        ]
        if self.pm_cpu_from is not None and night >= self.pm_cpu_from:
            builds.append(self._coupled(day, night, 'pm-cpu', 'gnu', failed=1))
        return builds

    def failed_tests(self, build):
        if build.failed == 0:
            return []
        name = f'{PEM}.{build.site}_{build.compiler}'
        return [FailedTest(name, 'Completed (FAIL)', COMPARE_OUTPUT)]

    @staticmethod
    def _coupled(day, night, site, compiler, failed):
        return Build(
            id=hash((site, compiler)) % 1000 * 100 + day,
            night=night,
            site=site,
            name=f'e3sm_omega_developer_develop_{compiler}',
            source='coupled',
            compiler=compiler,
            start=f'{night}T06:00:00+00:00',
            warnings=0,
            errors=0,
            failed=failed,
            passed=9 - failed,
            notrun=0,
        )


def _harvest(ledger, cdash=None, first='2026-10-05', last='2026-10-10'):
    return harvest_cdash(
        ledger,
        cdash or FakeCDash(),
        KINDS,
        first,
        last,
        lookback=4,
        day='2026-10-10',
    )


def _by_phase(ledger, phase):
    return [
        finding
        for finding in ledger.findings().values()
        if finding.keys[0].phase == phase
    ]


def test_one_failure_on_two_rows_is_one_finding(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    summary = _harvest(ledger)

    (finding,) = _by_phase(ledger, 'compare')
    assert finding.id in summary.new
    assert finding.keys == [
        Key(PEM, 'compare', 'base and modpes history files did not match')
    ]
    assert finding.rows == ['chrysalis/intel', 'pm-gpu/gnugpu']
    cpu = finding.occurrence(PEM, 'chrysalis/intel')
    assert (cpu.first_failed, cpu.last_passed) == ('2026-10-07', '2026-10-06')
    assert cpu.nights == 4
    gpu = finding.occurrence(PEM, 'pm-gpu/gnugpu')
    assert (gpu.first_failed, gpu.last_passed) == ('2026-10-01', None)
    assert 'did NOT match' in finding.evidence


def test_rows_with_no_results_and_warnings_that_rose(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger)

    (missing,) = _by_phase(ledger, 'missing')
    assert missing.keys == [
        Key('coupled nightly', 'missing', rows=['pm-cpu/gnu'])
    ]
    assert missing.claim == 'The coupled nightly has no results'
    assert missing.occurrences[0].first_failed == '2026-10-05'
    assert missing.rows == ['pm-cpu/gnu']
    assert missing.owner == 'unknown'

    (warnings,) = _by_phase(ledger, 'warnings')
    occurrence = warnings.occurrences[0]
    assert occurrence.row == 'chrysalis/gnu'
    assert (occurrence.first_failed, occurrence.last_passed) == (
        '2026-10-09',
        '2026-10-08',
    )
    assert warnings.evidence == ('9 warnings on 2026-10-05, 12 on 2026-10-10')


def test_harvesting_again_adds_nothing_new(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger)
    before = sorted(ledger.findings())
    summary = _harvest(ledger)

    assert summary.new == []
    assert sorted(ledger.findings()) == before
    assert ledger.covered('cdash') == '2026-10-10'


def test_a_row_split_off_keeps_its_failures(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger)
    (finding,) = _by_phase(ledger, 'compare')

    # what "bug_hunt.py update <id> --split pm-gpu/gnugpu" does
    split_keys = [
        Key(key.test, key.phase, key.message, rows=['pm-gpu/gnugpu'])
        for key in finding.keys
    ]
    split = finding.__class__(
        id='F-gpu', keys=split_keys, created='2026-10-10', source='coupled'
    )
    split.occurrences = [
        item for item in finding.occurrences if item.row == 'pm-gpu/gnugpu'
    ]
    finding.occurrences = [
        item for item in finding.occurrences if item.row != 'pm-gpu/gnugpu'
    ]
    ledger.save(finding)
    ledger.save(split)

    summary = _harvest(ledger)
    findings = ledger.findings()
    assert summary.new == []
    assert findings['F-gpu'].rows == ['pm-gpu/gnugpu']
    assert findings[finding.id].rows == ['chrysalis/intel']


def test_a_tracked_finding_is_raised_again_on_a_new_row(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger)
    (finding,) = _by_phase(ledger, 'compare')
    finding.status = 'tracked'
    finding.links = ['E3SM-Project/Omega#626']
    ledger.save(finding)

    summary = _harvest(ledger, FakeCDash(pm_cpu_from='2026-10-09'))
    changed = ledger.get(finding.id)
    assert summary.changed == [finding.id]
    assert changed.changed == 'now fails on pm-cpu/gnu too'


def test_a_finding_that_was_not_decided_on_is_not_raised_again(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger)
    summary = _harvest(ledger, FakeCDash(pm_cpu_from='2026-10-09'))
    (finding,) = _by_phase(ledger, 'compare')

    assert summary.changed == []
    assert finding.changed is None
    assert 'pm-cpu/gnu' in finding.rows


def test_local_failures(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    failure = LocalFailure(
        test='ocean/planar/overflow/nonlinear/pstar/smoke_test_order_3',
        phase='run',
        message='StateValidation: PseudoThickness contains 12566 NaN values',
        row='chrysalis/intel',
        source='polaris',
        night='2026-10-24',
        where='/scratch/run/case_outputs/overflow.log',
    )
    summary = harvest_local(ledger, [failure], day='2026-10-27')

    (finding,) = ledger.findings().values()
    assert summary.new == [finding.id]
    # a task's first error line differs by machine for the same cause, so
    # it is evidence rather than part of the key
    assert finding.keys[0].message is None
    assert finding.occurrences[0].url == failure.where


def test_merges_between(tmp_path):
    repo = tmp_path / 'omega'
    _git(repo.parent, 'init', '-q', 'omega')
    _commit(repo, 'Start', '2026-10-01T00:00:00')
    merges = ((512, '2026-10-06T12:00:00'), (603, '2026-10-08T12:00:00'))
    for number, date in merges:
        _git(repo, 'checkout', '-q', '-b', f'pr{number}')
        _commit(repo, f'Change for #{number}', date)
        _git(repo, 'checkout', '-q', 'main')
        _git(
            repo,
            'merge',
            '-q',
            '--no-ff',
            f'pr{number}',
            '-m',
            f'Merge pull request #{number} from someone/branch',
            env_date=date,
        )
    _git(repo, 'update-ref', 'refs/remotes/origin/develop', 'HEAD')

    assert merges_between(
        str(repo), '2026-10-06T00:00:00', '2026-10-07T00:00:00'
    ) == ['E3SM-Project/Omega#512']
    assert merges_between(str(repo), '2026-10-05', '2026-10-09') == [
        'E3SM-Project/Omega#512',
        'E3SM-Project/Omega#603',
    ]
    assert merges_between(str(repo), None, '2026-10-09') == []


def test_failures_that_ended_are_not_recorded(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    # chrysalis/intel fails only on the 7th and 8th, then passes again
    cdash = FakeCDash()
    cdash.cpu_until = '2026-10-08'
    summary = _harvest(ledger, cdash)

    (finding,) = _by_phase(ledger, 'compare')
    assert finding.rows == ['pm-gpu/gnugpu']
    assert summary.ended == 1


def test_failures_that_come_and_go_are_recorded(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    cdash = FakeCDash(cpu_from='2026-10-03')
    cdash.cpu_until = '2026-10-04'
    cdash.cpu_again = '2026-10-07'
    cdash.cpu_until_again = '2026-10-08'
    _harvest(ledger, cdash)

    (finding,) = _by_phase(ledger, 'compare')
    occurrence = finding.occurrence(PEM, 'chrysalis/intel')
    assert occurrence.intermittent
    assert (occurrence.first_failed, occurrence.last_failed) == (
        '2026-10-07',
        '2026-10-08',
    )


def test_nights_between():
    assert nights_between('2026-09-30', '2026-10-02') == [
        '2026-09-30',
        '2026-10-01',
        '2026-10-02',
    ]


def _commit(repo, message, date):
    _git(repo, 'commit', '-q', '--allow-empty', '-m', message, env_date=date)


def _git(path, *args, env_date=None):
    env = dict(os.environ)
    if env_date is not None:
        env['GIT_AUTHOR_DATE'] = env_date
        env['GIT_COMMITTER_DATE'] = env_date
    subprocess.run(['git', '-C', str(path)] + list(args), check=True, env=env)


def test_the_harvest_sets_the_priority_as_rows_change(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger, FakeCDash(cpu_from='2026-12-01'))
    (finding,) = _by_phase(ledger, 'compare')
    assert finding.rows == ['pm-gpu/gnugpu']
    finding.severity = 'S2'
    finding.confidence = 'measured'
    finding.priority = 'P2'
    ledger.save(finding)

    _harvest(ledger)
    finding = ledger.get(finding.id)
    assert finding.rows == ['chrysalis/intel', 'pm-gpu/gnugpu']
    assert finding.priority == 'P1'


def test_a_fixed_bug_that_fails_again_moves_up(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger, FakeCDash(cpu_from='2026-12-01'))
    (finding,) = _by_phase(ledger, 'compare')
    finding.severity = 'S3'
    finding.confidence = 'measured'
    finding.priority = 'P3'
    finding.status = 'fixed'
    for occurrence in finding.occurrences:
        occurrence.last_failed = '2026-10-05'
    ledger.save(finding)

    _harvest(ledger, FakeCDash(cpu_from='2026-12-01'))
    finding = ledger.get(finding.id)
    assert finding.changed == 'fails again after it was fixed'
    assert finding.came_back
    assert finding.priority == 'P2'


def _hold(ledger, since):
    reason = 'out of compute hours'
    ledger.save_holds({'pm-cpu/gnu': {'reason': reason, 'since': since}})


def test_a_row_on_hold_is_not_reported_as_stopped(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _hold(ledger, '2026-10-01')

    summary = _harvest(ledger)
    assert summary.released == []
    assert [finding.rows for finding in _by_phase(ledger, 'missing')] == []
    assert list(ledger.holds()) == ['pm-cpu/gnu']


def test_a_row_on_hold_that_reports_again_is_released(ledger_dir):
    ledger = Ledger(str(ledger_dir))
    _hold(ledger, '2026-10-08')

    summary = _harvest(ledger, FakeCDash(pm_cpu_from='2026-10-09'))
    assert summary.released == ['pm-cpu/gnu']
    assert ledger.holds() == {}
    # its failures are harvested as on any other row
    (finding,) = _by_phase(ledger, 'compare')
    assert 'pm-cpu/gnu' in finding.rows


def test_a_build_on_the_day_of_the_hold_does_not_release_it(ledger_dir):
    # a hold set on the day the row last reported, as Frontier's would be
    ledger = Ledger(str(ledger_dir))
    _hold(ledger, '2026-10-10')

    summary = _harvest(ledger, FakeCDash(pm_cpu_from='2026-10-09'))
    assert summary.released == []
    assert list(ledger.holds()) == ['pm-cpu/gnu']


def test_each_row_that_stops_reporting_is_its_own_finding(
    ledger_dir, monkeypatch
):
    ledger = Ledger(str(ledger_dir))
    _harvest(ledger)
    (pm_cpu,) = _by_phase(ledger, 'missing')

    # pm-gpu stops too: rows stop for different reasons
    cdash = FakeCDash()
    builds = cdash.builds
    monkeypatch.setattr(
        cdash,
        'builds',
        lambda night: [
            build for build in builds(night) if build.site != 'pm-gpu'
        ],
    )
    summary = _harvest(ledger, cdash)

    missing = _by_phase(ledger, 'missing')
    assert sorted(finding.rows for finding in missing) == [
        ['pm-cpu/gnu'],
        ['pm-gpu/gnugpu'],
    ]
    assert pm_cpu.id not in summary.new


def test_a_row_that_reported_the_night_before_a_short_window_is_fine(
    ledger_dir, monkeypatch
):
    ledger = Ledger(str(ledger_dir))
    cdash = FakeCDash(pm_cpu_from='2026-10-01')
    builds = cdash.builds
    # chrysalis/intel has not reported yet on the last night
    monkeypatch.setattr(
        cdash,
        'builds',
        lambda night: [
            build
            for build in builds(night)
            if not (night == '2026-10-10' and build.site == 'chrysalis')
        ],
    )
    _harvest(ledger, cdash, first='2026-10-10', last='2026-10-10')

    assert _by_phase(ledger, 'missing') == []
