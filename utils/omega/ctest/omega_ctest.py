#!/usr/bin/env python3

import argparse
import os
import subprocess

from jinja2 import Template

from polaris.config import PolarisConfigParser
from polaris.io import download
from polaris.job import _clean_up_whitespace, get_slurm_options


def make_build_script(machine, compiler, branch, build_only, mesh_filename,
                      debug, clean, cmake_flags):
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
    update_omega_submodule = (branch == omega_submodule)

    this_dir = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__)))

    template_filename = os.path.join(this_dir, 'build_and_ctest.template')

    with open(template_filename, 'r', encoding='utf-8') as f:
        template = Template(f.read())

    if debug:
        build_type = 'Debug'
    else:
        build_type = 'Release'

    if cmake_flags is None:
        cmake_flags = ''

    script = template.render(update_omega_submodule=update_omega_submodule,
                             polaris_source_dir=polaris_source_dir,
                             omega_base_dir=branch,
                             build_dir=build_dir,
                             machine=machine,
                             compiler=compiler,
                             metis_root=metis_root,
                             parmetis_root=parmetis_root,
                             omega_mesh_filename=mesh_filename,
                             run_ctest=(not build_only),
                             build_type=build_type,
                             clean=clean,
                             cmake_flags=cmake_flags)

    script = _clean_up_whitespace(script)

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


def download_mesh(config):
    """
    Download and symlink a mesh to use for testing.
    """
    base_url = config.get('download', 'server_base_url')
    database_root = config.get('paths', 'database_root')

    filepath = 'ocean/polaris_cache/global_convergence/icos/cosine_bell/' \
               'Icos480/mesh/mesh.230220.nc'

    url = f'{base_url}/{filepath}'
    download_path = os.path.join(database_root, filepath)
    download_target = download(url, download_path, config)
    return download_target


def write_job_script(config, machine, compiler, submit):
    """
    Write a job script for running the build script
    """

    if config.has_option('parallel', 'account'):
        account = config.get('parallel', 'account')
    else:
        account = ''

    nodes = 1

    partition, qos, constraint, _ = get_slurm_options(
        config, machine, nodes)

    wall_time = '0:15:00'

    # see if we can find a debug partition
    if config.has_option('parallel', 'partitions'):
        partition_list = config.getlist('parallel', 'partitions')
        for partition_local in partition_list:
            if 'debug' in partition_local:
                partition = partition_local
                break

    # see if we can find a debug qos
    if config.has_option('parallel', 'qos'):
        qos_list = config.getlist('parallel', 'qos')
        for qos_local in qos_list:
            if 'debug' in qos_local:
                qos = qos_local
                break

    job_name = f'omega_ctest_{machine}_{compiler}'

    this_dir = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__)))
    template_filename = os.path.join(this_dir, 'job_script.template')

    with open(template_filename, 'r', encoding='utf-8') as f:
        template = Template(f.read())

    build_dir = os.path.abspath(
        os.path.join('build_omega', f'build_{machine}_{compiler}'))

    script = template.render(job_name=job_name, account=account,
                             nodes=f'{nodes}', wall_time=wall_time, qos=qos,
                             partition=partition, constraint=constraint,
                             build_dir=build_dir)
    script = _clean_up_whitespace(script)

    build_omega_dir = os.path.abspath('build_omega')
    script_filename = f'job_build_and_ctest_omega_{machine}_{compiler}.sh'
    script_filename = os.path.join(build_omega_dir, script_filename)

    with open(script_filename, 'w', encoding='utf-8') as f:
        f.write(script)

    if submit:
        args = ['sbatch', script_filename]
        print(f'\nRunning:\n   {" ".join(args)}\n')
        subprocess.run(args=args, check=True)


def main():
    """
    Main function for building Omega and performing ctests
    """
    parser = argparse.ArgumentParser(
        description='Check out submodules, build Omega and run ctest')
    parser.add_argument('-o', '--omega_branch', dest='omega_branch',
                        default='e3sm_submodules/Omega',
                        help='The local Omega branch to test.')
    parser.add_argument('-c', '--clean', dest='clean', action='store_true',
                        help='Whether to remove the build directory and start '
                             'fresh')
    parser.add_argument('-s', '--submit', dest='submit', action='store_true',
                        help='Whether to submit a job to run ctests')
    parser.add_argument('-d', '--debug', dest='debug', action='store_true',
                        help='Whether to only build Omega in debug mode')
    parser.add_argument('--cmake_flags', dest='cmake_flags',
                        help='Quoted string with additional cmake flags')

    args = parser.parse_args()

    machine = os.environ['POLARIS_MACHINE']
    compiler = os.environ['POLARIS_COMPILER']

    config = PolarisConfigParser()
    config.add_from_package('polaris', 'default.cfg')
    config.add_from_package('mache.machines', f'{machine}.cfg')
    config.add_from_package('polaris.machines', f'{machine}.cfg')

    submit = args.submit
    branch = args.omega_branch
    debug = args.debug
    clean = args.clean
    cmake_flags = args.cmake_flags

    if 'SLURM_JOB_ID' in os.environ:
        # already on a comptue node so we will just run ctests directly
        submit = False
    else:
        build_only = True

    mesh_filename = download_mesh(config=config)

    script_filename = make_build_script(machine=machine, compiler=compiler,
                                        branch=branch, build_only=build_only,
                                        mesh_filename=mesh_filename,
                                        debug=debug, clean=clean,
                                        cmake_flags=cmake_flags)

    # clear environment variables and start fresh with those from login
    # so spack doesn't get confused by conda
    subprocess.check_call(f'env -i HOME="$HOME" bash -l {script_filename}',
                          shell=True)

    write_job_script(config=config, machine=machine, compiler=compiler,
                     submit=submit)


if __name__ == '__main__':
    main()
