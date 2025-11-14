import importlib.resources
import os
import subprocess

from jinja2 import Template


def build_mpas_ocean(branch, build_dir, clean, debug, make_flags, make_target):
    """
    Build MPAS-Ocean on the current machine.

    Parameters
    ----------
    branch : str
        The relative or absolute path to the base of the MPAS-Ocean branch to
        build.

    build_dir : str
        The directory in which to build MPAS-Ocean.

    clean : bool
        Whether to clean the build directory before building.

    debug : bool
        Whether to build in debug mode.

    make_flags : str
        Additional flags to pass to the build system.

    make_target : str
        The make target to build.
    """
    print('\nBuilding MPAS-Ocean:\n')

    machine = os.environ['POLARIS_MACHINE']
    compiler = os.environ['POLARIS_COMPILER']
    mpilib = os.environ['POLARIS_MPI']

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
    )

    print(f'  machine: {machine}')
    print(f'  compiler: {compiler}')
    print(f'  branch: {branch}')
    print(f'  build directory: {build_dir}')
    print(f'  clean? {clean}')
    print(f'  debug? {debug}')
    print('\n')

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(
        f'env -i HOME="$HOME" bash -l {script_filename}', shell=True
    )

    print(f'MPAS-Ocean builds script written to:\n  {script_filename}\n')


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
):
    """
    Make a shell script for checking out MPAS-Ocean and its submodules and
    building MPAS-Ocean.

    Parameters
    ----------
    machine : str
        The machine to build on.

    compiler : str
        The compiler to build with.

    mpilib : str
        The MPI library to build with.

    branch : str
        The branch of Omega to build.

    build_dir : str
        The directory in which to build Omega.

    debug : bool
        Whether to build in debug mode.

    clean : bool
        Whether to clean the build directory before building.

    make_flags : str
        Additional flags to pass to the build system.

    make_target : str
        The make target to build.

    Returns
    -------
    script_filename : str, optional
        The filename of the generated build script.
    """

    polaris_source_dir = os.environ['POLARIS_BRANCH']

    branch = os.path.abspath(branch)
    e3sm_submodule = os.path.join(
        polaris_source_dir, 'e3sm_submodules/E3SM-Project'
    )
    update_e3sm_submodule = branch == e3sm_submodule

    template_filename = importlib.resources.files('polaris.build').joinpath(
        'build_mpas_ocean.template'
    )

    with open(str(template_filename), 'r', encoding='utf-8') as f:
        template = Template(f.read())

    if make_flags is None:
        make_flags = ''

    mpas_ocean_subdir = os.path.join(branch, 'components', 'mpas-ocean')

    if debug:
        make_flags += ' debug=TRUE'

    load_script = os.environ['LOAD_POLARIS_ENV']

    script = template.render(
        load_script=load_script,
        update_e3sm_submodule=update_e3sm_submodule,
        polaris_source_dir=polaris_source_dir,
        mpas_ocean_subdir=mpas_ocean_subdir,
        build_dir=build_dir,
        make_target=make_target,
        clean=clean,
        make_flags=make_flags,
    )

    build_mpas_ocean_dir = os.path.abspath('build_mpas_ocean')
    os.makedirs(build_mpas_ocean_dir, exist_ok=True)

    script_filename = f'build_mpas_ocean_{machine}_{compiler}_{mpilib}.sh'
    script_filename = os.path.join(build_mpas_ocean_dir, script_filename)

    with open(script_filename, 'w', encoding='utf-8') as f:
        f.write(script)

    return script_filename
