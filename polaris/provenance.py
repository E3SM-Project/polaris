import os
import subprocess
import sys


def write(work_dir, tasks, config=None, machine=None, baseline_dir=None):
    """
    Write a file with provenance, such as the git version, conda packages,
    command, and tasks, to the work directory

    Parameters
    ----------
    work_dir : str
        The path to the work directory where the tasks will be set up

    tasks : dict
        A dictionary describing all of the tasks and their steps

    config : polaris.config.PolarisConfigParser, optional
        Configuration options for this task, a combination of user configs
        and the defaults for the machine and component

    machine : str, optional
        The machine on which Polaris is being run

    baseline_dir : str, optional
        The path to the baseline work directory, if any
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

    # Add readily parsable, PR-friendly metadata discovered at setup time
    _write_meta(provenance_file, 'machine', machine)
    _write_scheduler_metadata(provenance_file, config)
    _write_meta(provenance_file, 'compiler', _get_compiler(config))
    _write_meta(provenance_file, 'work directory', work_dir)
    _write_meta(provenance_file, 'build directory', _get_build_dir(config))
    _write_meta(provenance_file, 'baseline work directory', baseline_dir)
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


def _get_system(config):
    if config is None:
        return None
    if config.has_option('parallel', 'system'):
        return config.get('parallel', 'system')
    return None


def _resolve_scheduler_fields(config, system):
    """Resolve partition/qos/constraint (slurm) or just constraint (pbs)."""
    partition = None
    qos = None
    constraint = None

    if config is None:
        return partition, qos, constraint

    if system == 'pbs':
        # PBS: only constraint is relevant for our purposes
        cons_val = (
            config.get('job', 'constraint')
            if config.has_option('job', 'constraint')
            else None
        )
        if cons_val and cons_val != '<<<default>>>':
            constraint = cons_val
        elif config.has_option('parallel', 'constraints'):
            cons_list = config.getlist('parallel', 'constraints')
            if cons_list:
                constraint = cons_list[0]
        return partition, qos, constraint

    # Default to slurm-like resolution
    part_val = (
        config.get('job', 'partition')
        if config.has_option('job', 'partition')
        else None
    )
    if part_val and part_val != '<<<default>>>':
        partition = part_val
    elif config.has_option('parallel', 'partitions'):
        parts = config.getlist('parallel', 'partitions')
        if parts:
            partition = parts[0]

    qos_val = (
        config.get('job', 'qos') if config.has_option('job', 'qos') else None
    )
    if qos_val and qos_val != '<<<default>>>':
        qos = qos_val
    elif config.has_option('parallel', 'qos'):
        qos_list = config.getlist('parallel', 'qos')
        if qos_list:
            qos = qos_list[0]

    cons_val = (
        config.get('job', 'constraint')
        if config.has_option('job', 'constraint')
        else None
    )
    if cons_val and cons_val != '<<<default>>>':
        constraint = cons_val
    elif config.has_option('parallel', 'constraints'):
        cons_list = config.getlist('parallel', 'constraints')
        if cons_list:
            constraint = cons_list[0]

    return partition, qos, constraint


def _get_compiler(config):
    if config is None:
        return None
    if config.has_option('deploy', 'compiler'):
        val = config.get('deploy', 'compiler')
        return val or None
    return None


def _get_build_dir(config):
    if config is None:
        return None
    if config.has_option('paths', 'component_path'):
        val = config.get('paths', 'component_path')
        return val or None
    return None


def _write_meta(provenance_file, label, value):
    """Write a simple 'label: value' line if value is provided."""
    if value is None:
        return
    if isinstance(value, str) and value.strip() == '':
        return
    provenance_file.write(f'{label}: {value}\n\n')


def _write_scheduler_metadata(provenance_file, config):
    """Write partition/qos/constraint metadata when available."""
    system = _get_system(config)
    partition, qos, constraint = _resolve_scheduler_fields(config, system)
    _write_meta(provenance_file, 'partition', partition)
    _write_meta(provenance_file, 'qos', qos)
    _write_meta(provenance_file, 'constraint', constraint)
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
