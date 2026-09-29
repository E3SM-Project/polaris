import os
import shutil
import subprocess
import sys

from polaris.build.mpas_ocean import get_mpas_ocean_source_dir
from polaris.build.omega import (
    detect_omega_build_type,
    get_omega_source_dir,
)
from polaris.build.source_record import read_source_record
from polaris.version import __version__

# marks a component's git entries that come from its source tree at setup,
# which may have moved since the build
_AT_SETUP = '(at setup, not build)'


def write(
    work_dir,
    tasks,
    config=None,
    machine=None,
    baseline_dir=None,
    job_options=None,
):
    """
    Write a file with provenance, such as the git version, conda packages,
    command, and tasks, to the work directory.

    This function overwrites any existing provenance file in the work
    directory rather than appending, so the provenance reflects the most
    recent call to Polaris that used this work directory.

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

    job_options : {mache.parallel.slurm.SlurmOptions, \
mache.parallel.pbs.PbsOptions}, optional
        The scheduler options that were written to the job script, as
        returned by :py:func:`polaris.job.write_job_script()`.  If not
        provided, no scheduler metadata is recorded.
    """
    polaris_git_info = _get_polaris_git_info()

    if config is None:
        # this is a call to clean and we don't need to document the component
        # version
        component_git_info = None
    else:
        component_git_info = _get_component_git_info(config)

    pixi_list = None
    pixi_exe = _get_pixi_executable()
    if pixi_exe is not None:
        try:
            args = [pixi_exe, 'list']
            pixi_list = subprocess.check_output(args).decode('utf-8')
        except (OSError, subprocess.CalledProcessError):
            pass

    calling_command = ' '.join(sys.argv)

    try:
        os.makedirs(work_dir)
    except OSError:
        pass

    provenance_path = f'{work_dir}/provenance'
    # Always overwrite to ensure provenance reflects the latest setup/suite
    provenance_file = open(provenance_path, 'w')

    provenance_file.write(
        '**************************************************'
        '*********************\n'
    )
    _write_git_info(provenance_file, 'polaris', polaris_git_info)
    _write_git_info(provenance_file, 'component', component_git_info)
    provenance_file.write(f'command: {calling_command}\n\n')

    # Add readily parsable, PR-friendly metadata discovered at setup time
    _write_meta(provenance_file, 'machine', machine)
    _write_scheduler_metadata(provenance_file, job_options)
    _write_meta(provenance_file, 'compiler', _get_compiler(config))
    _write_meta(provenance_file, 'work directory', work_dir)
    _write_meta(provenance_file, 'build directory', _get_build_dir(config))
    _write_meta(provenance_file, 'build type', _get_build_type(config))
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

    if pixi_list is not None:
        provenance_file.write('pixi list:\n')
        provenance_file.write(f'{pixi_list}\n')

    provenance_file.write(
        '**************************************************'
        '*********************\n'
    )
    provenance_file.close()


def get_summary(config=None):
    """
    Get a short provenance of the Polaris that is running

    This is the provenance in the form something presented to a reader can
    carry --- a generated page, a report --- rather than the file
    :py:func:`polaris.provenance.write` writes, which is exhaustive.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser, optional
        The config options, used to record the version of the component that
        was built, if there is one

    Returns
    -------
    summary : dict
        Labels and the values they had, in the order they are worth reading
    """
    summary = {'polaris version': __version__}

    polaris_git_version = _get_polaris_git_version()
    if polaris_git_version is not None:
        summary['polaris git version'] = polaris_git_version

    if config is not None:
        component_git_version = _get_component_git_version(config)
        if component_git_version is not None:
            summary['component git version'] = component_git_version

    summary['command'] = ' '.join(sys.argv)
    return summary


def _get_polaris_git_version():
    """The git version of the Polaris being run, if it is a git checkout"""
    info = _get_polaris_git_info()
    if info is None:
        return None
    return info['describe']


def _get_polaris_git_info():
    """
    The git version, hash and log of the Polaris being run, if it is a git
    checkout
    """
    if not os.path.exists('.git'):
        return None
    return _get_git_info(os.getcwd())


def _get_component_git_version(config):
    """
    The git version of the source the component was built from, if it can
    be determined
    """
    info = _get_component_git_info(config)
    if info is None:
        return None
    if info['at_setup']:
        return f'{info["describe"]} {_AT_SETUP}'
    return info['describe']


def _get_component_git_info(config):
    """
    The git version, hash and log of the source the component was built
    from, if they can be determined

    Polaris's build scripts record these in the build directory.  A build
    without that record falls back on its source tree as it is now, noted in
    ``at_setup`` because the tree may have moved since the build.
    """
    record = read_source_record(_get_build_dir(config))
    if record is not None and record['describe'] is not None:
        return {
            'describe': record['describe'],
            'hash': record['hash'],
            'log': record['log'],
            'at_setup': False,
        }

    source_dir = _get_component_source_dir(config)
    if source_dir is None:
        return None
    info = _get_git_info(source_dir)
    if info is None:
        return None
    info['at_setup'] = True
    return info


