#!/usr/bin/env python3
"""
Test an Omega pull request on the supported machines

See README.md for the workflow and AGENTS.md for the instructions agents
follow.  Run this from a shell with a Polaris load script sourced.
"""

import argparse
import os
import sys

# the modules the PR testing utilities share
sys.path.insert(
    1,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
        'pr_testing',
    ),
)

import omega_pr_init  # noqa: E402
import omega_pr_lint  # noqa: E402
import omega_pr_report  # noqa: E402
import omega_pr_setup  # noqa: E402
import omega_pr_status  # noqa: E402
from omega_pr_manifest import (  # noqa: E402
    MARKER_PREFIX,
    UPSTREAM,
    ManifestError,
    fetch_manifest,
    get_row,
)
from pr_test_config import ConfigError, read_config  # noqa: E402
from pr_test_git import GitError  # noqa: E402
from pr_test_github import GitHubError  # noqa: E402
from pr_test_report import ReportError, post_file, read_notes  # noqa: E402
from pr_test_setup import SetupError, format_state  # noqa: E402

from polaris.job import SubmissionError  # noqa: E402

#: the errors that are reported as a message rather than a traceback
EXPECTED_ERRORS = (
    ConfigError,
    GitError,
    GitHubError,
    ManifestError,
    ValueError,
    omega_pr_init.InitError,
    omega_pr_lint.LintError,
    ReportError,
    SetupError,
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
    result = omega_pr_init.initiate(
        config=config,
        pull_request=args.pr,
        polaris_ref=args.polaris_ref,
        baseline_polaris_ref=args.baseline_polaris_ref,
        baseline_ref=args.baseline,
        reason=args.reason,
        test_ref=args.test_ref,
        merge_prs=args.merge_pr,
        baseline_merge_prs=args.baseline_merge_pr,
        rows=rows,
        notes=args.notes,
        push=args.push,
        force=args.force,
    )
    print(omega_pr_init.format_result(result, config.omega_repo))


def _lint(args):
    config = read_config(args.config_file)
    text, url, path, from_ci = omega_pr_lint.run_lint(
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
    state = omega_pr_setup.run_setup(
        config=config,
        fork=args.fork,
        branch=args.branch,
        submit=args.submit,
        baseline_dir=args.baseline_dir,
        baseline_load_script=args.baseline_load_script,
        no_baseline=args.no_baseline,
    )
    machine = state.row.split('/')[0]
    row_dir = os.path.dirname(state.pr_work_dir)
    print(format_state(state, row_dir, machine))


def _report(args):
    config = read_config(args.config_file)
    text, url, path = omega_pr_report.run_report(
        config=config,
        fork=args.fork,
        branch=args.branch,
        machine=args.machine,
        not_run=args.not_run,
        notes=read_notes(args.notes),
        agent=args.agent,
        post=args.post,
    )
    _print_report(text, url, path)


def _post(args):
    url = post_file(UPSTREAM, args.pr, args.comment, MARKER_PREFIX)
    print(f'Posted {url}')


def _status(args):
    config = None
    manifest = None
    if args.branch is not None:
        if args.fork is None:
            raise ValueError('--branch needs --fork.')
        config = read_config(args.config_file)
        manifest = fetch_manifest(config.omega_repo, args.fork, args.branch)
    print(omega_pr_status.run_status(args.pr, manifest, config))


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
        help='The config file, ~/.config/omega_pr_test.cfg by default',
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
        '--reason',
        help='Why --baseline is used instead of the submodule, as a '
        'lowercase clause that reports print after "because", such as '
        '"answer-changing PRs have merged into develop since the commit '
        'Polaris pins"',
    )
    init.add_argument(
        '--test-ref',
        help='A merge of the PR into its base branch that the requester '
        'made, such as one resolving conflicts, to test instead of the merge '
        'init makes: a branch on the fork or a commit',
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
        help='The Polaris commit the PR is tested with, which every '
        "tester's checkout must contain, the current main of "
        'E3SM-Project/polaris by default',
    )
    init.add_argument(
        '--baseline-polaris-ref',
        help='The Polaris commit the baseline runs with, whose Omega '
        'submodule is the baseline, the --polaris-ref commit by default.  '
        'Needed when the PR needs Polaris changes that the baseline Omega '
        'cannot run.  main is always the main of E3SM-Project/polaris, '
        "never the requester's fork's.",
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
        '--baseline-load-script',
        help='The load script for this row of a second Polaris checkout at '
        "the manifest's baseline Polaris commit, to find or set up the "
        'baseline with.  Needed when that commit is not the Polaris commit '
        'the PR is tested with.',
    )
    setup.add_argument(
        '--no-baseline',
        metavar='REASON',
        help='Run the PR suite without a baseline, for a row where the '
        'baseline commit cannot run, with the reason as a lowercase clause '
        'that the report prints after "because".  Only if the requester '
        'asks.',
    )
    setup.add_argument(
        '--submit',
        action='store_true',
        help="Submit the jobs.  Agents pass this only with the requester's "
        'permission.',
    )
    setup.set_defaults(func=_setup)

    report = subparsers.add_parser(
        'report',
        help="Write and post the Testing comment for a machine's rows "
        '(tester)',
    )
    _add_branch_args(report)
    report.add_argument(
        '--machine',
        help='The machine, that of the loaded Polaris environment, or else '
        'the one this runs on, by default.  Pm-cpu and pm-gpu share a '
        'comment.',
    )
    report.add_argument(
        '--not-run',
        metavar='REASON',
        help='Report the rows without results as not run, and why',
    )
    _add_report_args(report)
    report.set_defaults(func=_report)

    post = subparsers.add_parser(
        'post',
        help='Post a Testing comment that report or lint wrote, such as one '
        'copied from a machine without gh.  Agents run this only with the '
        "requester's permission.",
    )
    post.add_argument('--pr', type=int, required=True, help='The Omega PR')
    post.add_argument('comment', help="The comment's file")
    post.set_defaults(func=_post)

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
