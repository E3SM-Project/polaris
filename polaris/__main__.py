#!/usr/bin/env python3

import argparse
import importlib
import os
import sys

from polaris.version import __version__

# the module whose main() runs each command, imported only for the command
# that is run, so that each command imports only what it needs
COMMANDS = {
    'list': 'polaris.list',
    'setup': 'polaris.setup',
    'suite': 'polaris.suite',
    'serial': 'polaris.run.serial',
    'parallel': 'polaris.run.parallel',
}


def main():
    """
    Entry point for the main script ``polaris``
    """

    parser = argparse.ArgumentParser(
        description='Perform polaris operations',
        usage="""
polaris <command> [<args>]

The available polaris commands are:
    list    List the available test cases
    setup   Set up a test case
    suite   Manage a regression test suite
    serial  Run a suite, test case or step in task serial
    parallel  Run a suite or task with independent steps at the same time

 To get help on an individual command, run:

    polaris <command> --help
    """,
    )

    parser.add_argument('command', help='command to run')
    parser.add_argument(
        '-v',
        '--version',
        action='version',
        version=f'polaris {__version__}',
        help='Show version number and exit',
    )
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(sys.argv[1:2])

    commands = dict(COMMANDS)

    # only allow the "polaris cache" command if we're on Chrysalis
    allow_cache = 'POLARIS_MACHINE' in os.environ and os.environ[
        'POLARIS_MACHINE'
    ] in ['chrysalis']

    if allow_cache:
        commands['cache'] = 'polaris.cache'

    if args.command not in commands:
        print(f'Unrecognized command {args.command}')
        parser.print_help()
        exit(1)

    # call the main() of the module for the requested command
    module = importlib.import_module(commands[args.command])
    module.main()


if __name__ == '__main__':
    main()
