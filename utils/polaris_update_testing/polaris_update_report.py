"""
The tester's Testing comment for a machine's rows with one kind of Spack
environment: a line for each row, generated from the results, and below it
the files Polaris and CTest wrote, pasted unchanged
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import pr_test_git as git_tools
import pr_test_report as report
from polaris_update_deploy import SPACK_VIEW_VARIABLE, get_spack_kind
from polaris_update_manifest import (
    MARKER_PREFIX,
    UPSTREAM,
    Manifest,
    fetch_manifest,
)
from polaris_update_setup import get_row_dir, get_run_dir
from pr_test_config import PrTestConfig
from pr_test_git import POLARIS_DIR
from pr_test_report import ReportError, RowResult
from pr_test_rows import Row, get_machine_rows
from pr_test_setup import SetupError, SetupState, read_state
from pr_test_warnings import format_warnings_section

from polaris.machines import discover_machine

#: the table's columns after each row's label
COLUMNS = ['Suite', 'CTests', 'New build warnings']

#: the kinds of Spack environment a report can be for
SPACK_KINDS = ['shared', 'test']


def run_report(
    config: PrTestConfig,
    fork: str,
    branch: str,
    machine: Optional[str] = None,
    spack: Optional[str] = None,
    not_run: Optional[str] = None,
    notes: Optional[str] = None,
    agent: Optional[str] = None,
    polaris_dir: str = POLARIS_DIR,
) -> Tuple[str, str]:
    """
    Write the Testing comment for a machine's rows, for someone to read
    before it is posted,
    with one kind of Spack environment

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    fork : str
        The URL of the requester's Polaris fork

    branch : str
        The test branch

    machine : str, optional
        The machine, that of the loaded Polaris environment, or else the
        one this is run on, by default.  Pm-cpu and pm-gpu share a comment.

    spack : {'shared', 'test'}, optional
        The kind of Spack environment, that of the loaded load script by
        default

    not_run : str, optional
        Why the rows without results could not be run, which reports them
        as not run.  Without it, every row must have results.

    notes : str, optional
        Notes to add to the comment

    agent : str, optional
        The agent posting the comment, which adds the signature

    polaris_dir : str, optional
        The Polaris checkout to fetch the test branch into

    Returns
    -------
    text : str
        The comment

    path : str
        The file the comment was written to
    """
    manifest = fetch_manifest(polaris_dir, fork, branch)
    if machine is None:
        machine = os.environ.get('POLARIS_MACHINE') or discover_machine(
            quiet=True
        )
    if machine is None:
        raise ReportError(
            'This is not a Polaris machine and no Polaris environment is '
            'loaded.  Pass --machine.'
        )
    if spack is None:
        spack = _get_loaded_kind(polaris_dir, machine)
    rows = get_machine_rows(manifest.rows, machine)
    if not rows:
        raise ReportError(f'The manifest has no rows for {machine}.')
    machines = list(dict.fromkeys(row.machine for row in rows))
    run_dir = get_run_dir(config, manifest, spack)

    changed = _get_changed_omega_files(config, manifest)
    results = []
    states = []
    comparisons = []
    missing = []
    for row in rows:
        try:
            result, state = _row_result(manifest, row, run_dir, changed)
        except ReportError as exc:
            if not_run is None:
                missing.append(f'  {row.name}: {exc}')
            else:
                results.append(report.not_run(row, not_run, COLUMNS))
                comparisons.append((row, None, f'it was not run: {not_run}'))
            continue
        results.append(result)
        states.append(state)
        comparisons.append(_compare(manifest, row, state, result))
    if missing:
        raise ReportError(
            'These rows have no results to report:\n'
            + '\n'.join(missing)
            + '\nReport once their jobs are done, or pass --not-run with the '
            'reason if they cannot be run.'
        )

    marker = report.make_marker(
        MARKER_PREFIX,
        pr=manifest.pull_request,
        pr_head=manifest.pr_head,
        spack=spack,
        rows=report.get_marker_entries(results),
    )
    text = report.assemble(
        heading=f'Testing on {" and ".join(machines)} with the {spack} '
        f'Spack environments',
        marker=marker,
        sections=[
            describe(manifest, spack, states),
            report.format_bit_for_bit(comparisons),
        ]
        + report.format_rows(COLUMNS, results),
        requester=manifest.requester,
        requester_notes=manifest.notes,
        notes=notes,
        agent=agent,
    )
    path = os.path.join(run_dir, f'report_{"_".join(machines)}.md')
    report.write_comment(text, path)
    return text, path


def describe(manifest: Manifest, spack: str, states: List[SetupState]) -> str:
    """What was tested with what, against what, in a few sentences"""
    test = manifest.test
    environment: Dict[str, str] = states[0].environment if states else {}
    mache = environment.get('mache_version')
    with_mache = f' with mache {mache}' if mache else ''
    paths = sorted(
        {
            state.environment['spack_path']
            for state in states
            if 'spack_path' in state.environment
        }
    )
    where = ''
    if paths:
        where = f' in {", ".join(f"`{path}`" for path in paths)}'
    omega = f'Omega `{test.omega_commit[:10]}`'
    if manifest.omega_merge is not None:
        merged = ', '.join(
            f'E3SM-Project/Omega#{number}'
            for number in manifest.omega_merge.pull_requests
        )
        omega = (
            f'{omega} with {merged} merged in '
            f'(`{manifest.omega_merge.commit[:10]}`)'
        )
    text = (
        f'Tested {UPSTREAM}#{manifest.pull_request} '
        f'(`{test.polaris_commit[:10]}`), Polaris {test.polaris_version}'
        f'{with_mache}, {omega} and E3SM `{test.e3sm_commit[:10]}`, with the '
        f'{spack} Spack environments{where}.'
    )
    baseline = manifest.baseline
    if baseline is None:
        return f'{text} There is no baseline.'
    return (
        f'{text} The baseline is `{baseline.polaris_commit[:10]}`, Polaris '
        f'{baseline.polaris_version}, Omega `{baseline.omega_commit[:10]}` '
        f'and E3SM `{baseline.e3sm_commit[:10]}`, with its shared Spack '
        f'environments, so differences can come from any of these.'
    )


def _row_result(
    manifest: Manifest, row: Row, run_dir: str, changed: List[str]
) -> Tuple[RowResult, SetupState]:
    """A row's line and the files its jobs wrote"""
    try:
        state = read_state(get_row_dir(run_dir, row))
    except SetupError as exc:
        raise ReportError(str(exc)) from exc
    suite_md = report.read_required(
        os.path.join(state.pr_work_dir, f'{state.suite}_output_for_pr.md'),
        'the PR suite has not finished',
    )
    passed, suite_cell = report.summarize_suite(state.pr_work_dir, state.suite)
    suite_cell = f'`{state.suite}`: {suite_cell}'
    sections = [suite_md]
    ctest_cell = ''
    warnings_cell = ''
    marker: Dict[str, Any] = {}
    if state.ctest_dir is not None:
        sections.append(
            report.read_required(
                os.path.join(state.pr_build_dir, 'ctest_output_for_pr.md'),
                'the CTests have not finished',
            )
        )
        ctest_passed, ctest_cell = report.summarize_ctests(state.pr_build_dir)
        passed = passed and ctest_passed
        if state.baseline_work_dir is not None:
            baseline_build = None
            if state.baseline_build_log is not None:
                baseline_build = os.path.dirname(state.baseline_build_log)
            warnings_text, new_warnings = format_warnings_section(
                baseline_build, state.pr_build_dir, changed
            )
            sections.append(warnings_text)
            marker['new_warnings'] = new_warnings
            warnings_cell = (
                'not compared' if new_warnings is None else str(new_warnings)
            )
        else:
            warnings_cell = 'not compared'
    if state.no_baseline_reason is not None:
        suite_cell = f'{suite_cell}, without a baseline'
        sections.append(
            f'Without the baseline, because {state.no_baseline_reason}.'
        )
        marker['no_baseline'] = state.no_baseline_reason
    result = RowResult(
        row=row,
        status='complete',
        result='pass' if passed else 'fail',
        cells=[suite_cell, ctest_cell, warnings_cell],
        details='\n\n'.join(section.strip() for section in sections),
        marker=marker,
    )
    return result, state


