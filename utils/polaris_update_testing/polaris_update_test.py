#!/usr/bin/env python3
"""
Test a Polaris version update on the supported machines

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
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'pr_testing',
    ),
)

import polaris_update_deploy  # noqa: E402
import polaris_update_init  # noqa: E402
import polaris_update_report  # noqa: E402
import polaris_update_setup  # noqa: E402
import polaris_update_status  # noqa: E402
from polaris_update_manifest import (  # noqa: E402
    MARKER_PREFIX,
    UPSTREAM,
    ManifestError,
    fetch_manifest,
)
from pr_test_config import ConfigError, read_config  # noqa: E402
from pr_test_git import POLARIS_DIR, GitError  # noqa: E402
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
    polaris_update_deploy.DeployError,
    polaris_update_init.InitError,
    ReportError,
    SetupError,
    SubmissionError,
)


def main():
    """Run a subcommand of the Polaris version update testing utility"""
    args = _parse_args()
    try:
        args.func(args)
    except EXPECTED_ERRORS as exc:
        print(f'\nError: {exc}', file=sys.stderr)
        sys.exit(1)


def _init(args):
    config = read_config(args.config_file)
    row_names = None
    if args.rows is not None:
        row_names = args.rows.split(',')
    result = polaris_update_init.initiate(
        config=config,
        pull_request=args.pr,
        baseline_ref=args.baseline,
        row_names=row_names,
        merge_omega_prs=args.merge_omega_pr,
        notes=args.notes,
        push=args.push,
        force=args.force,
    )
    print(polaris_update_init.format_result(result, POLARIS_DIR))


def _deploy(args):
    config = read_config(args.config_file)
    deployments = polaris_update_deploy.run_deploy(
        config=config,
        fork=args.fork,
        branch=args.branch,
        machine=args.machine,
        spack_path=args.spack_path,
        recreate=args.recreate,
        run=args.run,
    )
    print(polaris_update_deploy.format_deployments(deployments, POLARIS_DIR))


def _setup(args):
    config = read_config(args.config_file)
    states = polaris_update_setup.run_setup(
        config=config,
        fork=args.fork,
        branch=args.branch,
        submit=args.submit,
        baseline_load_script=args.baseline_load_script,
        no_baseline=args.no_baseline,
    )
    for state, row_dir in states:
        machine = state.row.split('/')[0]
        print(f'\n{format_state(state, row_dir, machine)}')


def _report(args):
    config = read_config(args.config_file)
    text, url, path = polaris_update_report.run_report(
        config=config,
        fork=args.fork,
        branch=args.branch,
        machine=args.machine,
        spack=args.spack,
        not_run=args.not_run,
        notes=read_notes(args.notes),
        agent=args.agent,
        post=args.post,
    )
    if url is None:
        print(text)
        print(f'Not posted.  The comment is in {path}')
    else:
        print(f'Posted {url}')


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
        manifest = fetch_manifest(POLARIS_DIR, args.fork, args.branch)
    print(polaris_update_status.run_status(args.pr, manifest, config))


def _add_branch_args(parser):
    parser.add_argument(
        '--fork', required=True, help="The URL of the requester's Polaris fork"
    )
    parser.add_argument('--branch', required=True, help='The test branch')


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Test a Polaris version update on the supported machines'
    )
    parser.add_argument(
        '-f',
        '--config_file',
        help='The config file, ~/.config/polaris_pr_test.cfg by default',
    )
    subparsers = parser.add_subparsers(required=True, metavar='command')

    init = subparsers.add_parser(
        'init', help='Pin what to test in a branch with a manifest'
    )
    init.add_argument(
        '--pr', type=int, required=True, help='The Polaris PR to test'
    )
    init.add_argument(
        '--baseline',
        help='The Polaris commit to compare against, "main" for the current '
        'main of E3SM-Project/polaris.  Without it, there is no baseline.',
    )
    init.add_argument(
        '--rows',
        help='Comma-separated <machine>/<compiler>/<model> rows to test, '
        'every row the PR supports by default',
    )
    init.add_argument(
        '--merge-omega-pr',
        type=int,
        action='append',
        default=[],
        help='An Omega PR to merge into the Omega the Polaris PR pins, such '
        'as a fix still in review (may be repeated).  The merge is pushed to '
        'the E3SM fork, "fork" in the config file.',
    )
    init.add_argument('--notes', help='Notes for the requester')
    init.add_argument(
        '--push',
        action='store_true',
        help="Push the branches to the requester's forks.  Agents pass "
        "this only with the requester's permission.",
    )
    init.add_argument(
        '--force',
        action='store_true',
        help='Overwrite a branch of the same name on the fork',
    )
    init.set_defaults(func=_init)

    deploy = subparsers.add_parser(
        'deploy',
        help="Deploy the Spack environments for this machine's rows, or "
        'show the command that would (tester)',
    )
    _add_branch_args(deploy)
    deploy.add_argument(
        '--machine',
        help='The machine, the one this runs on by default.  Pm-cpu and '
        'pm-gpu are deployed one after the other.',
    )
    deploy.add_argument(
        '--spack-path',
        help='Where to deploy test environments; the shared environments by '
        'default',
    )
    deploy.add_argument(
        '--recreate',
        action='store_true',
        help='Recreate environments that exist',
    )
    deploy.add_argument(
        '--run',
        action='store_true',
        help='Run the deployment.  Agents pass this only with the '
        "requester's permission.",
    )
    deploy.set_defaults(func=_deploy)

    setup = subparsers.add_parser(
        'setup',
        help='Set up the rows the loaded load script tests: baseline, PR '
        'suite and CTests (tester)',
    )
    _add_branch_args(setup)
    setup.add_argument(
        '--baseline-load-script',
        help='The load script for the same compiler of a second Polaris '
        "checkout at the manifest's baseline commit",
    )
    setup.add_argument(
        '--no-baseline',
        metavar='REASON',
        help="Run these rows without the manifest's baseline, with the "
        'reason as a lowercase clause that the report prints after '
        '"because".  Only if the requester asks.',
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
        '--spack',
        choices=polaris_update_report.SPACK_KINDS,
        help='The kind of Spack environment, that of the loaded load script '
        'by default',
    )
    report.add_argument(
        '--not-run',
        metavar='REASON',
        help='Report the rows without results as not run, and why',
    )
    report.add_argument(
        '--notes', help='A file with notes to add to the comment'
    )
    report.add_argument(
        '--agent',
        help='The agent posting the comment, e.g. "Claude Code", which adds '
        'the signature',
    )
    report.add_argument(
        '--post',
        action='store_true',
        help='Post the comment on the PR.  Agents pass this only with the '
        "requester's permission.",
    )
    report.set_defaults(func=_report)

    post = subparsers.add_parser(
        'post',
        help='Post a Testing comment that report wrote, such as one copied '
        'from a machine without gh.  Agents run this only with the '
        "requester's permission.",
    )
    post.add_argument('--pr', type=int, required=True, help='The Polaris PR')
    post.add_argument('comment', help="The comment's file")
    post.set_defaults(func=_post)

    status = subparsers.add_parser(
        'status', help="List the rows' Testing comments on the PR"
    )
    status.add_argument('--pr', type=int, required=True, help='The Polaris PR')
    status.add_argument(
        '--fork', help="The requester's Polaris fork, to list the rows"
    )
    status.add_argument('--branch', help='The test branch, to list the rows')
    status.set_defaults(func=_status)

    return parser.parse_args()


if __name__ == '__main__':
    main()
