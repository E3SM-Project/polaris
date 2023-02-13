#!/usr/bin/env python3

import argparse
import sys

from polaris import list, setup
from polaris.version import __version__


def main():
    """
    Entry point for the main script ``polaris``
    """

    parser = argparse.ArgumentParser(
        description="Perform polaris operations",
        usage='''
polaris <command> [<args>]

The available polaris commands are:
    list    List the available test cases
    setup   Set up a test case
    clean   Clean up a test case
    suite   Manage a regression test suite
    run     Run a suite, test case or step

 To get help on an individual command, run:

    polaris <command> --help
    ''')

    parser.add_argument('command', help='command to run')
    parser.add_argument('-v', '--version',
                        action='version',
                        version=f'polaris {__version__}',
                        help="Show version number and exit")
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args(sys.argv[1:2])

    commands = {'list': list.main,
                'setup': setup.main}

    if args.command not in commands:
        print('Unrecognized command {}'.format(args.command))
        parser.print_help()
        exit(1)

    # call the function associated with the requested command
    commands[args.command]()


if __name__ == "__main__":
    main()
