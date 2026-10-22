import importlib.resources
import os
import shutil
import subprocess
from typing import Optional

from jinja2 import Template

from polaris.build.source_record import read_source_record

# the environment variable that a Polaris load script sets when its Spack
# environment provides Albany (see deploy/load.sh)
ALBANY_LINK_LIBS_VARIABLE = 'POLARIS_ALBANY_LINK_LIBS'

# the record of the source that build_mali.template writes
MALI_SOURCE_RECORD = 'mali_source.txt'


def build_mali(
    branch,
    build_dir,
    clean,
    quiet,
    debug,
    make_flags,
    make_target,
    albany,
    log_filename=None,
):
    """
    Build MALI on the current machine.

    Parameters
    ----------
    branch : str
        The relative or absolute path to the base of the E3SM branch to build
        MALI from.

    build_dir : str
        The directory in which to build MALI.

    clean : bool
        Whether to clean the build directory before building.

    quiet : bool
        Whether to build quietly (suppress output).

    debug : bool
        Whether to build in debug mode.

    make_flags : str
        Additional flags to pass to the build system.

    make_target : str
        The make target to build.

    albany : bool
        Whether to build with Albany, which MALI's first-order velocity solver
        needs.  The environment must provide Albany.

    log_filename : str, optional
        The filename to use for logging build output.
    """
    print('\nBuilding MALI:\n')

    machine = os.environ['POLARIS_MACHINE']
    compiler = os.environ['POLARIS_COMPILER']
    mpilib = os.environ['POLARIS_MPI']

    if albany and not environment_has_albany():
        raise ValueError(
            'A MALI build with Albany was requested, but the Polaris '
            'environment does not provide Albany.  Deploy it with '
            '"./deploy.py --with-albany" or set "albany = False" in the '
            '[build] section of a user config file.'
        )

    # remove and/or create build directory first so the log file can be created
    # there if needed
    if clean and os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)

    script_filename = make_build_script(
        machine=machine,
        compiler=compiler,
        mpilib=mpilib,
        branch=branch,
        build_dir=build_dir,
        debug=debug,
        clean=clean,
        make_flags=make_flags,
        make_target=make_target,
        albany=albany,
    )

    print(f'  machine: {machine}')
    print(f'  compiler: {compiler}')
    print(f'  branch: {branch}')
    print(f'  build directory: {build_dir}')
    print(f'  clean? {clean}')
    print(f'  debug? {debug}')
    print(f'  albany? {albany}')
    print('\n')

    # clear environment variables and start fresh with those from login
    command = f'env -i HOME="$HOME" bash -l {script_filename}'
    if log_filename is not None:
        print(f'Logging build to: {log_filename}')
        if quiet:
            command += f' > {log_filename} 2>&1 '
        else:
            # use pipefail so a build failure is not masked by tee's exit code
            command = f'set -o pipefail; {command} 2>&1 | tee {log_filename}'
    subprocess.check_call(command, shell=True)

    print(f'MALI build script written to:\n  {script_filename}\n')


def make_build_script(
    machine,
    compiler,
    mpilib,
    branch,
    build_dir,
    debug,
    clean,
    make_flags,
    make_target,
    albany,
):
    """
    Make a shell script for building MALI.

    Parameters
    ----------
    machine : str
        The machine to build on.

    compiler : str
        The compiler to build with.

    mpilib : str
        The MPI library to build with.

    branch : str
        The E3SM branch to build MALI from.

    build_dir : str
        The directory in which to build MALI.

    debug : bool
        Whether to build in debug mode.

    clean : bool
        Whether to clean the build directory before building.

    make_flags : str
        Additional flags to pass to the build system.

    make_target : str
        The make target to build.

    albany : bool
        Whether to build with Albany.

    Returns
    -------
    script_filename : str
        The filename of the generated build script.
    """

    polaris_source_dir = os.environ['POLARIS_BRANCH']

    branch = os.path.abspath(branch)
    mali_submodule = os.path.join(
        polaris_source_dir, 'e3sm_submodules/MALI-Dev'
    )
    update_mali_submodule = branch == mali_submodule

    template_filename = importlib.resources.files('polaris.build').joinpath(
        'build_mali.template'
    )

    with open(str(template_filename), 'r', encoding='utf-8') as f:
        template = Template(f.read())

    if make_flags is None:
        make_flags = ''

    mali_subdir = os.path.join(branch, 'components', 'mpas-albany-landice')

    if debug:
        make_flags += ' DEBUG=true'

    load_script = os.environ['POLARIS_LOAD_SCRIPT']

    script = template.render(
        load_script=load_script,
        update_mali_submodule=update_mali_submodule,
        polaris_source_dir=polaris_source_dir,
        e3sm_base_dir=branch,
        mali_subdir=mali_subdir,
        build_dir=build_dir,
        make_target=make_target,
        clean=clean,
        make_flags=make_flags,
        albany=albany,
    )

    script_filename = f'build_mali_{machine}_{compiler}_{mpilib}.sh'
    script_filename = os.path.join(build_dir, script_filename)

    with open(script_filename, 'w', encoding='utf-8') as f:
        f.write(script)

    return script_filename


def environment_has_albany():
    """
    Whether the Polaris environment provides Albany

    Returns
    -------
    has_albany : bool
        Whether the load script found Albany in the Spack environment
    """
    return bool(os.environ.get(ALBANY_LINK_LIBS_VARIABLE))


def get_mali_source_dir(build_dir: Optional[str]) -> Optional[str]:
    """
    Get the source directory that a MALI build was made from.

    Parameters
    ----------
    build_dir : str, optional
        Either a MALI source directory it was built in
        (``components/mpas-albany-landice`` within an E3SM branch) or a build
        directory that Polaris copied the build into.

    Returns
    -------
    Optional[str]
        The source directory of the build, or ``None`` if it cannot be
        determined.
    """
    if not build_dir:
        return None

    build_dir = os.path.abspath(build_dir)
    if os.path.exists(os.path.join(build_dir, 'src', 'Registry.xml')):
        # MALI builds in its source directory
        return build_dir

    if not os.path.exists(os.path.join(build_dir, MALI_SOURCE_RECORD)):
        return None

    record = read_source_record(build_dir)
    if record is None or record['source'] is None:
        return None

    return os.path.join(record['source'], 'components', 'mpas-albany-landice')


def get_mali_build_albany(build_dir: Optional[str]) -> Optional[bool]:
    """
    Get whether a MALI build that Polaris made has Albany.

    Parameters
    ----------
    build_dir : str, optional
        A build directory that Polaris copied a MALI build into

    Returns
    -------
    Optional[bool]
        Whether the build has Albany, or ``None`` if the build directory has
        no record of it
    """
    if not build_dir:
        return None

    if not os.path.exists(os.path.join(build_dir, MALI_SOURCE_RECORD)):
        return None

    record = read_source_record(build_dir)
    if record is None:
        return None
    return record['albany']
