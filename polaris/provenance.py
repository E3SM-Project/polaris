import os
import subprocess
import sys


def write(work_dir, tasks, config=None):
    """
    Write a file with provenance, such as the git version, conda packages,
    command, and tasks, to the work directory

    Parameters
    ----------
    work_dir : str
        The path to the work directory where the tasks will be set up

    tasks : dict
        A dictionary describing all of the tasks and their steps

    config : polaris.config.PolarisConfigParser
        Configuration options for this task, a combination of user configs
        and the defaults for the machine and component
    """
    polaris_git_version = None
    if os.path.exists('.git'):
        try:
            args = ['git', 'describe', '--tags', '--dirty', '--always']
            polaris_git_version = subprocess.check_output(args).decode('utf-8')
            polaris_git_version = polaris_git_version.strip('\n')
        except subprocess.CalledProcessError:
            pass

    if config is None:
        # this is a call to clean and we don't need to document the component
        # version
        component_git_version = None
    else:
        component_git_version = _get_component_git_version(config)

    try:
        args = ['conda', 'list']
        conda_list = subprocess.check_output(args).decode('utf-8')
    except subprocess.CalledProcessError:
        conda_list = None

    calling_command = ' '.join(sys.argv)

    try:
        os.makedirs(work_dir)
    except OSError:
        pass

    provenance_path = f'{work_dir}/provenance'
    if os.path.exists(provenance_path):
        provenance_file = open(provenance_path, 'a')
        provenance_file.write('\n')
    else:
        provenance_file = open(provenance_path, 'w')

    provenance_file.write(
        '**************************************************'
        '*********************\n'
    )
    if polaris_git_version is not None:
        provenance_file.write(
            f'polaris git version: {polaris_git_version}\n\n'
        )
    if component_git_version is not None:
        provenance_file.write(
            f'component git version: {component_git_version}\n\n'
        )
    provenance_file.write(f'command: {calling_command}\n\n')
    provenance_file.write('tasks:\n')

    for _, task in tasks.items():
        prefix = '  '
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
        lines.append(f'{prefix}steps:')
        for step in task.steps.values():
            if step.name == step.subdir:
                lines.append(f'{prefix} - {step.name}')
            else:
                lines.append(f'{prefix} - {step.name}: {step.subdir}')
        lines.append('')
        print_string = '\n'.join(lines)

        provenance_file.write(f'{print_string}\n')

    if conda_list is not None:
        provenance_file.write('conda list:\n')
        provenance_file.write(f'{conda_list}\n')

    provenance_file.write(
        '**************************************************'
        '*********************\n'
    )
    provenance_file.close()


def _get_component_git_version(config):
    if config.has_option('paths', 'component_path'):
        component_path = config.get('paths', 'component_path')
    else:
        component_path = None

    if component_path is None or not os.path.exists(component_path):
        return None

    cwd = os.getcwd()
    os.chdir(component_path)

    try:
        args = ['git', 'describe', '--tags', '--dirty', '--always']
        component_git_version = subprocess.check_output(args).decode('utf-8')
        component_git_version = component_git_version.strip('\n')
    except subprocess.CalledProcessError:
        component_git_version = None
    os.chdir(cwd)

    return component_git_version
