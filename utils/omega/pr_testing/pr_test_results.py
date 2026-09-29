"""
The tester's Testing comment for a row: the files Polaris and CTest wrote,
pasted unchanged, with a generated summary, the commits and new build
warnings
"""

import json
import os
import re
from typing import List, Optional, Tuple

import pr_test_git as git_tools
import pr_test_report as report
from pr_test_config import PrTestConfig
from pr_test_manifest import (
    POLARIS_SUBMODULE,
    UPSTREAM,
    Manifest,
    fetch_manifest,
    get_row,
)
from pr_test_setup import SUITE, get_env_row, get_row_dir, read_state
from pr_test_warnings import format_warnings_section

_CTEST_COUNTS = re.compile(
    r'(\d+)% tests passed, (\d+) tests failed out of (\d+)'
)


class ReportError(Exception):
    """The row's results are not ready to report"""


def run_report(
    config: PrTestConfig,
    fork: str,
    branch: str,
    row_name: Optional[str] = None,
    not_run: Optional[str] = None,
    notes: Optional[str] = None,
    agent: Optional[str] = None,
    post: bool = False,
) -> Tuple[str, Optional[str], str]:
    """
    Write, and optionally post, the Testing comment for a row

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The per-machine settings

    fork : str
        The URL of the requester's fork

    branch : str
        The test branch

    row_name : str, optional
        ``<machine>/<compiler>``, the loaded Polaris environment's row by
        default

    not_run : str, optional
        Why the row could not be run, which reports it as not run

    notes : str, optional
        Notes to add to the comment

    agent : str, optional
        The agent posting the comment, which adds the signature

    post : bool, optional
        Whether to post the comment

    Returns
    -------
    text : str
        The comment

    url : str, optional
        The URL of the posted comment

    path : str
        The file the comment was written to
    """
    manifest = fetch_manifest(config.omega_repo, fork, branch)
    if row_name is None:
        row = get_env_row(manifest)
    else:
        row = get_row(row_name)
        row = manifest.get_row(row.machine, row.compiler)
    row_dir = get_row_dir(config, manifest, row)

    if not_run is not None:
        text = _not_run_report(manifest, row, not_run, notes, agent)
    else:
        text = _results_report(config, manifest, row, row_dir, notes, agent)

    path = os.path.join(row_dir, 'report.md')
    url = report.deliver(text, path, manifest.pull_request, post)
    return text, url, path


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
    return (
        f'Tested {merged} as `{manifest.test_commit[:10]}`, against '
        f'{baseline}.'
    )


def _not_run_report(manifest, row, reason, notes, agent):
    return report.assemble(
        heading=f'Testing: {row.label}',
        marker=report.make_marker(
            manifest, row=row.name, status='not-run', result='none'
        ),
        sections=[f'Not run: {reason}', describe_commits(manifest)],
        manifest=manifest,
        notes=notes,
        agent=agent,
    )


def _results_report(config, manifest, row, row_dir, notes, agent):
    state = read_state(row_dir)
    pr_md = _read_required(
        os.path.join(state.pr_work_dir, f'{SUITE}_output_for_pr.md'),
        'the PR suite has not finished',
    )
    ctest_md = _read_required(
        os.path.join(state.pr_build_dir, 'ctest_output_for_pr.md'),
        'the CTests have not finished',
    )
    passed, total, suite_line = _summarize_suite(state.pr_work_dir)
    ctest_passed, ctest_line = _summarize_ctests(state.pr_build_dir)

    changed = git_tools.git(
        [
            'diff',
            '--name-only',
            f'{manifest.base_head}...{manifest.pr_head}',
        ],
        config.omega_repo,
    ).splitlines()
    baseline_build = None
    if state.baseline_build_log is not None:
        baseline_build = os.path.dirname(state.baseline_build_log)
    warnings_text, new_warnings = format_warnings_section(
        baseline_build, state.pr_build_dir, changed
    )

    result = 'pass' if passed == total and ctest_passed else 'fail'
    return report.assemble(
        heading=f'Testing: {row.label}',
        marker=report.make_marker(
            manifest,
            row=row.name,
            status='complete',
            result=result,
            new_warnings=new_warnings,
        ),
        sections=[
            f'{ctest_line} {suite_line}',
            describe_commits(manifest),
            pr_md,
            ctest_md,
            warnings_text,
        ],
        manifest=manifest,
        notes=notes,
        agent=agent,
    )


def _read_required(path, what):
    if not os.path.exists(path):
        raise ReportError(
            f'There is no {os.path.basename(path)} in {os.path.dirname(path)}'
            f', so {what}.  Report once the job is done, or use --not-run '
            f'if it cannot be.'
        )
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _summarize_suite(work_dir) -> Tuple[int, int, str]:
    path = os.path.join(work_dir, f'{SUITE}_results.json')
    with open(path, 'r', encoding='utf-8') as f:
        results = json.load(f)
    summary = results['summary']
    total = summary['total']
    passed = summary['passed']
    diffs = [
        task['path']
        for task in results.get('tasks', [])
        if task.get('baseline') == 'fail'
    ]
    line = f'`{SUITE}`: {passed} of {total} tasks passed'
    if diffs:
        line = f'{line}, {len(diffs)} with baseline differences'
    if not results.get('complete', False):
        line = f'{line} (the run did not finish)'
    return passed, total, f'{line}.'


def _summarize_ctests(build_dir) -> Tuple[bool, str]:
    path = os.path.join(build_dir, 'ctests.log')
    counts: List[Tuple[str, str, str]] = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            counts = _CTEST_COUNTS.findall(f.read())
    if not counts:
        return False, 'CTests: no summary found.'
    _, failed, total = counts[-1]
    passed = int(total) - int(failed)
    return int(failed) == 0, f'CTests: {passed} of {total} passed.'
