#!/usr/bin/env python3
"""
Test an Omega pull request on the supported machines

See README.md for the workflow and AGENTS.md for the instructions agents
follow.  Run this from a shell with the Polaris load script sourced.
"""

import argparse
import os
import sys

import pr_test_init
import pr_test_lint
import pr_test_results
import pr_test_setup
import pr_test_status
from pr_test_config import ConfigError, read_config
from pr_test_git import GitError
from pr_test_github import GitHubError
from pr_test_manifest import ManifestError, fetch_manifest, get_row
from pr_test_report import read_notes

from polaris.job import SubmissionError

#: the errors that are reported as a message rather than a traceback
EXPECTED_ERRORS = (
    ConfigError,
    GitError,
    GitHubError,
    ManifestError,
    ValueError,
    pr_test_init.InitError,
    pr_test_lint.LintError,
    pr_test_results.ReportError,
    pr_test_setup.SetupError,
    SubmissionError,
)


def main():
    """Run a subcommand of the Omega PR testing utility"""
    args = _parse_args()
    try:
        args.func(args)
    except EXPECTED_ERRORS as exc:
        print(f'\nError: {exc}', file=sys.stderr)
        sys.exit(1)


def _init(args):
    config = read_config(args.config_file)
    rows = None
    if args.rows is not None:
        rows = [get_row(name) for name in args.rows.split(',')]
    result = pr_test_init.initiate(
        config=config,
        pull_request=args.pr,
        polaris_ref=args.polaris_ref,
        baseline_ref=args.baseline,
        reason=args.reason,
        merge_prs=args.merge_pr,
        baseline_merge_prs=args.baseline_merge_pr,
        rows=rows,
        notes=args.notes,
        push=args.push,
        force=args.force,
    )
    print(pr_test_init.format_result(result, config.omega_repo))


def _lint(args):
    config = read_config(args.config_file)
    text, url, path, from_ci = pr_test_lint.run_lint(
        config=config,
        fork=args.fork,
        branch=args.branch,
        notes=read_notes(args.notes),
        agent=args.agent,
        post=args.post,
    )
    if from_ci:
        print(text)
        print(
            f"Not posted: Omega CI's checks passed, which the PR already "
            f'shows.  The comment is in {path}'
        )
    else:
        _print_report(text, url, path)


def _setup(args):
    config = read_config(args.config_file)
    state = pr_test_setup.run_setup(
        config=config,
        fork=args.fork,
        branch=args.branch,
        submit=args.submit,
        baseline_dir=args.baseline_dir,
    )
    machine = state.row.split('/')[0]
    row_dir = os.path.dirname(state.pr_work_dir)
    print(pr_test_setup.format_state(state, row_dir, machine))


def _report(args):
    config = read_config(args.config_file)
    text, url, path = pr_test_results.run_report(
        config=config,
        fork=args.fork,
        branch=args.branch,
        row_name=args.row,
        not_run=args.not_run,
        notes=read_notes(args.notes),
        agent=args.agent,
        post=args.post,
    )
    _print_report(text, url, path)


def _status(args):
    manifest = None
    if args.branch is not None:
        if args.fork is None:
            raise ValueError('--branch needs --fork.')
        config = read_config(args.config_file)
        manifest = fetch_manifest(config.omega_repo, args.fork, args.branch)
    print(pr_test_status.run_status(args.pr, manifest))


def _print_report(text, url, path):
    if url is None:
        print(text)
        print(f'Not posted.  The comment is in {path}')
    else:
        print(f'Posted {url}')


def _add_branch_args(parser):
    parser.add_argument(
        '--fork', required=True, help="The URL of the requester's fork"
    )
    parser.add_argument('--branch', required=True, help='The test branch')


def _add_report_args(parser):
    parser.add_argument(
        '--notes', help='A file with notes to add to the comment'
    )
    parser.add_argument(
        '--agent',
        help='The agent posting the comment, e.g. "Claude Code", which adds '
        'the signature',
    )
    parser.add_argument(
        '--post',
        action='store_true',
        help='Post the comment on the PR.  Agents pass this only with the '
        "requester's permission.",
    )


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Test an Omega pull request on the supported machines'
    )
    parser.add_argument(
        '-f',
        '--config_file',
        help='The per-machine config file, ~/.config/omega_pr_test.cfg by '
        'default',
    )
    subparsers = parser.add_subparsers(required=True, metavar='command')

    init = subparsers.add_parser(
        'init',
        help='Pin the commits to test in a branch with a manifest',
    )
    init.add_argument(
        '--pr', type=int, required=True, help='The Omega PR to test'
    )
    init.add_argument(
        '--baseline',
        help='An Omega branch or commit to compare against instead of '
        "Polaris' Omega submodule",
    )
    init.add_argument(
        '--reason', help='Why --baseline is used instead of the submodule'
    )
    init.add_argument(
        '--merge-pr',
        type=int,
        action='append',
        default=[],
        help='Another Omega PR to merge into the test commit, such as a '
        'build fix still in review (may be repeated)',
    )
    init.add_argument(
        '--baseline-merge-pr',
        type=int,
        action='append',
        default=[],
        help='Another Omega PR to merge into the baseline commit (may be '
        'repeated)',
    )
    init.add_argument(
        '--rows',
        help='Comma-separated <machine>/<compiler> rows to test, those of '
        'the Omega PR template by default',
    )
    init.add_argument(
        '--polaris-ref',
        help='The Polaris commit whose Omega submodule is the baseline, the '
        'current main of E3SM-Project/polaris by default',
    )
    init.add_argument('--notes', help='Notes for the requester')
    init.add_argument(
        '--push',
        action='store_true',
        help="Push the branches to the requester's fork.  Agents pass this "
        "only with the requester's permission.",
    )
    init.add_argument(
        '--force',
        action='store_true',
        help='Overwrite branches of the same name on the fork',
    )
    init.set_defaults(func=_init)

    lint = subparsers.add_parser(
        'lint',
        help='Check linting and the documentation build, posting only if '
        "they had to run here because Omega's CI had not passed (initiator)",
    )
    _add_branch_args(lint)
    _add_report_args(lint)
    lint.set_defaults(func=_lint)

    setup = subparsers.add_parser(
        'setup',
        help="Set up this machine's row: baseline, PR suite and CTests "
        '(tester)',
    )
    _add_branch_args(setup)
    setup.add_argument(
        '--baseline-dir',
        help='An existing baseline work directory to use, which must match',
    )
    setup.add_argument(
        '--submit',
        action='store_true',
        help="Submit the jobs.  Agents pass this only with the requester's "
        'permission.',
    )
    setup.set_defaults(func=_setup)

    report = subparsers.add_parser(
        'report', help="Write and post this machine's Testing comment (tester)"
    )
    _add_branch_args(report)
    report.add_argument(
        '--row',
        help='The <machine>/<compiler> row, that of the loaded Polaris '
        'environment by default',
    )
    report.add_argument(
        '--not-run',
        metavar='REASON',
        help='Report the row as not run, and why',
    )
    _add_report_args(report)
    report.set_defaults(func=_report)

    status = subparsers.add_parser(
        'status', help="List the rows' Testing comments on the PR"
    )
    status.add_argument('--pr', type=int, required=True, help='The Omega PR')
    status.add_argument(
        '--fork', help="The requester's fork, to list the manifest's rows"
    )
    status.add_argument(
        '--branch', help="The test branch, to list the manifest's rows"
    )
    status.set_defaults(func=_status)

    return parser.parse_args()


if __name__ == '__main__':
    main()
