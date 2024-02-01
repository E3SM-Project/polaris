#!/usr/bin/env python3

import argparse
import os
import shutil
from configparser import ConfigParser

from shared import check_call, get_logger

# build targets from
# https://mpas-dev.github.io/polaris/latest/developers_guide/machines/index.html#supported-machines
all_build_targets = {
    'anvil': {
        ('intel', 'impi'): 'intel-mpi',
        ('intel', 'openmpi'): 'ifort',
        ('gnu', 'openmpi'): 'gfortran'},
    'chicoma-cpu': {
        ('gnu', 'mpich'): 'gnu-cray'},
    'chrysalis': {
        ('intel', 'impi'): 'intel-mpi',
        ('intel', 'openmpi'): 'ifort',
        ('gnu', 'openmpi'): 'gfortran'},
    'compy': {
        ('intel', 'impi'): 'intel-mpi'},
    'frontier': {
        ('gnu', 'mpich'): 'gnu-cray',
        ('crayclang', 'mpich'): 'cray-cray'},
    'pm-cpu': {
        ('gnu', 'mpich'): 'gnu-cray',
        ('intel', 'mpich'): 'intel-cray'},
    'conda-linux': {
        ('gfortran', 'mpich'): 'gfortran',
        ('gfortran', 'openmpi'): 'gfortran'},
    'conda-osx': {
        ('gfortran-clang', 'mpich'): 'gfortran-clang',
        ('gfortran-clang', 'openmpi'): 'gfortran-clang'}
}


def setup_matrix(config_filename, submit):
    """
    Build and set up (and optionally submit jobs for) a matrix of MPAS builds

    Parameters
    ----------
    config_filename : str
        The name of the config file containing config options to use for both
        the matrix and the test case(s)

    submit : bool
        Whether to submit each suite or set of tasks once it has been built
        and set up
    """

    config = ConfigParser()
    config.read(config_filename)

    matrix_filename = 'conda/logs/matrix.log'
    if not os.path.exists(matrix_filename):
        raise OSError(f'{matrix_filename} not found.\n Try running '
                      f'./configure_polaris_env.py to generate it.')
    with open(matrix_filename, 'r') as f:
        machine = f.readline().strip()
        lines = f.readlines()
        compilers = list()
        mpis = list()
        for line in lines:
            compiler, mpi = line.split(',')
            compilers.append(compiler.strip())
            mpis.append(mpi.strip())

    if machine not in all_build_targets:
        raise ValueError(f'build targets not known for machine: {machine}')
    build_targets = all_build_targets[machine]

    env_name = config.get('matrix', 'env_name')

    openmp_str = config.get('matrix', 'openmp')
    openmp = [value.strip().lower() == 'true' for value in
              openmp_str.replace(',', '').split(' ')]
    debug_str = config.get('matrix', 'debug')
    debug = [value.strip().lower() == 'true' for value in
             debug_str.replace(',', '').split(' ')]
    other_build_flags = config.get('matrix', 'other_build_flags')

    mpas_path = config.get('matrix', 'mpas_path')
    mpas_path = os.path.abspath(mpas_path)

    setup_command = config.get('matrix', 'setup_command')
    work_base = config.get('matrix', 'work_base')
    work_base = os.path.abspath(work_base)
    baseline_base = config.get('matrix', 'baseline_base')
    if baseline_base != '':
        baseline_base = os.path.abspath(baseline_base)

    for compiler, mpi in zip(compilers, mpis):
        if (compiler, mpi) not in build_targets:
            raise ValueError(f'Unsupported compiler {compiler} and MPI {mpi}')
        target = build_targets[(compiler, mpi)]

        script_name = get_load_script_name(machine, compiler, mpi, env_name)
        script_name = os.path.abspath(script_name)

        for use_openmp in openmp:
            for use_debug in debug:
                suffix = f'{machine}_{compiler}_{mpi}'
                make_command = \
                    f'make clean && make {target} {other_build_flags}'
                if use_openmp:
                    make_command = f'{make_command} OPENMP=true'
                else:
                    suffix = f"{suffix}_noopenmp"
                    make_command = f'{make_command} OPENMP=false'
                if use_debug:
                    suffix = f'{suffix}_debug'
                    make_command = f'{make_command} DEBUG=true'
                else:
                    make_command = f'{make_command} DEBUG=false'
                mpas_model = build_mpas(
                    script_name, mpas_path, make_command, suffix)

                polaris_setup(script_name, setup_command, mpas_path,
                              mpas_model, work_base, baseline_base, config,
                              env_name, suffix, submit)


def get_load_script_name(machine, compiler, mpi, env_name):
    """
    Get the load script for this configuration

    Parameters
    ----------
    machine : str
        The name of the current machine

    compiler : str
        The name of the compiler

    mpi : str
        the MPI library

    env_name : str
        The name of the conda environment to run polaris from

    Returns
    -------
    script_name : str
        The name of the load script to source to get the appropriate polaris
        environment


    """
    if machine.startswith('conda'):
        script_name = f'load_{env_name}_{mpi}.sh'
    else:
        script_name = f'load_{env_name}_{machine}_{compiler}_{mpi}.sh'
    return script_name


