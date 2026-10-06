"""
The initiator's report on linting and the documentation build, which do not
depend on the machine
"""

import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pr_test_git as git_tools
import pr_test_github as github
import pr_test_report as report
from pr_test_config import PrTestConfig
from pr_test_manifest import Manifest, fetch_manifest

#: the job in Omega's omega-pr workflow that lints and builds the docs
CI_JOB = 'lint and test docs'


class LintError(Exception):
    """Linting and the documentation build could not be checked"""


@dataclass
class Check:
    """
    One of the two checks, how it was run and its result

    Attributes
    ----------
    label : str
        What the check is, as the comment names it

    ci_step : str
        The name of the check's step in the CI job

    command : list of str
        The command that runs the check locally

    subdir : str
        Where in the Omega tree to run it locally
    """

    label: str
    ci_step: str
    command: List[str]
    subdir: str


CHECKS = [
    Check(
        label='pre-commit on the files the PR changes',
        ci_step='Run pre-commit',
        command=['pre-commit', 'run', '--show-diff-on-failure', '--files'],
        subdir='.',
    ),
    Check(
        label='Documentation build (`make html-strict`)',
        ci_step='Build Sphinx Docs',
        command=['make', 'html-strict'],
        subdir='components/omega/doc',
    ),
]


def run_lint(
    config: PrTestConfig,
    fork: str,
    branch: str,
    notes: Optional[str] = None,
    agent: Optional[str] = None,
    post: bool = False,
) -> Tuple[str, Optional[str], str, bool]:
    """
    Report on linting and the documentation build for a test branch

    The results come from Omega's CI for the PR head if its job passed, and
    otherwise from running the same commands on the test commit.  Results
    from CI are never posted, since the PR's own checks already show them.

    Parameters
    ----------
    config : pr_test_config.PrTestConfig
        The settings

    fork : str
        The URL of the requester's fork

    branch : str
        The test branch

    notes : str, optional
        Notes to add to the comment

    agent : str, optional
        The agent posting the comment, which adds the signature

    post : bool, optional
        Whether to post the comment, if its results did not come from CI

    Returns
    -------
    text : str
        The comment

    url : str, optional
        The URL of the posted comment

    path : str
        The file the comment was written to

    from_ci : bool
        Whether the results came from Omega's CI, in which case the comment
        was not posted
    """
    manifest = fetch_manifest(config.omega_repo, fork, branch)
    lint_dir = os.path.join(report.get_run_dir(config, manifest), 'lint')

    ci_run = _find_ci_run(manifest.pr_head)
    ci_line = _format_ci_line(manifest, ci_run)
    from_ci = ci_run is not None and ci_run['conclusion'] == 'success'
    if from_ci:
        results = _ci_results(ci_run)
    else:
        results = _local_results(config, manifest, lint_dir)

    passed = all(result for _, result, _ in results)
    lines = [ci_line, '']
    for label, result, source in results:
        outcome = 'passed' if result else 'failed'
        lines.append(f'- {label}: {outcome} ({source})')

    text = report.assemble(
        heading='Testing: lint and docs',
        marker=report.make_marker(
            manifest,
            row='lint',
            status='complete',
            result='pass' if passed else 'fail',
        ),
        sections=['\n'.join(lines)],
        manifest=manifest,
        notes=notes,
        agent=agent,
    )
    path = os.path.join(lint_dir, 'report.md')
    # results that only repeat what the PR's own checks show are not posted
    url = report.deliver(
        text, path, manifest.pull_request, post and not from_ci
    )
    return text, url, path, from_ci


def _find_ci_run(sha):
    for run in github.get_check_runs(sha):
        if run['name'] == CI_JOB:
            return run
    return None


def _format_ci_line(manifest, ci_run):
    head = f'`{manifest.pr_head[:10]}`'
    if ci_run is None:
        return (
            f'Omega CI has not run its `{CI_JOB}` job on the PR head {head}.'
        )
    if ci_run['status'] != 'completed':
        state = 'has not finished'
    else:
        state = f'finished with `{ci_run["conclusion"]}`'
    return (
        f"Omega CI's [`{CI_JOB}`]({ci_run['html_url']}) job on the PR head "
        f'{head} {state}.'
    )


def _ci_results(ci_run):
    """The result of each check's step in a CI job that passed"""
    steps = {
        step['name']: step['conclusion']
        for step in github.get_job_steps(ci_run['id'])
    }
    return [
        (check.label, steps.get(check.ci_step) == 'success', 'CI')
        for check in CHECKS
    ]


def _local_results(config, manifest: Manifest, lint_dir):
    """Run each check on the test commit in a worktree of its own"""
    if config.omega_dev_env is None:
        raise LintError(
            f'Omega CI\'s "{CI_JOB}" job has not passed on the PR head, so '
            f'the checks have to run here, which needs "omega_dev_env" in '
            f'the config file.'
        )
    repo = config.omega_repo
    # the checks can change files, so they never run in a tree that is built
    worktree = os.path.join(lint_dir, 'omega')
    git_tools.add_worktree(repo, manifest.test_commit, worktree)

    changed = git_tools.git(
        [
            'diff',
            '--name-only',
            '--diff-filter=d',
            f'{manifest.base_head}...{manifest.pr_head}',
        ],
        repo,
    ).splitlines()

    env = dict(os.environ)
    env['PATH'] = f'{config.omega_dev_env}/bin:{env["PATH"]}'
    results = []
    for check in CHECKS:
        command = list(check.command)
        if check.command[0] == 'pre-commit':
            command.extend(changed)
        name = check.command[0]
        log_path = os.path.join(lint_dir, f'{name}.log')
        with open(log_path, 'w', encoding='utf-8') as log:
            completed = subprocess.run(
                command,
                cwd=os.path.join(worktree, check.subdir),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        results.append(
            (
                check.label,
                completed.returncode == 0,
                f'local run on the test commit, log `{log_path}`',
            )
        )
    return results
