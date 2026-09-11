#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess
from dataclasses import dataclass

from jinja2 import Template
from mache.permissions import update_permissions

from polaris.build.omega import make_build_script as make_base_build_script
from polaris.config import PolarisConfigParser
from polaris.io import download
from polaris.job import write_job_script

# the CDash project that Omega results are submitted to, and its nightly start
# time as configured on my.cdash.org
CDASH_SUBMIT_URL = 'https://my.cdash.org/submit.php?project=omega'
CDASH_NIGHTLY_START_TIME = '01:00:00 UTC'

THIS_DIR = os.path.realpath(os.path.dirname(__file__))
CTEST_DASHBOARD_SCRIPT = os.path.join(THIS_DIR, 'ctest_dashboard.cmake')


@dataclass
class DashboardOptions:
    """
    Options for recording a build and its tests for CDash.

    Attributes
    ----------
    site : str
        The site name shown on CDash, typically the machine

    build_name : str
        The build name shown on CDash

    model : str
        The CTest model, one of ``Nightly``, ``Experimental`` or
        ``Continuous``

    submit_url : str
        The CDash submit URL

    submit : bool
        Whether to submit the results at the end of the test stage
    """

    site: str
    build_name: str
    model: str
    submit_url: str
    submit: bool


def make_build_script(
    machine,
    compiler,
    branch,
    build_only,
    build_dir,
    mesh_filename,
    planar_mesh_filename,
    sphere_mesh_filename,
    debug,
    clean,
    cmake_flags,
    account,
    dashboard=None,
):
    """
    Make a shell script using the standard Omega builder, then append
    CTest-specific commands (link meshes and optionally run ctests).

    With ``dashboard`` set, the build goes through ``ctest_build()`` so that
    CTest records it under ``Testing/<tag>/`` for CDash.
    """

    if branch is None:
        validate_omega_build_dir(build_dir)
        if clean:
            raise ValueError(
                'Cannot use --clean with --component_path because the '
                'utility is using an existing build.'
            )

        appended_script = os.path.join(
            build_dir, f'prepare_ctest_omega_{machine}_{compiler}.sh'
        )
        content = f'#!/bin/bash\nset -e\n\ncd "{build_dir}"\n'
    else:
        # Use the standard builder to generate the build script
        build_omega_dir = os.path.abspath('build_omega')
        os.makedirs(build_omega_dir, exist_ok=True)

        # there if needed
        if clean and os.path.exists(build_dir):
            shutil.rmtree(build_dir)
        os.makedirs(build_dir, exist_ok=True)

        if dashboard is None:
            build_command = None
        else:
            build_command = dashboard_ctest_command(
                stage='build',
                branch=branch,
                build_dir=build_dir,
                dashboard=dashboard,
            )

        base_script = make_base_build_script(
            machine=machine,
            compiler=compiler,
            branch=branch,
            build_dir=build_dir,
            debug=debug,
            cmake_flags=cmake_flags,
            account=account,
            build_command=build_command,
        )

        if build_only:
            appended_script = base_script
        else:
            appended_script = os.path.join(
                build_dir, f'build_and_ctest_omega_{machine}_{compiler}.sh'
            )

        with open(base_script, 'r', encoding='utf-8') as f:
            content = f.read()

    # we need to symlink the 3 meshes regardless of whether we run CTests now
    # or later
    extra = (
        f'\n\nln -sfn "{mesh_filename}" test/OmegaMesh.nc\n'
        f'ln -sfn "{planar_mesh_filename}" test/OmegaPlanarMesh.nc\n'
        f'ln -sfn "{sphere_mesh_filename}" test/OmegaSphereMesh.nc\n'
    )

    if not build_only:
        ctest_command = test_command(
            branch=branch, build_dir=build_dir, dashboard=dashboard
        )
        extra = f'{extra}{ctest_command}\n'

    with open(appended_script, 'w', encoding='utf-8') as f:
        f.write(content)
        f.write(extra)

    os.chmod(appended_script, 0o755)

    return appended_script


def validate_omega_build_dir(build_dir):
    """
    Validate that ``build_dir`` appears to be an existing Omega build.
    """
    required_paths = [
        'configs/Default.yml',
        'src/omega.exe',
        'omega_ctest.sh',
        'test',
    ]

    missing = []
    for required_path in required_paths:
        if not os.path.exists(os.path.join(build_dir, required_path)):
            missing.append(required_path)

    if missing:
        missing_str = ', '.join(missing)
        raise FileNotFoundError(
            f'Existing Omega build path appears invalid: {build_dir}. '
            f'Missing: {missing_str}'
        )


