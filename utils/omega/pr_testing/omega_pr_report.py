"""
The tester's Testing comment for a machine: a line for each of its rows,
generated from the results, and below it the files Polaris, CTest and CIME
wrote, pasted unchanged, with any new build warnings
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import omega_pr_coupled as coupled
import pr_test_git as git_tools
import pr_test_report as report
from omega_pr_manifest import (
    MARKER_PREFIX,
    POLARIS_SUBMODULE,
    UPSTREAM,
    Manifest,
    fetch_manifest,
)
from omega_pr_setup import SUITE, get_row_dir, get_run_dir
from pr_test_config import PrTestConfig
from pr_test_report import ReportError, RowResult
from pr_test_rows import Row, get_machine_rows
from pr_test_setup import Job, SetupError, get_system, read_state
from pr_test_warnings import format_warnings_section

from polaris.machines import discover_machine

#: the table's columns after each row's label
COLUMNS = ['CTests', f'`{SUITE}`', 'Coupled', 'New build warnings']


def run_report(
    config: PrTestConfig,
    fork: str,
    branch: str,
    machine: Optional[str] = None,
    not_run: Optional[str] = None,
    notes: Optional[str] = None,
    agent: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Write the Testing comment for a machine's rows, for someone to read
    before it is posted

    The rows are the manifest's rows on the machine and on any machine that
    shares its login nodes, so Perlmutter's pm-cpu and pm-gpu rows share a
    comment.

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    fork : str
        The URL of the requester's fork

    branch : str
        The test branch

    machine : str, optional
        The machine, that of the loaded Polaris environment, or else the
        one this is run on, by default

    not_run : str, optional
        Why the rows without results could not be run, which reports them
        as not run.  Without it, every row must have results.

    notes : str, optional
        Notes to add to the comment

    agent : str, optional
        The agent posting the comment, which adds the signature

    Returns
    -------
    text : str
        The comment

    path : str
        The file the comment was written to
    """
    manifest = fetch_manifest(config.omega_repo, fork, branch)
    if machine is None:
        machine = os.environ.get('POLARIS_MACHINE') or discover_machine(
            quiet=True
        )
    if machine is None:
        raise ReportError(
            'This is not a Polaris machine and no Polaris environment is '
            'loaded.  Pass --machine.'
        )
    rows = get_machine_rows(manifest.rows, machine)
    if not rows:
        names = ', '.join(row.name for row in manifest.rows)
        raise ReportError(
            f'The manifest has no rows for {machine}; its rows are {names}.'
        )
    machines = list(dict.fromkeys(row.machine for row in rows))

    changed = git_tools.git(
        ['diff', '--name-only', f'{manifest.base_head}...{manifest.pr_head}'],
        config.omega_repo,
    ).splitlines()
    results = []
    missing = []
    for row in rows:
        try:
            results.append(_row_result(config, manifest, row, changed))
        except ReportError as exc:
            if not_run is None:
                missing.append(f'  {row.name}: {exc}')
            else:
                results.append(report.not_run(row, not_run, COLUMNS))
    if missing:
        raise ReportError(
            'These rows have no results to report:\n'
            + '\n'.join(missing)
            + '\nReport once their jobs are done, or pass --not-run with the '
            'reason if they cannot be run.'
        )

    text = report.assemble(
        heading=f'Testing on {" and ".join(machines)}',
        marker=make_marker(manifest, report.get_marker_entries(results)),
        sections=[describe_commits(manifest)]
        + report.format_rows(COLUMNS, results),
        requester=manifest.requester,
        requester_notes=manifest.notes,
        notes=notes,
        agent=agent,
    )
    path = os.path.join(
        get_run_dir(config, manifest), f'report_{"_".join(machines)}.md'
    )
    report.write_comment(text, path)
    return text, path


def make_marker(manifest: Manifest, rows: List[Dict[str, Any]]) -> str:
    """
    The hidden marker for a Testing comment on rows of a manifest

    Parameters
    ----------
    manifest : omega_pr_manifest.Manifest
        The manifest that was tested

    rows : list of dict
        Each row's ``row``, ``status`` and ``result``

    Returns
    -------
    marker : str
        An HTML comment holding the marker as JSON
    """
    return report.make_marker(
        MARKER_PREFIX,
        pr=manifest.pull_request,
        pr_head=manifest.pr_head,
        test=manifest.test_commit,
        baseline=manifest.baseline_commit,
        rows=rows,
    )


