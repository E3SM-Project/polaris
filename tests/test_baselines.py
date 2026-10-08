import json

import pytest

from polaris.baselines import (
    BaselineCriteria,
    check_baseline,
    find_baseline,
    find_build_log,
)

POLARIS_HASH = 'a' * 40
OMEGA_HASH = 'c' * 40

CRITERIA = BaselineCriteria(
    machine='chrysalis',
    compiler='intel',
    build_type='Release',
    component_hash=OMEGA_HASH,
    polaris_hash=POLARIS_HASH,
)


def test_find_baseline_match(tmp_path):
    work_dir = _make_run(tmp_path / 'test_20260929' / 'baseline')

    matches, near_misses = find_baseline([str(tmp_path)], CRITERIA)

    assert matches == [str(work_dir)]
    assert near_misses == []


@pytest.mark.parametrize(
    'changes, reason',
    [
        ({'machine': 'pm-cpu'}, 'its machine is pm-cpu, not chrysalis'),
        ({'compiler': 'gnu'}, 'its compiler is gnu, not intel'),
        ({'build type': 'Debug'}, 'its build type is Debug, not Release'),
        (
            {'component_hash': 'e' * 40},
            f'its component commit is {"e" * 12}, not {"c" * 12}',
        ),
        (
            {'polaris_hash': 'b' * 40},
            f'its Polaris commit is {"b" * 12}, not {"a" * 12}',
        ),
        (
            {'at_setup': True},
            'its component commit was recorded at setup, not when it was '
            'built',
        ),
        (
            {'polaris_describe': '1.0.0-801-gaaaaaaaaa-dirty'},
            'its Polaris tree had uncommitted changes',
        ),
        (
            {'command': 'polaris suite -c ocean -t omega_nightly'},
            'it was set up as suite omega_nightly, not omega_pr',
        ),
        (
            {'command': 'polaris suite -c ocean -t omega_pr -f my.cfg'},
            'it was set up with config file my.cfg',
        ),
        (
            {'command': 'polaris setup -n 1 2 --suite_name omega_pr'},
            'it was not set up with "polaris suite"',
        ),
        (
            {'command': "polaris suite -t omega_pr --cmake_flags='-DX=1'"},
            'it was set up with --cmake_flags',
        ),
        ({'complete': False}, 'its run is not complete'),
        ({'failed': 2}, '2 of its tasks failed'),
        ({'results': False}, 'it has no readable omega_pr_results.json'),
    ],
)
def test_find_baseline_near_miss(tmp_path, changes, reason):
    work_dir = _make_run(tmp_path / 'run', **changes)

    matches, near_misses = find_baseline([str(tmp_path)], CRITERIA)

    assert matches == []
    assert len(near_misses) == 1
    assert near_misses[0].path == str(work_dir)
    assert near_misses[0].reasons == [reason]


def test_find_baseline_search_depth(tmp_path):
    shallow = _make_run(tmp_path / 'a' / 'b' / 'c')
    _make_run(tmp_path / 'a' / 'b' / 'c' / 'd' / 'nested')
    _make_run(tmp_path / 'e' / 'f' / 'g' / 'h')

    matches, _ = find_baseline([str(tmp_path)], CRITERIA)

    # nothing inside a run, and nothing more than 3 levels below the root
    assert matches == [str(shallow)]


def test_near_misses_are_sorted(tmp_path):
    one = _make_run(tmp_path / 'one', compiler='gnu')
    _make_run(tmp_path / 'two', compiler='gnu', machine='pm-cpu')

    _, near_misses = find_baseline([str(tmp_path)], CRITERIA)

    assert near_misses[0].path == str(one)
    assert len(near_misses[1].reasons) == 2


def test_check_baseline_without_provenance(tmp_path):
    assert check_baseline(str(tmp_path), CRITERIA) == [
        'it has no provenance file'
    ]


