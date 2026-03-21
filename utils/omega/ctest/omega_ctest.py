#!/usr/bin/env python3

import argparse
import os
import shutil
import subprocess

from jinja2 import Template

from polaris.build.omega import make_build_script as make_base_build_script
from polaris.config import PolarisConfigParser
from polaris.io import download, update_permissions
from polaris.job import write_job_script


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
):
    """
    Make a shell script using the standard Omega builder, then append
    CTest-specific commands (link meshes and optionally run ctests).
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

        base_script = make_base_build_script(
            machine=machine,
            compiler=compiler,
            branch=branch,
            build_dir=build_dir,
            debug=debug,
            cmake_flags=cmake_flags,
            account=account,
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
        extra = f'{extra}./omega_ctest.sh\n'

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
        'ocean.QU.240km.151209.nc',
        'PlanarPeriodic48x48.nc',
        'cosine_bell_icos480_initial_state.230220.nc',
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
        update_permissions([database_path], group)

    return download_targets


def write_omega_ctest_job_script(
    config, machine, compiler, build_dir, debug, nodes=1
):
    """
    Write a job script for running Omega CTest using the generalized template.
    """
    build_omega_dir = os.path.abspath('build_omega')
    os.makedirs(build_omega_dir, exist_ok=True)

    build_type = 'Debug' if debug else 'Release'

    this_dir = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__))
    )
    template_filename = os.path.join(this_dir, 'run_command.template')

    with open(template_filename, 'r', encoding='utf-8') as f:
        template = Template(f.read())

    run_command = template.render(
        build_dir=build_dir,
        machine=machine,
        compiler=compiler,
        build_type=build_type,
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
    )

    # clear environment variables and start fresh with those from login
    subprocess.check_call(
        f'env -i HOME="$HOME" bash -l "{script_filename}"', shell=True
    )

    if account is not None:
        config.set('parallel', 'account', account)

    job_script_filename = write_omega_ctest_job_script(
        config=config,
        machine=machine,
        compiler=compiler,
        build_dir=build_dir,
        debug=debug,
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


if __name__ == '__main__':
    main()