def _get_git_info(source_dir):
    """
    The git version, full hash and last five first-parent commits of a
    source tree, or None if it is not a git tree
    """
    describe = _git_output(
        ['describe', '--tags', '--dirty', '--always'], source_dir
    )
    if describe is None:
        return None
    log = _git_output(
        ['log', '--first-parent', '-n', '5', '--format=%h %s'], source_dir
    )
    return {
        'describe': describe,
        'hash': _git_output(['rev-parse', 'HEAD'], source_dir),
        'log': [] if log is None else log.splitlines(),
        'at_setup': False,
    }


def _get_component_source_dir(config):
    """
    The source directory of the component: the branch if Polaris is building
    the component from it, or else the source the build records
    """
    if _is_building(config):
        return _get_branch_source_dir(config)

    build_dir = _get_build_dir(config)
    for get_source_dir in (get_omega_source_dir, get_mpas_ocean_source_dir):
        source_dir = get_source_dir(build_dir)
        if source_dir is not None:
            if not os.path.isdir(source_dir):
                return None
            return source_dir

    return None


def _is_building(config):
    if not config.has_option('build', 'build'):
        return False
    try:
        return config.getboolean('build', 'build')
    except ValueError:
        return False


def _get_branch_source_dir(config):
    if not config.has_option('build', 'branch'):
        return None
    branch = config.get('build', 'branch')
    if not os.path.isdir(branch):
        return None

    # an uninitialized submodule is an empty directory, and git would walk up
    # to the Polaris checkout it is in
    toplevel = _git_output(['rev-parse', '--show-toplevel'], branch)
    if toplevel is None or not os.path.samefile(toplevel, branch):
        return None
    return branch


def _git_output(args, cwd):
    """The output of a git command run in cwd, or None if it fails"""
    try:
        output = subprocess.check_output(
            ['git'] + args, cwd=cwd, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return output.decode('utf-8').strip('\n')


def _get_pixi_executable():
    for env_var in (
        'MACHE_DEPLOY_ACTIVE_PIXI_EXE',
        'MACHE_DEPLOY_COMPUTE_PIXI_EXE',
        'PIXI',
    ):
        pixi_exe = os.environ.get(env_var)
        if _is_executable_file(pixi_exe):
            return pixi_exe

    pixi_exe = shutil.which('pixi')
    if pixi_exe is not None:
        return pixi_exe

    default_pixi = os.path.join(
        os.path.expanduser('~'), '.pixi', 'bin', 'pixi'
    )
    if _is_executable_file(default_pixi):
        return default_pixi

    return None


def _is_executable_file(path):
    return (
        path is not None and os.path.isfile(path) and os.access(path, os.X_OK)
    )


def _get_compiler(config):
    if config is None:
        return None
    if config.has_option('build', 'compiler'):
        val = config.get('build', 'compiler')
        if val:
            return val
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


def _get_model(config):
    if config is None:
        return None
    if config.has_option('ocean', 'model'):
        val = config.get('ocean', 'model')
        return val or None
    return None


def _get_build_type(config):
    if config is None:
        return None

    build_dir = _get_build_dir(config)
    build_type = detect_omega_build_type(build_dir)
    if build_type is not None:
        return build_type

    if _get_model(config) != 'omega':
        return None

    if not config.has_option('build', 'debug'):
        return None

    try:
        debug = config.getboolean('build', 'debug')
    except ValueError:
        return None

    if debug:
        return 'Debug'
    return 'Release'


def _write_git_info(provenance_file, name, info):
    """
    Write the git version, hash and log of Polaris or the component, with the
    log on indented continuation lines after its label
    """
    if info is None:
        return
    marker = f' {_AT_SETUP}' if info['at_setup'] else ''
    provenance_file.write(
        f'{name} git version: {info["describe"]}{marker}\n\n'
    )
    if info['hash'] is not None:
        provenance_file.write(f'{name} git hash: {info["hash"]}{marker}\n\n')
    if info['log']:
        provenance_file.write(f'{name} git log:{marker}\n')
        for line in info['log']:
            provenance_file.write(f'  {line}\n')
        provenance_file.write('\n')


def _write_meta(provenance_file, label, value):
    """Write a simple 'label: value' line if value is provided."""
    if value is None:
        return
    if isinstance(value, str) and value.strip() == '':
        return
    provenance_file.write(f'{label}: {value}\n\n')


def _write_scheduler_metadata(provenance_file, job_options):
    """Write the scheduler options that the job script actually used.

    Slurm machines have a partition and a QOS, PBS machines have a queue,
    and either may have a constraint, so only the fields that the resolved
    options actually carry are written.
    """
    if job_options is None:
        return
    for label in ('partition', 'qos', 'queue', 'constraint'):
        _write_meta(provenance_file, label, getattr(job_options, label, None))
