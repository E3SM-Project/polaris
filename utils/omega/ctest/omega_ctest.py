#!/usr/bin/env python3

import argparse
import os
import subprocess

from jinja2 import Template

from polaris.config import PolarisConfigParser
from polaris.io import download, update_permissions
from polaris.job import write_job_script


def make_build_script(
    machine,
    compiler,
    branch,
    build_only,
    mesh_filename,
    planar_mesh_filename,
    sphere_mesh_filename,
    debug,
    clean,
    cmake_flags,
    account,
):
    """
    Make a shell script for checking out Omega and its submodules, building
    Omega and its ctests, linking to testing data files, and running ctests.
    """

    polaris_source_dir = os.environ['POLARIS_BRANCH']
    metis_root = os.environ['METIS_ROOT']
    parmetis_root = os.environ['PARMETIS_ROOT']

    build_dir = f'build_{machine}_{compiler}'

    branch = os.path.abspath(branch)
    omega_submodule = os.path.join(polaris_source_dir, 'e3sm_submodules/Omega')
    update_omega_submodule = branch == omega_submodule

    this_dir = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__))
    )

    template_filename = os.path.join(this_dir, 'build_and_ctest.template')

    with open(template_filename, 'r', encoding='utf-8') as f:
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
        omega_mesh_filename=mesh_filename,
        omega_planar_mesh_filename=planar_mesh_filename,
        omega_sphere_mesh_filename=sphere_mesh_filename,
        run_ctest=(not build_only),
        build_type=build_type,
        clean=clean,
        cmake_flags=cmake_flags,
        nersc_host=nersc_host,
    )

    build_omega_dir = os.path.abspath('build_omega')
    os.makedirs(build_omega_dir, exist_ok=True)

    if build_only:
        script_filename = f'build_omega_{machine}_{compiler}.sh'
    else:
        script_filename = f'build_and_ctest_omega_{machine}_{compiler}.sh'

    script_filename = os.path.join(build_omega_dir, script_filename)

    with open(script_filename, 'w', encoding='utf-8') as f:
        f.write(script)

    return script_filename


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


def write_omega_ctest_job_script(config, machine, compiler, debug, nodes=1):
    """
    Write a job script for running Omega CTest using the generalized template.
    """
    build_omega_dir = os.path.abspath('build_omega')
    build_dir = os.path.join(build_omega_dir, f'build_{machine}_{compiler}')

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
    cmake_flags = args.cmake_flags
    account = args.account

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
        mesh_filename=mesh_filename,
        planar_mesh_filename=planar_mesh_filename,
        sphere_mesh_filename=sphere_mesh_filename,
        debug=debug,
        clean=clean,
        cmake_flags=cmake_flags,
        account=account,
    )

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(
        f'env -i HOME="$HOME" bash -l {script_filename}', shell=True
    )

    if account is not None:
        config.set('parallel', 'account', account)

    job_script_filename = write_omega_ctest_job_script(
        config=config,
        machine=machine,
        compiler=compiler,
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
