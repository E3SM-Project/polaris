#!/usr/bin/env python3

import argparse
import os
import sys

import polaris.run.serial as run_serial
from polaris import cache, list, setup, suite
from polaris.version import __version__


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

    commands = {
        'list': list.main,
        'setup': setup.main,
        'suite': suite.main,
        'serial': run_serial.main,
    }

    # only allow the "polaris cache" command if we're on Anvil or Chrysalis
    allow_cache = 'POLARIS_MACHINE' in os.environ and os.environ[
        'POLARIS_MACHINE'
    ] in ['anvil', 'chrysalis']

    if allow_cache:
        commands['cache'] = cache.main

    if args.command not in commands:
        print(f'Unrecognized command {args.command}')
        parser.print_help()
        exit(1)

    # call the function associated with the requested command
    commands[args.command]()


if __name__ == '__main__':
    main()
