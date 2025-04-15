import argparse
import importlib.resources as imp_res
import os
import re
import sys

from polaris.tasks import get_components


def list_cases(task_expr=None, number=None, verbose=False):
    """
    List the available tasks

    Parameters
    ----------
    task_expr : str, optional
        A regular expression for a task path name to search for

    number : int, optional
        The number of the task to list

    verbose : bool, optional
        Whether to print details of each task or just the subdirectories.
        When applied to suites, verbose will list the tasks in the suite.
    """
    components = get_components()

    if number is None:
        print('Tasks:')

    tasks = []
    for component in components:
        for task in component.tasks.values():
            tasks.append(task)

    for task_number, task in enumerate(tasks):
        print_number = False
        print_task = False
        if number is not None:
            if number == task_number:
                print_task = True
        elif task_expr is None or re.match(task_expr, task.path):
            print_task = True
            print_number = True

        if print_task:
            number_string = f'{task_number:d}: '.rjust(6)
            if print_number:
                prefix = number_string
            else:
                prefix = ''
            if verbose:
                lines = list()
                to_print = {
                    'path': task.path,
                    'name': task.name,
                    'component': task.component.name,
                    'subdir': task.subdir,
                }
                for key in to_print:
                    key_string = f'{key}: '.ljust(15)
                    lines.append(f'{prefix}{key_string}{to_print[key]}')
                    if print_number:
                        prefix = '      '
                lines.append(f'{prefix}steps:')
                longest = 0
                for step in task.steps.values():
                    longest = max(longest, len(step.name))
                for step in task.steps.values():
                    step_name = f'{step.name}: '.ljust(longest + 2)
                    lines.append(f'{prefix} - {step_name}{step.path}')
                lines.append('')
                print_string = '\n'.join(lines)
            else:
                print_string = f'{prefix}{task.path}'

            print(print_string)


def list_machines():
    machine_configs = sorted(
        [
            resource.name
            for resource in imp_res.files('polaris.machines').iterdir()
            if resource.is_file()
        ]
    )

    print('Machines:')
    for config in machine_configs:
        if config.endswith('.cfg'):
            print(f'   {os.path.splitext(config)[0]}')


def list_suites(components=None, verbose=False):
    if components is None:
        components = [component.name for component in get_components()]
    print('Suites:')
    for component in components:
        package = f'polaris.suites.{component}'
        try:
            suites = sorted(
                [
                    resource.name
                    for resource in imp_res.files(package).iterdir()
                    if resource.is_file()
                ]
            )
        except FileNotFoundError:
            continue
        for suite in sorted(suites):
            print_header_if_cached = True
            if suite.endswith('.txt'):
                print(f'  -c {component} -t {os.path.splitext(suite)[0]}')
                if verbose:
                    text = imp_res.files(package).joinpath(suite).read_text()
                    tasks = list()
                    for task in text.split('\n'):
                        task = task.strip()
                        if task == 'cached':
                            print('\t  Cached steps: all')
                        elif task.startswith('cached'):
                            if print_header_if_cached:
                                print('\t  Cached steps:')
                            # don't print the header again if there are
                            # multiple lines of cached steps
                            print_header_if_cached = False
                            print(task.replace('cached: ', '\t    '))
                        elif (
                            len(task) > 0
                            and task not in tasks
                            and not task.startswith('#')
                        ):
                            print(f'\t* {task}')
                            print_header_if_cached = True


def main():
    parser = argparse.ArgumentParser(
        description='List the available tasks or machines', prog='polaris list'
    )
    parser.add_argument(
        '-t',
        '--task_expr',
        dest='task_expr',
        help='A regular expression for a task path name to search for.',
        metavar='TASK',
    )
    parser.add_argument(
        '-n',
        '--number',
        dest='number',
        type=int,
        help='The number of the task to list.',
    )
    parser.add_argument(
        '--machines',
        dest='machines',
        action='store_true',
        help='List supported machines (instead of task cases).',
    )
    parser.add_argument(
        '--suites',
        dest='suites',
        action='store_true',
        help='List suites (instead of tasks).',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        dest='verbose',
        action='store_true',
        help='List details of each task, not just the '
        'path.  When applied to suites, verbose lists '
        'the tasks contained in each suite.',
    )
    args = parser.parse_args(sys.argv[2:])
    if args.machines:
        list_machines()
    elif args.suites:
        list_suites(verbose=args.verbose)
    else:
        list_cases(
            task_expr=args.task_expr, number=args.number, verbose=args.verbose
        )