def build_mpas(script_name, mpas_path, make_command, suffix):
    """
    Build the MPAS component


    Parameters
    ----------
    script_name : str
        The name of the load script to source to get the appropriate polaris
        environment

    mpas_path : str
        The path to the MPAS component to run

    make_command : str
        The make command to run to build the MPAS component

    suffix : str
        A suffix related to the machine, compilers, MPI libraries, etc.

    Returns
    -------
    new_mpas_model : str
        The new name for the MPAS executable with a suffix for the build

    """

    mpas_subdir = os.path.basename(mpas_path)
    if mpas_subdir == 'mpas-ocean':
        mpas_model = 'ocean_model'
    elif mpas_subdir == 'mpas-albany-landice':
        mpas_model = 'landice_model'
    else:
        raise ValueError(f'Unexpected model subdirectory {mpas_subdir}')

    cwd = os.getcwd()
    print(f'Changing directory to:\n{mpas_path}\n')
    os.chdir(mpas_path)
    args = f'source {script_name} && {make_command}'

    log_filename = f'build_{suffix}.log'
    print_command = '\n'.join(args.split(' && '))
    print(f'\nRunning:\n{print_command}\n')
    logger = get_logger(name=__name__, log_filename=log_filename)
    check_call(args, logger=logger)

    new_mpas_model = f'{mpas_model}_{suffix}'
    shutil.move(mpas_model, new_mpas_model)

    print(f'Changing directory to:\n{cwd}\n')
    os.chdir(cwd)

    return new_mpas_model


def polaris_setup(script_name, setup_command, mpas_path, mpas_model, work_base,
                  baseline_base, config, env_name, suffix, submit):
    """
    Set up the polaris suite or test case(s)

    Parameters
    ----------
    script_name : str
        The name of the load script to source to get the appropriate polaris
        environment

    setup_command : str
        The command for setting up the polaris test case or suite

    mpas_path : str
        The path to the MPAS component to run

    mpas_model : str
        The name of the MPAS executable within the ``mpas_path``

    work_base : str
        The base work directory for the matrix.  The work directory used for
        the suite or test case(s) is a subdirectory ``suffix`` within this
        directory.

    baseline_base : str
        The base work directory for a baseline matrix to compare to (or an
        empty string for no baseline)

    config : configparser.ConfigParser
        Config options for both the matrix and the test case(s)

    env_name : str
        The name of the conda environment to run polaris from

    suffix : str
        A suffix related to the machine, compilers, MPI libraries, etc.

    submit : bool
        Whether to submit each suite or set of tasks once it has been built
        and set up
    """

    if not config.has_section('paths'):
        config.add_section('paths')
    config.set('paths', 'mpas_model', mpas_path)
    if not config.has_section('executables'):
        config.add_section('executables')
    config.set('executables', 'model',
               f'${{paths:mpas_model}}/{mpas_model}')

    new_config_filename = f'{env_name}_{suffix}.cfg'
    with open(new_config_filename, 'w') as f:
        config.write(f)

    work_dir = f'{work_base}/{suffix}'

    args = f'export NO_POLARIS_REINSTALL=true;' \
           f'source {script_name} && ' \
           f'{setup_command} ' \
           f'-p {mpas_path} ' \
           f'-w {work_dir} ' \
           f'-f {new_config_filename}'

    if baseline_base != '':
        args = f'{args} -b {baseline_base}/{suffix}'

    log_filename = f'setup_{env_name}_{suffix}.log'
    print_command = '\n'.join(args.split(' && '))
    print(f'\nRunning:\n{print_command}\n')
    logger = get_logger(name=__name__, log_filename=log_filename)
    check_call(args, logger=logger)

    if submit:
        suite = None
        if setup_command.startswith('polaris suite'):
            parts = setup_command.split()
            index = parts.index('-t')
            if index == -1:
                index = parts.index('--test_suite')

            if index != -1 and len(parts) > index + 1:
                suite = parts[index + 1]
        elif setup_command.startswith('polaris setup'):
            suite = 'custom'

        if suite is not None:
            job_script = f'job_script.{suite}.sh'
            if not os.path.exists(os.path.join(work_dir, job_script)):
                raise OSError(f'Could not find job script {job_script} for '
                              f'suite {suite}')
            args = f'cd {work_dir} && sbatch {job_script}'
            print_command = '\n'.join(args.split(' && '))
            print(f'\nRunning:\n{print_command}\n')
            check_call(args)


def main():
    parser = argparse.ArgumentParser(
        description='Build MPAS and set up polaris with a matrix of build '
                    'configs')
    parser.add_argument("-f", "--config_file", dest="config_file",
                        required=True,
                        help="Configuration file with matrix build options.",
                        metavar="FILE")
    parser.add_argument("--submit", dest="submit", action='store_true',
                        help="Whether to submit the job scripts for each test "
                             "once setup is complete.")

    args = parser.parse_args()
    setup_matrix(args.config_file, args.submit)


if __name__ == '__main__':
    main()
