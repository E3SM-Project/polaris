import importlib.resources
import os
import shutil
import subprocess

from jinja2 import Template


def build_omega(
    branch,
    build_dir,
    clean,
    quiet,
    debug,
    cmake_flags,
    account=None,
    log_filename=None,
):
    """
    Build Omega on the current machine.

    Parameters
    ----------
    branch : str
        The relative or absolute path to the base of the Omega branch to build.

    build_dir : str
        The directory in which to build Omega.

    clean : bool
        Whether to clean the build directory before building.

    quiet : bool
        Whether to build quietly (suppress output).

    debug : bool
        Whether to build in debug mode.

    cmake_flags : str
        Additional flags to pass to CMake.

    account : str, optional
        The account to use for the build.

    log_filename : str, optional
        The filename to use for logging build output.
    """
    print('\nBuilding Omega:\n')

    machine = os.environ['POLARIS_MACHINE']
    compiler = os.environ['POLARIS_COMPILER']

    # there if needed
    if clean and os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)

    script_filename = make_build_script(
        machine=machine,
        compiler=compiler,
        branch=branch,
        build_dir=build_dir,
        debug=debug,
        cmake_flags=cmake_flags,
        account=account,
    )

    print(f'  machine: {machine}')
    print(f'  compiler: {compiler}')
    print(f'  branch: {branch}')
    print(f'  build directory: {build_dir}')
    print(f'  clean? {clean}')
    print(f'  debug? {debug}')
    if account is not None:
        print(f'  account: {account}')
    print('\n')

    # remove and/or create build directory first so the log file can be created
    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    command = f'env -i HOME="$HOME" bash -l {script_filename}'
    if log_filename is not None:
        print(f'Logging build to: {log_filename}')
        if quiet:
            command += f' > {log_filename} 2>&1 '
        else:
            command += f' 2>&1 | tee {log_filename}'
    subprocess.check_call(command, shell=True)

    print(f'Omega builds script written to:\n  {script_filename}\n')


def make_build_script(
    machine,
    compiler,
    branch,
    build_dir,
    debug,
    cmake_flags,
    account=None,
):
    """
    Make a shell script for checking out Omega and its submodules and building
    Omega.

    Parameters
    ----------
    machine : str
        The machine to build on.

    compiler : str
        The compiler to build with.

    branch : str
        The branch of Omega to build.

    build_dir : str
        The directory in which to build Omega.

    debug : bool
        Whether to build in debug mode.

    cmake_flags : str
        Additional flags to pass to CMake.

    account : str, optional
        The account to use for the build.

    Returns
    -------
    script_filename : str, optional
        The filename of the generated build script.
    """

    polaris_source_dir = os.environ['POLARIS_BRANCH']
    metis_root = os.environ['METIS_ROOT']
    parmetis_root = os.environ['PARMETIS_ROOT']

    branch = os.path.abspath(branch)
    omega_submodule = os.path.join(polaris_source_dir, 'e3sm_submodules/Omega')
    update_omega_submodule = branch == omega_submodule

    template_filename = importlib.resources.files('polaris.build').joinpath(
        'build_omega.template'
    )

    with open(str(template_filename), 'r', encoding='utf-8') as f:
        template = Template(f.read())

    if debug:
        build_type = 'Debug'
    else:
        build_type = 'Release'

    if cmake_flags is None:
        cmake_flags = ''

    if account is not None:
        cmake_flags = f'{cmake_flags} -DOMEGA_CIME_PROJECT={account}'

    if machine in ['pm-cpu', 'pm-gpu']:
        nersc_host = 'export NERSC_HOST="perlmuter"'
    else:
        nersc_host = ''

    script = template.render(
        update_omega_submodule=update_omega_submodule,
        polaris_source_dir=polaris_source_dir,
        omega_base_dir=branch,
        build_dir=build_dir,
        machine=machine,
        compiler=compiler,
        metis_root=metis_root,
        parmetis_root=parmetis_root,
        build_type=build_type,
        cmake_flags=cmake_flags,
        nersc_host=nersc_host,
    )
    script_filename = f'build_omega_{machine}_{compiler}.sh'
    script_filename = os.path.join(build_dir, script_filename)

    with open(script_filename, 'w', encoding='utf-8') as f:
        f.write(script)

    return script_filename