def download_meshes(config):
    """
    Download and symlink a mesh to use for testing.
    """
    database_root = config.get('paths', 'database_root')

    base_url = 'https://web.lcrc.anl.gov/public/e3sm/polaris/'

    files = [
        'ocean.QU.240km.omega_vars.260807.nc',
        'PlanarPeriodic48x48.omega_vars.260825.nc',
        'cosine_bell_icos480.omega_vars.260807.nc',
    ]

    database_path = 'ocean/omega_ctest'

    download_targets = []
    for filename in files:
        download_path = os.path.join(database_root, database_path, filename)
        url = f'{base_url}/{database_path}/{filename}'
        download_target = download(url, download_path, config)
        download_targets.append(download_target)

    if config.has_option('e3sm_unified', 'group'):
        database_path = os.path.join(database_root, database_path)
        group = config.get('e3sm_unified', 'group')
        update_permissions([database_path], group, group_writable=True)

    return download_targets


def dashboard_ctest_command(stage, branch, build_dir, dashboard):
    """
    The ``ctest -S`` command that runs one stage of the dashboard script.

    Parameters
    ----------
    stage : {'build', 'test', 'submit'}
        The stage to run

    branch : str or None
        The Omega branch, or ``None`` when reusing an existing build, in
        which case the source directory is read from the CMake cache

    build_dir : str
        The Omega build directory

    dashboard : DashboardOptions
        The CDash options

    Returns
    -------
    command : str
        The command, to run from ``build_dir``
    """
    if branch is None:
        source_dir = _read_cmake_cache_value(build_dir, 'CMAKE_HOME_DIRECTORY')
    else:
        source_dir = os.path.join(os.path.abspath(branch), 'components/omega')

    parts = [
        'ctest',
        '-S',
        f'"{CTEST_DASHBOARD_SCRIPT}"',
        f'-DSTAGE={stage}',
        f'-DCTEST_SOURCE_DIRECTORY="{source_dir}"',
        f'-DCTEST_BINARY_DIRECTORY="{build_dir}"',
        f'-DCTEST_SITE="{dashboard.site}"',
        f'-DCTEST_BUILD_NAME="{dashboard.build_name}"',
        f'-DCTEST_MODEL={dashboard.model}',
        f'-DCTEST_NIGHTLY_START_TIME="{CDASH_NIGHTLY_START_TIME}"',
        f'-DCTEST_SUBMIT_URL="{dashboard.submit_url}"',
    ]
    if stage == 'build':
        parts.append('-DCTEST_BUILD_COMMAND=./omega_build.sh')
    if stage == 'test':
        submit = 'ON' if dashboard.submit else 'OFF'
        parts.append(f'-DSUBMIT={submit}')

    return ' \\\n   '.join(parts)


def test_command(branch, build_dir, dashboard):
    """
    The command that runs the CTests from ``build_dir``: Omega's own
    ``omega_ctest.sh``, or the dashboard script's test stage.
    """
    if dashboard is None:
        return './omega_ctest.sh'

    ctest_command = dashboard_ctest_command(
        stage='test', branch=branch, build_dir=build_dir, dashboard=dashboard
    )
    # omega_ctest.sh sources the environment and clears old logs before
    # running ctest; the dashboard stage has to do the same
    return f'source ./omega_env.sh\nrm -f test/logs/*.log\n{ctest_command}'


def write_omega_ctest_job_script(
    config, machine, compiler, build_dir, debug, ctest_command, nodes=1
):
    """
    Write a job script for running Omega CTest using the generalized template.
    """
    build_omega_dir = os.path.abspath('build_omega')
    os.makedirs(build_omega_dir, exist_ok=True)

    build_type = 'Debug' if debug else 'Release'

    template_filename = os.path.join(THIS_DIR, 'run_command.template')

    with open(template_filename, 'r', encoding='utf-8') as f:
        template = Template(f.read())

    run_command = template.render(
        build_dir=build_dir,
        machine=machine,
        compiler=compiler,
        build_type=build_type,
        ctest_command=ctest_command,
    )

    job_script_filename = f'job_build_and_ctest_omega_{machine}_{compiler}.sh'
    job_script_filename = os.path.join(build_omega_dir, job_script_filename)

    write_job_script(
        config=config,
        machine=machine,
        nodes=nodes,
        work_dir=build_dir,
        script_filename=job_script_filename,
        run_command=run_command,
    )
    return job_script_filename