def describe_commits(manifest: Manifest) -> str:
    """What was tested against what, in a sentence or two"""
    merged = (
        f'the merge of {UPSTREAM}#{manifest.pull_request} '
        f'(`{manifest.pr_head[:10]}`) into `{manifest.base_branch}` '
        f'(`{manifest.base_head[:10]}`)'
    )
    extras = [
        f'#{merge.pull_request}'
        for merge in manifest.extra_merges
        if 'test' in merge.sides
    ]
    if extras:
        merged = f'{merged}, with {", ".join(extras)} merged in,'
    if manifest.baseline_source == POLARIS_SUBMODULE:
        baseline = (
            f"Polaris' Omega submodule (`{manifest.baseline_commit[:10]}`)"
        )
    else:
        baseline = (
            f'`{manifest.baseline_source}` '
            f'(`{manifest.baseline_commit[:10]}`) rather than the Polaris '
            f'submodule, because {manifest.baseline_reason}'
        )
    baseline_extras = [
        f'#{merge.pull_request}'
        for merge in manifest.extra_merges
        if 'baseline' in merge.sides
    ]
    if baseline_extras:
        baseline = f'{baseline}, with {", ".join(baseline_extras)} merged in'
    text = (
        f'Tested {merged} as `{manifest.test_commit[:10]}`, against '
        f'{baseline}.'
    )
    if manifest.baseline_polaris_commit != manifest.polaris_commit:
        text = (
            f'{text} The baseline ran with Polaris '
            f'`{manifest.baseline_polaris_commit[:10]}`, without the changes '
            f'in Polaris `{manifest.polaris_commit[:10]}` that the PR needs.'
        )
    return text


def _row_result(config, manifest, row: Row, changed) -> RowResult:
    """A row's line and the files its jobs wrote"""
    row_dir = get_row_dir(config, manifest, row)
    try:
        state = read_state(row_dir)
    except SetupError as exc:
        raise ReportError(str(exc)) from exc
    pr_md = report.read_required(
        os.path.join(state.pr_work_dir, f'{SUITE}_output_for_pr.md'),
        'the PR suite has not finished',
    )
    ctest_md = report.read_required(
        os.path.join(state.pr_build_dir, 'ctest_output_for_pr.md'),
        'the CTests have not finished',
    )
    suite_passed, suite_cell = report.summarize_suite(
        state.pr_work_dir, SUITE, state.baseline_work_dir
    )
    ctest_passed, ctest_cell = report.summarize_ctests(state.pr_build_dir)
    if state.coupled_cases:
        coupled_passed, coupled_cell, coupled_text = (
            coupled.summarize_coupled_tests(
                state.coupled_cases,
                [Job(**job) for job in state.jobs],
                get_system(row.machine),
                coupled.get_cime_env_script(row.machine),
            )
        )
    else:
        # set up before the utility ran coupled tests
        coupled_passed, coupled_cell, coupled_text = True, 'not run', ''

    if state.no_baseline_reason is None:
        baseline_build = None
        if state.baseline_build_log is not None:
            baseline_build = os.path.dirname(state.baseline_build_log)
        warnings_text, new_warnings = format_warnings_section(
            baseline_build, state.pr_build_dir, changed
        )
        warnings_cell = (
            'not compared' if new_warnings is None else str(new_warnings)
        )
    else:
        suite_cell = f'{suite_cell}, without a baseline'
        warnings_text = (
            f'### Build warnings\n\nNot compared: this row ran without a '
            f'baseline, because {state.no_baseline_reason}.'
        )
        new_warnings = None
        warnings_cell = 'not compared'

    marker: Dict[str, Any] = {'new_warnings': new_warnings}
    if state.no_baseline_reason is not None:
        marker['no_baseline'] = state.no_baseline_reason
    return RowResult(
        row=row,
        status='complete',
        result='pass'
        if suite_passed and ctest_passed and coupled_passed
        else 'fail',
        cells=[ctest_cell, suite_cell, coupled_cell, warnings_cell],
        details='\n\n'.join(
            text.strip()
            for text in [pr_md, ctest_md, coupled_text, warnings_text]
            if text
        ),
        marker=marker,
    )