def _compare(manifest, row, state, result):
    """
    A row's comparison with the baseline, recorded in its marker, or why
    there is none
    """
    if state.baseline_work_dir is None:
        if state.no_baseline_reason is not None:
            reason = state.no_baseline_reason
        else:
            reason = 'there is no baseline'
        return row, None, reason
    comparison = report.compare_with_baseline(state.pr_work_dir, state.suite)
    result.marker['non_bfb'] = len(comparison.differ)
    result.marker['did_not_run'] = len(comparison.did_not_run)
    return row, comparison, ''


def _get_loaded_kind(polaris_dir, machine):
    """The kind of Spack environment the loaded load script uses"""
    view = os.environ.get(SPACK_VIEW_VARIABLE, '').strip()
    if not view:
        raise ReportError(
            'No load script with a Spack environment is loaded.  Pass '
            '--spack shared or --spack test.'
        )
    return get_spack_kind(polaris_dir, machine, view)


def _get_changed_omega_files(config, manifest):
    """
    The Omega files that differ between the baseline and the PR, whose
    new warnings are marked
    """
    if manifest.baseline is None:
        return []
    baseline = manifest.baseline.omega_commit
    test = manifest.omega_build_commit
    if baseline == test:
        return []
    try:
        return git_tools.git(
            ['diff', '--name-only', f'{baseline}...{test}'],
            config.omega_repo,
        ).splitlines()
    except git_tools.GitError:
        return []
