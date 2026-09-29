#!/usr/bin/env python3
"""
Test an Omega pull request on the supported machines

See README.md for the workflow and AGENTS.md for the instructions agents
follow.  Run this from a shell with the Polaris load script sourced.
"""

import argparse
import sys

import pr_test_init
from pr_test_config import ConfigError, read_config
from pr_test_git import GitError
from pr_test_github import GitHubError
from pr_test_manifest import ManifestError, get_row

#: the errors that are reported as a message rather than a traceback
EXPECTED_ERRORS = (
    ConfigError,
    GitError,
    GitHubError,
    ManifestError,
    ValueError,
    pr_test_init.InitError,
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

    return parser.parse_args()


if __name__ == '__main__':
    main()