def test_find_build_log_from_run(tmp_path):
    # the build is outside the search root, and found from the run
    build_dir = _make_build(tmp_path / 'builds' / 'omega')
    _make_run(tmp_path / 'runs' / 'baseline', build_dir=build_dir)

    logs, near_misses = find_build_log([str(tmp_path / 'runs')], CRITERIA)

    assert logs == [str(build_dir / 'build_omega.log')]
    assert near_misses == []


@pytest.mark.parametrize(
    'changes, reason',
    [
        (
            {'clean_build': False},
            'it was not built from an empty build directory',
        ),
        ({'exe': False}, 'it has no omega.exe, so the build did not finish'),
        ({'compiler': 'gnu'}, 'its compiler is gnu, not intel'),
        (
            {'component_hash': 'e' * 40},
            f'its component commit is {"e" * 12}, not {"c" * 12}',
        ),
    ],
)
def test_find_build_log_near_miss(tmp_path, changes, reason):
    build_dir = _make_build(tmp_path / 'build', **changes)

    logs, near_misses = find_build_log([str(tmp_path)], CRITERIA)

    assert logs == []
    assert near_misses[0].path == str(build_dir)
    assert near_misses[0].reasons == [reason]


def _make_run(
    work_dir,
    machine='chrysalis',
    compiler='intel',
    component_hash=OMEGA_HASH,
    polaris_hash=POLARIS_HASH,
    polaris_describe='1.0.0-801-gaaaaaaaaa',
    at_setup=False,
    command='polaris suite -c ocean -t omega_pr --model omega',
    complete=True,
    failed=0,
    results=True,
    build_dir=None,
    **kwargs,
):
    work_dir.mkdir(parents=True)
    build_type = kwargs.get('build type', 'Release')
    if build_dir is None:
        build_dir = work_dir / 'build'
    marker = ' (at setup, not build)' if at_setup else ''
    lines = [
        f'polaris git version: {polaris_describe}',
        f'polaris git hash: {polaris_hash}',
        f'component git version: Omega-v0.1.0-5500-gccccccccc{marker}',
        f'component git hash: {component_hash}{marker}',
        f'command: {command} -w {work_dir} -p {build_dir}',
        f'machine: {machine}',
        f'compiler: {compiler}',
        f'build directory: {build_dir}',
        f'build type: {build_type}',
        'tasks:',
    ]
    (work_dir / 'provenance').write_text(
        '\n\n'.join(lines) + '\n', encoding='utf-8'
    )
    (work_dir / 'omega_pr.pickle').write_bytes(b'')
    if results:
        contents = {
            'suite': 'omega_pr',
            'complete': complete,
            'summary': {'total': 3, 'passed': 3 - failed, 'failed': failed},
        }
        (work_dir / 'omega_pr_results.json').write_text(
            json.dumps(contents), encoding='utf-8'
        )
    return work_dir


def _make_build(
    build_dir,
    compiler='intel',
    component_hash=OMEGA_HASH,
    clean_build=True,
    exe=True,
):
    (build_dir / 'src').mkdir(parents=True)
    (build_dir / 'omega_build.sh').write_text('', encoding='utf-8')
    if exe:
        (build_dir / 'src' / 'omega.exe').write_bytes(b'')
    (build_dir / 'build_omega.log').write_text('', encoding='utf-8')
    (build_dir / 'CMakeCache.txt').write_text(
        'OMEGA_BUILD_TYPE:UNINITIALIZED=Release\n'
        f'OMEGA_CIME_COMPILER:UNINITIALIZED={compiler}\n'
        'OMEGA_CIME_MACHINE:UNINITIALIZED=chrysalis\n',
        encoding='utf-8',
    )
    (build_dir / 'omega_source.txt').write_text(
        'source: /path/to/omega\n'
        f'hash: {component_hash}\n'
        'describe: Omega-v0.1.0-5500-gccccccccc\n'
        f'clean_build: {"true" if clean_build else "false"}\n'
        'log:\n'
        '  ccccccccc Merge pull request #1 from someone/branch\n',
        encoding='utf-8',
    )
    return build_dir