def main():
    """
    Main function for building Omega and performing ctests
    """
    parser = argparse.ArgumentParser(
        description='Check out submodules, build Omega and run ctest'
    )
    parser.add_argument(
        '-o',
        '--omega_branch',
        dest='omega_branch',
        default='e3sm_submodules/Omega',
        help='The local Omega branch to test.',
    )
    parser.add_argument(
        '-c',
        '--clean',
        dest='clean',
        action='store_true',
        help='Whether to remove the build directory and start fresh',
    )
    parser.add_argument(
        '-s',
        '--submit',
        dest='submit',
        action='store_true',
        help='Whether to submit a job to run ctests',
    )
    parser.add_argument(
        '-d',
        '--debug',
        dest='debug',
        action='store_true',
        help='Whether to only build Omega in debug mode',
    )
    parser.add_argument(
        '-p',
        '--component_path',
        dest='component_path',
        help='Path to an existing Omega build directory to use for CTests.',
    )
    parser.add_argument(
        '--cmake_flags',
        dest='cmake_flags',
        help='Quoted string with additional cmake flags',
    )
    parser.add_argument(
        '--account', dest='account', help='slurm account to submit the job to'
    )
    parser.add_argument(
        '--build_only',
        dest='build_only',
        action='store_true',
        help='Build Omega but do not write or submit a job to run ctests',
    )
    parser.add_argument(
        '--dashboard',
        dest='dashboard',
        action='store_true',
        help='Record the build and tests with CTest for CDash, under '
        'Testing/<tag>/ in the build directory',
    )
    parser.add_argument(
        '--cdash_site',
        dest='cdash_site',
        help='The site name shown on CDash (default: the machine)',
    )
    parser.add_argument(
        '--cdash_build_name',
        dest='cdash_build_name',
        help='The build name shown on CDash (default: '
        'omega_ctest_<machine>_<compiler>)',
    )
    parser.add_argument(
        '--cdash_model',
        dest='cdash_model',
        default='Experimental',
        choices=['Nightly', 'Experimental', 'Continuous'],
        help='The CTest model (default: Experimental)',
    )
    parser.add_argument(
        '--cdash_url',
        dest='cdash_url',
        default=CDASH_SUBMIT_URL,
        help=f'The CDash submit URL (default: {CDASH_SUBMIT_URL})',
    )
    parser.add_argument(
        '--cdash_submit',
        dest='cdash_submit',
        action='store_true',
        help='Submit the results to CDash when the ctests finish (implies '
        '--dashboard)',
    )

    args = parser.parse_args()

    machine = os.environ['POLARIS_MACHINE']
    compiler = os.environ['POLARIS_COMPILER']

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('mache.machines', f'{machine}.cfg')
    config.add_from_package('polaris.machines', f'{machine}.cfg')

    job_name = f'omega_ctest_{machine}_{compiler}'
    config.set('job', 'job_name', job_name)

    submit = args.submit
    branch = args.omega_branch
    debug = args.debug
    clean = args.clean
    component_path = args.component_path
    cmake_flags = args.cmake_flags
    account = args.account

    if args.dashboard or args.cdash_submit:
        site = args.cdash_site
        if site is None:
            site = machine
        build_name = args.cdash_build_name
        if build_name is None:
            build_name = job_name
        dashboard = DashboardOptions(
            site=site,
            build_name=build_name,
            model=args.cdash_model,
            submit_url=args.cdash_url,
            submit=args.cdash_submit,
        )
    else:
        dashboard = None

    if component_path is not None:
        branch = None
        build_dir = os.path.abspath(component_path)
    else:
        build_omega_dir = os.path.abspath('build_omega')
        build_dir = os.path.join(
            build_omega_dir, f'build_{machine}_{compiler}'
        )

    if 'SLURM_JOB_ID' in os.environ:
        # already on a comptue node so we will just run ctests directly
        submit = False
        build_only = False
    else:
        build_only = True

    mesh_filename, planar_mesh_filename, sphere_mesh_filename = (
        download_meshes(config=config)
    )

    script_filename = make_build_script(
        machine=machine,
        compiler=compiler,
        branch=branch,
        build_only=build_only,
        build_dir=build_dir,
        mesh_filename=mesh_filename,
        planar_mesh_filename=planar_mesh_filename,
        sphere_mesh_filename=sphere_mesh_filename,
        debug=debug,
        clean=clean,
        cmake_flags=cmake_flags,
        account=account,
        dashboard=dashboard,
    )

    # clear environment variables and start fresh with those from login
    subprocess.check_call(
        f'env -i HOME="$HOME" bash -l "{script_filename}"', shell=True
    )

    if args.build_only:
        return

    if account is not None:
        config.set('parallel', 'account', account)

    ctest_command = test_command(
        branch=branch, build_dir=build_dir, dashboard=dashboard
    )

    job_script_filename = write_omega_ctest_job_script(
        config=config,
        machine=machine,
        compiler=compiler,
        build_dir=build_dir,
        debug=debug,
        ctest_command=ctest_command,
    )

    if submit:
        system = config.get('parallel', 'system')
        if system == 'slurm':
            submit = 'sbatch'
        elif system == 'pbs':
            submit = 'qsub'
        else:
            raise ValueError(f'Unsupported parallel system: {system}')
        cmd = [submit, job_script_filename]
        print(f'\nRunning:\n   {" ".join(cmd)}\n')
        subprocess.run(args=cmd, check=True)


def _read_cmake_cache_value(build_dir, key):
    """
    Read one value from ``CMakeCache.txt`` in ``build_dir``.
    """
    cache_path = os.path.join(build_dir, 'CMakeCache.txt')
    with open(cache_path, 'r', encoding='utf-8') as cache_file:
        for line in cache_file:
            name_and_type, separator, value = line.strip().partition('=')
            if separator == '':
                continue
            name, _, _ = name_and_type.partition(':')
            if name == key:
                return value.strip()
    raise KeyError(f'{key} not found in {cache_path}')


if __name__ == '__main__':
    main()
