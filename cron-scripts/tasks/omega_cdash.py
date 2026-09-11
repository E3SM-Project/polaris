#!/usr/bin/env python3
"""
Nightly task: build Omega ``develop`` and submit its CTests to CDash.

The checkout of ``develop`` lives at ``<cron_root>/omega_develop`` and is
brought up to date each night.  The build, the job that runs the CTests and
the CDash submission all go through ``utils/omega/ctest/omega_ctest.py
--dashboard``; this task only keeps the checkout current and picks the build
name, ``unitest-develop-<compiler>``, that CDash's group rules expect.
"""

import os
import subprocess

from common import omega_ctest_command, parse_task_args, run

OMEGA_REMOTE = 'https://github.com/E3SM-Project/Omega.git'
OMEGA_BRANCH = 'develop'


def main():
    args = parse_task_args(
        'Build Omega develop and submit its CTests to CDash'
    )

    omega = os.path.join(args.cron_root, 'omega_develop')
    update_checkout(omega)

    work_dir = os.path.join(
        args.cron_root, 'tasks', 'omega_cdash', args.compiler
    )
    os.makedirs(work_dir, exist_ok=True)

    command = omega_ctest_command(
        polaris_root=args.polaris_root,
        args=args,
        branch=omega,
        build_name=f'unitest-{OMEGA_BRANCH}-{args.compiler}',
        extra=['--submit', '--cdash_submit'],
    )
    run(command, cwd=work_dir)


def update_checkout(omega):
    """
    Clone Omega if needed, then reset the checkout to the tip of ``develop``.
    The nested submodules are handled by the Polaris build script.
    """
    if not os.path.isdir(os.path.join(omega, '.git')):
        run(['git', 'clone', '-b', OMEGA_BRANCH, OMEGA_REMOTE, omega])
    run(['git', 'fetch', 'origin', OMEGA_BRANCH], cwd=omega)
    run(
        ['git', 'checkout', '-q', '-f', '-B', OMEGA_BRANCH, 'FETCH_HEAD'],
        cwd=omega,
    )
    commit = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'], cwd=omega, text=True
    ).strip()
    print(f'Omega {OMEGA_BRANCH} at {commit}')


if __name__ == '__main__':
    main()
