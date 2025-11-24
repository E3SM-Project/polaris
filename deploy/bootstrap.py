#!/usr/bin/env python3

import glob
import grp
import importlib.resources
import os
import platform
import shutil
import socket
import stat
import subprocess
import time
from configparser import ConfigParser, ExtendedInterpolation
from typing import Dict

import progressbar
from jinja2 import Template
from mache import MachineInfo
from mache import discover_machine as mache_discover_machine
from mache.spack import get_spack_script, make_spack_env
from packaging import version
from shared import (
    check_call,
    get_conda_base,
    get_logger,
    install_miniforge,
    parse_args,
)


def main():  # noqa: C901
    """
    Entry point for bootstrap
    """

    args = parse_args(bootstrap=True)
    options = vars(args)

    if options['verbose']:
        options['logger'] = None
    else:
        options['logger'] = get_logger(
            log_filename='deploy_tmp/logs/bootstrap.log', name=__name__
        )

    source_path = os.getcwd()
    options['source_path'] = source_path
    options['conda_template_path'] = f'{source_path}/deploy'
    options['spack_template_path'] = f'{source_path}/deploy/spack'

    polaris_version = _get_version()
    options['polaris_version'] = polaris_version

    options['local_mache'] = (
        options['mache_fork'] is not None
        and options['mache_branch'] is not None
    )

    machine = None
    if not options['conda_env_only']:
        if options['machine'] is None:
            machine = _discover_machine()
        else:
            machine = options['machine']

    options['known_machine'] = machine is not None

    if machine is None and not options['conda_env_only']:
        if platform.system() == 'Linux':
            machine = 'conda-linux'
        elif platform.system() == 'Darwin':
            machine = 'conda-osx'

    options['machine'] = machine
    options['config'] = _get_config(options['config_file'], machine)

    env_type = options['config'].get('deploy', 'env_type')
    if env_type not in ['dev', 'test_release', 'release']:
        raise ValueError(f'Unexpected env_type: {env_type}')
    shared = env_type != 'dev'
    conda_base = get_conda_base(
        options['conda_base'], options['config'], shared=shared, warn=False
    )
    options['env_type'] = env_type
    conda_base = os.path.abspath(conda_base)
    options['conda_base'] = conda_base

    source_activation_scripts = f'source {conda_base}/etc/profile.d/conda.sh'

    activate_base = f'{source_activation_scripts} && conda activate'

    if machine is None:
        compilers = [None]
        mpis = ['nompi']
    else:
        _get_compilers_mpis(options)

        compilers = options['compilers']
        mpis = options['mpis']

        # write out a log file for use by matrix builds
        with open('deploy_tmp/logs/matrix.log', 'w') as f:
            f.write(f'{machine}\n')
            for compiler, mpi in zip(compilers, mpis, strict=False):
                f.write(f'{compiler}, {mpi}\n')

        print(
            'Configuring environment(s) for the following compilers and MPI '
            'libraries:'
        )
        for compiler, mpi in zip(compilers, mpis, strict=False):
            print(f'  {compiler}, {mpi}')
        print('')

    previous_conda_env = None

    permissions_dirs = []
    activ_path = None

    soft_spack_view = _build_spack_soft_env(options)

    for compiler, mpi in zip(compilers, mpis, strict=False):
        _get_env_setup(options, compiler, mpi)

        build_dir = f'deploy_tmp/build{options["activ_suffix"]}'

        _safe_rmtree(build_dir)
        os.makedirs(name=build_dir, exist_ok=True)

        os.chdir(build_dir)

        if options['spack_base'] is not None:
            spack_base = options['spack_base']
        elif options['known_machine'] and compiler is not None:
            _get_spack_base(options)
        else:
            spack_base = None

        if spack_base is not None and options['update_spack']:
            # even if this is not a release, we need to update permissions on
            # shared system libraries
            permissions_dirs.append(spack_base)

        conda_env_name = options['conda_env_name']
        if previous_conda_env != conda_env_name:
            _build_conda_env(options, activate_base)

            if options['local_mache']:
                print('Install local mache\n')
                commands = (
                    f'source {conda_base}/etc/profile.d/conda.sh && '
                    f'conda activate {conda_env_name} && '
                    f'cd ../build_mache/mache && '
                    f'conda install -y --file spec-file.txt && '
                    f'python -m pip install --no-deps --no-build-isolation .'
                )
                check_call(commands, logger=options['logger'])

            previous_conda_env = conda_env_name

            if env_type != 'dev':
                permissions_dirs.append(conda_base)

        spack_script = ''
        if compiler is not None:
            env_vars = _get_env_vars(options['machine'], compiler, mpi)
            if spack_base is not None:
                spack_script, env_vars = _build_spack_libs_env(
                    options, compiler, mpi, env_vars
                )

                spack_script = (
                    f'echo Loading Spack environment...\n'
                    f'{spack_script}\n'
                    f'echo Done.\n'
                    f'echo\n'
                )
            else:
                conda_env_path = options['conda_env_path']
                env_vars = (
                    f'{env_vars}'
                    f'export PIO={conda_env_path}\n'
                    f'export OPENMP_INCLUDE=-I"{conda_env_path}/include"\n'
                )

            if soft_spack_view is not None:
                env_vars = (
                    f'{env_vars}export PATH="{soft_spack_view}/bin:$PATH"\n'
                )
            elif options['known_machine']:
                raise ValueError(
                    'A software compiler or a spack base was not '
                    'defined so required software was not '
                    'installed with spack.'
                )

        else:
            env_vars = ''

        if env_type == 'dev':
            if conda_env_name is not None:
                prefix = f'load_{conda_env_name}'
            else:
                prefix = f'load_dev_polaris_{polaris_version}'
        elif env_type == 'test_release':
            prefix = f'test_polaris_{polaris_version}'
        else:
            prefix = f'load_polaris_{polaris_version}'

        script_filename = _write_load_polaris(
            options, prefix, spack_script, env_vars
        )

        if options['check']:
            _check_env(options, script_filename, conda_env_name)

        if env_type == 'release' and not (
            options['with_albany'] or options['with_petsc']
        ):
            activ_path = options['activ_path']
            # make a symlink to the activation script
            link = os.path.join(
                activ_path, f'load_latest_polaris_{compiler}_{mpi}.sh'
            )
            check_call(f'ln -sfn {script_filename} {link}')

            default_compiler = options['config'].get('deploy', 'compiler')
            default_mpi = options['config'].get(
                'deploy', f'mpi_{default_compiler}'
            )
            if compiler == default_compiler and mpi == default_mpi:
                # make a default symlink to the activation script
                link = os.path.join(activ_path, 'load_latest_polaris.sh')
                check_call(f'ln -sfn {script_filename} {link}')
        os.chdir(options['source_path'])

    commands = f'{activate_base} && conda clean -y -p -t'
    check_call(commands, logger=options['logger'])

    if options['update_spack'] or env_type != 'dev':
        # we need to update permissions on shared stuff
        _update_permissions(options, permissions_dirs)


def _get_spack_base(options):
    """
    Get the absolute path to the spack base files
    """

    config = options['config']
    spack_base = options['spack_base']
    if spack_base is None:
        if config.has_option('deploy', 'spack'):
            spack_base = config.get('deploy', 'spack')
        else:
            raise ValueError(
                'No spack base provided with --spack and none is '
                'provided in a config file.'
            )
    # handle "~" in the path
    options['spack_base'] = os.path.abspath(os.path.expanduser(spack_base))


def _get_config(config_file, machine):
    """
    Read in the options from the config file and return the config object
    """

    # we can't load polaris so we find the config files
    here = os.path.abspath(os.path.dirname(__file__))
    default_config = os.path.join(here, 'default.cfg')
    config = ConfigParser(interpolation=ExtendedInterpolation())
    config.read(default_config)

    if machine is not None:
        machine_config = str(
            importlib.resources.files('mache.machines') / f'{machine}.cfg'
        )
        # it's okay if a given machine isn't part of mache
        if os.path.exists(machine_config):
            config.read(machine_config)

        machine_config = os.path.join(
            here, '..', 'polaris', 'machines', f'{machine}.cfg'
        )
        if not os.path.exists(machine_config):
            raise FileNotFoundError(
                f'Could not find a config file for this machine at '
                f'polaris/machines/{machine}.cfg'
            )

        config.read(machine_config)

    if config_file is not None:
        config.read(config_file)

    return config


def _get_version():
    """
    Get the Polaris version by parsing the version file
    """

    # we can't import polaris because we probably don't have the necessary
    # dependencies, so we get the version by parsing (same approach used in
    # the root setup.py)
    here = os.path.abspath(os.path.dirname(__file__))
    version_path = os.path.join(here, '..', 'polaris', 'version.py')
    with open(version_path) as f:
        main_ns: Dict[str, str] = dict()
        exec(f.read(), main_ns)
        version = main_ns['__version__']

    return version


def _get_compilers_mpis(options):  # noqa: C901
    """
    Get the compilers and MPI variants from the config object
    """

    compilers = options['compilers']
    mpis = options['mpis']
    config = options['config']
    machine = options['machine']
    source_path = options['source_path']

    unsupported = _parse_unsupported(machine, source_path)
    if machine == 'conda-linux':
        all_compilers = ['gfortran']
        all_mpis = ['mpich', 'openmpi']
    elif machine == 'conda-osx':
        all_compilers = ['clang']
        all_mpis = ['mpich', 'openmpi']
    else:
        machine_info = MachineInfo(machine)
        all_compilers = machine_info.compilers
        all_mpis = machine_info.mpilibs

    if not config.has_option('deploy', 'compiler'):
        raise ValueError(
            f'Machine config file for {machine} is missing a default compiler.'
        )
    default_compiler = config.get('deploy', 'compiler')

    error_on_unsupported = True

    if compilers is not None and compilers[0] == 'all':
        error_on_unsupported = False
        if mpis is not None and mpis[0] == 'all':
            # make a matrix of compilers and mpis
            compilers = list()
            mpis = list()
            for compiler in all_compilers:
                for mpi in all_mpis:
                    compilers.append(compiler)
                    mpis.append(mpi)
        else:
            compilers = all_compilers
            if mpis is not None:
                if len(mpis) > 1:
                    raise ValueError(
                        f'"--compiler all" can only be combined '
                        f'with "--mpi all" or a single MPI '
                        f'library, \n'
                        f'but got: {mpis}'
                    )
                mpi = mpis[0]
                mpis = [mpi for _ in compilers]

    elif mpis is not None and mpis[0] == 'all':
        error_on_unsupported = False
        mpis = all_mpis
        if compilers is None:
            compiler = default_compiler
        else:
            if len(compilers) > 1:
                raise ValueError(
                    f'"--mpis all" can only be combined with '
                    f'"--compiler all" or a single compiler, \n'
                    f'but got: {compilers}'
                )
            compiler = compilers[0]
        # The compiler is all the same
        compilers = [compiler for _ in mpis]

    if compilers is None:
        compilers = [config.get('deploy', 'compiler')]

    if mpis is None:
        mpis = list()
        for compiler in compilers:
            option = f'mpi_{compiler.replace("-", "_")}'
            if not config.has_option('deploy', option):
                raise ValueError(
                    f'Machine config file for {machine} is '
                    f'missing [deploy]/{option}, the default MPI '
                    f'library for the requested compiler.'
                )
            mpi = config.get('deploy', option)
            mpis.append(mpi)

    supported_compilers = list()
    supported_mpis = list()
    for compiler, mpi in zip(compilers, mpis, strict=False):
        if (compiler, mpi) in unsupported:
            if error_on_unsupported:
                raise ValueError(
                    f'{compiler} with {mpi} is not supported on {machine}'
                )
        else:
            supported_compilers.append(compiler)
            supported_mpis.append(mpi)

    options['compilers'] = supported_compilers
    options['mpis'] = supported_mpis


def _get_env_setup(options, compiler, mpi):
    """
    Setup the options for the environment for the given compiler and MPI
    variant
    """

    conda_env_name = options['conda_env_name']
    env_type = options['env_type']
    source_path = options['source_path']
    config = options['config']
    logger = options['logger']
    machine = options['machine']
    polaris_version = options['polaris_version']
    conda_base = options['conda_base']

    if options['python'] is not None:
        python = options['python']
    else:
        python = config.get('deploy', 'python')

    if options['recreate'] is not None:
        recreate = options['recreate']
    else:
        recreate = config.getboolean('deploy', 'recreate')

    if machine is None:
        conda_mpi = 'nompi'
        activ_suffix = ''
        env_suffix = ''
    elif not machine.startswith('conda'):
        conda_mpi = 'nompi'
        activ_suffix = f'_{machine}_{compiler}_{mpi}'
        env_suffix = ''
    else:
        activ_suffix = f'_{mpi}'
        env_suffix = activ_suffix
        conda_mpi = mpi

    lib_suffix = ''
    if options['with_albany']:
        lib_suffix = f'{lib_suffix}_albany'
    else:
        config.set('deploy', 'albany', 'None')

    if options['with_petsc']:
        lib_suffix = f'{lib_suffix}_petsc'
        logger.info(
            "Turning off OpenMP because it doesn't work well with  PETSc"
        )
        options['without_openmp'] = True
    else:
        config.set('deploy', 'petsc', 'None')
        config.set('deploy', 'lapack', 'None')

    activ_suffix = f'{activ_suffix}{lib_suffix}'

    if env_type == 'dev':
        activ_path = source_path
    else:
        activ_path = os.path.abspath(os.path.join(conda_base, '..'))

    if options['with_albany']:
        _check_supported('albany', machine, compiler, mpi, source_path)

    if options['with_petsc']:
        _check_supported('petsc', machine, compiler, mpi, source_path)

    if env_type == 'dev':
        ver = version.parse(polaris_version)
        release_version = '.'.join(str(vr) for vr in ver.release)
        spack_env = f'dev_polaris_{release_version}{env_suffix}'
        conda_env = f'dev_polaris_{polaris_version}{env_suffix}'
    elif env_type == 'test_release':
        spack_env = f'test_polaris_{polaris_version}{env_suffix}'
        conda_env = spack_env
    else:
        spack_env = f'polaris_{polaris_version}{env_suffix}'
        conda_env = spack_env

    if conda_env_name is None or env_type != 'dev':
        conda_env_name = conda_env

    # add the compiler and MPI library to the spack env name
    spack_env = f'{spack_env}_{compiler}_{mpi}{lib_suffix}'
    # spack doesn't like dots
    spack_env = spack_env.replace('.', '_')

    conda_env_path = os.path.join(conda_base, 'envs', conda_env_name)

    source_activation_scripts = f'source {conda_base}/etc/profile.d/conda.sh'

    activate_env = (
        f'{source_activation_scripts} && conda activate {conda_env_name}'
    )

    options['conda_env_name'] = conda_env_name
    options['python'] = python
    options['recreate'] = recreate
    options['conda_mpi'] = conda_mpi
    options['activ_suffix'] = activ_suffix
    options['env_suffix'] = env_suffix
    options['activ_path'] = activ_path
    options['conda_env_path'] = conda_env_path
    options['activate_env'] = activate_env
    options['spack_env'] = spack_env


def _build_conda_env(options, activate_base):
    """
    Build the conda environment
    """

    config = options['config']
    logger = options['logger']
    env_type = options['env_type']
    conda_env_name = options['conda_env_name']
    source_path = options['source_path']
    use_local = options['use_local']
    local_conda_build = options['local_conda_build']
    update_jigsaw = options['update_jigsaw']
    conda_template_path = options['conda_template_path']
    version = options['polaris_version']
    local_mache = options['local_mache']
    conda_base = options['conda_base']
    conda_mpi = options['conda_mpi']
    python = options['python']
    conda_env_path = options['conda_env_path']
    recreate = options['recreate']

    if env_type != 'dev':
        install_miniforge(conda_base, activate_base, logger)

    if conda_mpi == 'nompi':
        mpi_prefix = 'nompi'
    else:
        mpi_prefix = f'mpi_{conda_mpi}'

    channel_list = ['-c conda-forge', '-c defaults']
    if use_local:
        channel_list = ['--use-local'] + channel_list
    if local_conda_build is not None:
        channel_list = ['-c', local_conda_build] + channel_list
    if env_type == 'test_release':
        # for a test release, we will be the polaris package from the dev label
        channel_list = channel_list + ['-c e3sm/label/polaris_dev']
    channel_list = channel_list + ['-c e3sm/label/polaris']

    channels = f'--override-channels {" ".join(channel_list)}'
    packages = f'python={python}'

    base_activation_script = os.path.abspath(
        f'{conda_base}/etc/profile.d/conda.sh'
    )

    activate_env = (
        f'source {base_activation_script} && conda activate {conda_env_name}'
    )

    with open(f'{conda_template_path}/conda-dev-spec.template', 'r') as f:
        template = Template(f.read())

    if env_type == 'dev':
        supports_otps = platform.system() == 'Linux'
        if platform.system() == 'Linux':
            conda_openmp = 'libgomp'
        elif platform.system() == 'Darwin':
            conda_openmp = 'llvm-openmp'
        else:
            conda_openmp = ''

        replacements = dict(
            supports_otps=supports_otps,
            mpi=conda_mpi,
            openmp=conda_openmp,
            mpi_prefix=mpi_prefix,
            include_mache=not local_mache,
        )

        for package in [
            'esmf',
            'geometric_features',
            'mache',
            'metis',
            'mpas_tools',
            'netcdf_c',
            'netcdf_fortran',
            'otps',
            'parallelio',
            'pnetcdf',
        ]:
            replacements[package] = config.get('deploy', package)

        replacements['moab'] = config.get('deploy', 'conda_moab')

        spec_file = template.render(**replacements)

        spec_filename = f'spec-file-{conda_mpi}.txt'
        with open(spec_filename, 'w') as handle:
            handle.write(spec_file)
    else:
        spec_filename = None

    if not os.path.exists(conda_env_path):
        recreate = True

    if recreate:
        print(f'creating {conda_env_name}')
        if env_type == 'dev':
            # install dev dependencies and polaris itself
            commands = (
                f'{activate_base} && '
                f'conda create -y -n {conda_env_name} {channels} '
                f'--file {spec_filename} {packages}'
            )
            check_call(commands, logger=logger)
        else:
            # conda packages don't like dashes
            version_conda = version.replace('-', '')
            packages = f'{packages} "polaris={version_conda}={mpi_prefix}_*"'
            commands = (
                f'{activate_base} && '
                f'conda create -y -n {conda_env_name}'
                f'{channels} {packages}'
            )
            check_call(commands, logger=logger)
    else:
        if env_type == 'dev':
            print(f'Updating {conda_env_name}\n')
            # install dev dependencies and polaris itself
            commands = (
                f'{activate_base} && '
                f'conda install -y -n {conda_env_name} {channels} '
                f'--file {spec_filename} {packages}'
            )
            check_call(commands, logger=logger)
        else:
            print(f'{conda_env_name} already exists')

    if env_type == 'dev':
        if recreate or update_jigsaw:
            _build_jigsaw(options, activate_env, source_path, conda_env_path)

        # install (or reinstall) polaris in edit mode
        print('Installing polaris\n')
        commands = (
            f'{activate_env} && '
            f'cd {source_path} && '
            f'rm -rf polaris.egg-info && '
            f'python -m pip install --no-deps --no-build-isolation -e .'
        )
        check_call(commands, logger=logger)

        print('Installing pre-commit\n')
        commands = f'{activate_env} && cd {source_path} && pre-commit install'
        check_call(commands, logger=logger)


def _build_jigsaw(options, activate_env, source_path, conda_env_path):
    """
    Build the JIGSAW and JIGSAW-Python tools using conda-forge compilers
    """

    logger = options['logger']
    conda_base = options['conda_base']

    # remove conda jigsaw and jigsaw-python
    t0 = time.time()
    commands = (
        f'{activate_env} && conda remove -y --force-remove jigsaw jigsawpy'
    )
    try:
        check_call(commands, logger=logger)
    except subprocess.CalledProcessError:
        # this is fine, we just want to make sure these package are removed if
        # present
        pass

    commands = (
        f'{activate_env} && '
        f'cd {source_path} && '
        f'git submodule update --init jigsaw-python'
    )
    check_call(commands, logger=logger)

    print('Building JIGSAW\n')
    # add build tools to deployment env, not polaris env
    jigsaw_build_deps = 'cxx-compiler cmake make'
    if platform.system() == 'Linux':
        jigsaw_build_deps = f'{jigsaw_build_deps} sysroot_linux-64=2.17'
        netcdf_lib = f'{conda_env_path}/lib/libnetcdf.so'
    elif platform.system() == 'Darwin':
        jigsaw_build_deps = (
            f'{jigsaw_build_deps} macosx_deployment_target_osx-64=10.13'
        )
        netcdf_lib = f'{conda_env_path}/lib/libnetcdf.dylib'
    cmake_args = f'-DCMAKE_BUILD_TYPE=Release -DNETCDF_LIBRARY={netcdf_lib}'

    commands = (
        f'source {conda_base}/etc/profile.d/conda.sh && '
        f'conda activate polaris_bootstrap && '
        f'conda install -y {jigsaw_build_deps} && '
        f'cd {source_path}/jigsaw-python/external/jigsaw && '
        f'rm -rf tmp && '
        f'mkdir tmp && '
        f'cd tmp && '
        f'cmake .. {cmake_args} && '
        f'cmake --build . --config Release --target install --parallel 4 && '
        f'cd {source_path}/jigsaw-python && '
        f'rm -rf jigsawpy/_bin jigsawpy/_lib && '
        f'cp -r external/jigsaw/bin/ jigsawpy/_bin && '
        f'cp -r external/jigsaw/lib/ jigsawpy/_lib'
    )

    # need a clean environment on Aurora because of its gcc module and
    # should do no harm on other machines
    clean_env = {
        'HOME': os.environ['HOME'],
        'TERM': os.environ.get('TERM', 'xterm'),
    }

    check_call(commands, env=clean_env, logger=logger)

    print('Installing JIGSAW and JIGSAW-Python\n')
    commands = (
        f'{activate_env} && '
        f'cd {source_path}/jigsaw-python && '
        f'python -m pip install --no-deps --no-build-isolation -e . && '
        f'cp jigsawpy/_bin/* ${{CONDA_PREFIX}}/bin'
    )
    check_call(commands, logger=logger)

    t1 = time.time()
    total = int(t1 - t0 + 0.5)
    message = f'JIGSAW install took {total:.1f} s.'
    if logger is None:
        print(message)
    else:
        logger.info(message)


def _get_env_vars(machine, compiler, mpi):
    """
    Get the environment variables for the given machine, compiler, and MPI
    variant
    """

    if machine is None:
        machine = 'None'

    env_vars = (
        f'export POLARIS_COMPILER={compiler}\nexport POLARIS_MPI={mpi}\n'
    )

    env_vars = f'{env_vars}export MPAS_EXTERNAL_LIBS=""\n'

    if 'intel' in compiler and machine == 'anvil':
        env_vars = (
            f'{env_vars}'
            f'export I_MPI_CC=icc\n'
            f'export I_MPI_CXX=icpc\n'
            f'export I_MPI_F77=ifort\n'
            f'export I_MPI_F90=ifort\n'
        )

    if machine.startswith('conda'):
        # we're using parallelio so we don't have ADIOS support
        env_vars = f'{env_vars}export HAVE_ADIOS=false\n'

    if platform.system() == 'Linux' and machine.startswith('conda'):
        env_vars = (
            f'{env_vars}'
            f'export MPAS_EXTERNAL_LIBS="${{MPAS_EXTERNAL_LIBS}} -lgomp"\n'
        )

    if mpi == 'mvapich':
        env_vars = (
            f'{env_vars}'
            f'export MV2_ENABLE_AFFINITY=0\n'
            f'export MV2_SHOW_CPU_BINDING=1\n'
        )

    if machine.startswith('chicoma') or machine.startswith('pm'):
        env_vars = (
            f'{env_vars}'
            f'export NETCDF=${{CRAY_NETCDF_HDF5PARALLEL_PREFIX}}\n'
            f'export NETCDFF=${{CRAY_NETCDF_HDF5PARALLEL_PREFIX}}\n'
            f'export PNETCDF=${{CRAY_PARALLEL_NETCDF_PREFIX}}\n'
        )
    else:
        env_vars = (
            f'{env_vars}'
            f'export NETCDF=$(dirname $(dirname $(which nc-config)))\n'
            f'export NETCDFF=$(dirname $(dirname $(which nf-config)))\n'
            f'export PNETCDF=$(dirname $(dirname $(which pnetcdf-config)))\n'
        )

    return env_vars


def _build_spack_soft_env(options):  # noqa: C901
    """
    Build the software spack environment
    """

    update_spack = options['update_spack']
    spack_template_path = options['spack_template_path']
    tmpdir = options['tmpdir']
    config = options['config']
    machine = options['machine']
    env_type = options['env_type']
    polaris_version = options['polaris_version']

    if not config.has_option('deploy', 'software_compiler'):
        return None

    compiler = config.get('deploy', 'software_compiler')
    mpi_option = f'mpi_{compiler.replace("-", "_")}'
    if not config.has_option('deploy', mpi_option):
        raise ValueError(
            f'Machine config file for {machine} is missing '
            f'{mpi_option}, the MPI library for the software '
            f'compiler.'
        )
    mpi = config.get('deploy', mpi_option)

    if machine is not None:
        _get_spack_base(options)

    spack_base = options['spack_base']

    if spack_base is None:
        return None

    if env_type == 'dev':
        ver = version.parse(polaris_version)
        release_version = '.'.join(str(vr) for vr in ver.release)
        spack_env = f'dev_polaris_soft_{release_version}'
    elif env_type == 'test_release':
        spack_env = f'test_polaris_soft_{polaris_version}'
    else:
        spack_env = f'polaris_soft_{polaris_version}'

    spack_env = spack_env.replace('.', '_')

    build_dir = f'deploy_tmp/build_soft_{machine}'

    _safe_rmtree(build_dir)
    os.makedirs(name=build_dir, exist_ok=True)

    os.chdir(build_dir)

    esmf = config.get('deploy', 'esmf')

    if config.has_option('deploy', 'spack_mirror'):
        spack_mirror = config.get('deploy', 'spack_mirror')
    else:
        spack_mirror = None

    spack_branch_base = f'{spack_base}/{spack_env}'

    specs = list()

    e3sm_hdf5_netcdf = config.getboolean('deploy', 'use_e3sm_hdf5_netcdf')
    if not e3sm_hdf5_netcdf:
        hdf5 = config.get('deploy', 'hdf5')
        netcdf_c = config.get('deploy', 'netcdf_c')
        netcdf_fortran = config.get('deploy', 'netcdf_fortran')
        specs.extend(
            [
                f'hdf5@{hdf5}+cxx+fortran+hl+mpi+shared',
                f'netcdf-c@{netcdf_c}+mpi~parallel-netcdf',
                f'netcdf-fortran@{netcdf_fortran}',
            ]
        )

    if esmf != 'None':
        specs.append(f'esmf@{esmf}+mpi+netcdf~pnetcdf~external-parallelio')

    yaml_template: str | None = None
    template_path = f'{spack_template_path}/{machine}_{compiler}_{mpi}.yaml'
    if os.path.exists(template_path):
        yaml_template = template_path

    if machine is not None:
        here = os.path.abspath(os.path.dirname(__file__))
        machine_config = os.path.join(
            here, '..', 'polaris', 'machines', f'{machine}.cfg'
        )
    else:
        machine_config = None

    if update_spack:
        make_spack_env(
            spack_path=spack_branch_base,
            env_name=spack_env,
            spack_specs=specs,
            compiler=compiler,
            mpi=mpi,
            machine=machine,
            config_file=machine_config,
            include_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            yaml_template=yaml_template,
            tmpdir=tmpdir,
            spack_mirror=spack_mirror,
        )

    spack_view = (
        f'{spack_branch_base}/var/spack/environments/'
        f'{spack_env}/.spack-env/view'
    )

    os.chdir(options['source_path'])

    return spack_view


def _build_spack_libs_env(options, compiler, mpi, env_vars):  # noqa: C901
    """
    Build the library spack environment
    """

    config = options['config']
    machine = options['machine']
    update_spack = options['update_spack']
    spack_base = options['spack_base']
    tmpdir = options['tmpdir']
    spack_template_path = options['spack_template_path']
    spack_env = options['spack_env']

    albany = config.get('deploy', 'albany')
    cmake = config.get('deploy', 'cmake')
    lapack = config.get('deploy', 'lapack')
    metis = config.get('deploy', 'metis')
    moab = config.get('deploy', 'spack_moab')
    parmetis = config.get('deploy', 'parmetis')
    petsc = config.get('deploy', 'petsc')
    scorpio = config.get('deploy', 'scorpio')

    spack_branch_base = f'{spack_base}/{spack_env}'

    specs = list()

    if cmake != 'None':
        specs.append(f'cmake@{cmake}')

    e3sm_hdf5_netcdf = config.getboolean('deploy', 'use_e3sm_hdf5_netcdf')
    if not e3sm_hdf5_netcdf:
        hdf5 = config.get('deploy', 'hdf5')
        netcdf_c = config.get('deploy', 'netcdf_c')
        netcdf_fortran = config.get('deploy', 'netcdf_fortran')
        pnetcdf = config.get('deploy', 'pnetcdf')
        specs.extend(
            [
                f'hdf5@{hdf5}+cxx+fortran+hl+mpi+shared',
                f'netcdf-c@{netcdf_c}+mpi~parallel-netcdf',
                f'netcdf-fortran@{netcdf_fortran}',
                f'parallel-netcdf@{pnetcdf}+cxx+fortran',
            ]
        )

    if lapack != 'None':
        specs.append(f'netlib-lapack@{lapack}')
        include_e3sm_lapack = False
    else:
        include_e3sm_lapack = True
    if metis != 'None':
        specs.append(f'metis@{metis}+int64+real64~shared')
    if moab != 'None':
        specs.append(
            f'moab@{moab}+mpi+hdf5+netcdf+pnetcdf+metis+parmetis+tempest'
        )
    if parmetis != 'None':
        specs.append(f'parmetis@{parmetis}+int64~shared')
    if petsc != 'None':
        specs.append(f'petsc@{petsc}+mpi+batch')

    if scorpio != 'None':
        specs.append(
            f'e3sm-scorpio@{scorpio}+mpi~timing~internal-timing~tools+malloc'
        )

    if albany != 'None':
        specs.append(f'albany@{albany}+mpas')

    yaml_template: str | None = None
    template_path = f'{spack_template_path}/{machine}_{compiler}_{mpi}.yaml'
    if os.path.exists(template_path):
        yaml_template = template_path

    if machine is not None:
        here = os.path.abspath(os.path.dirname(__file__))
        machine_config = os.path.join(
            here, '..', 'polaris', 'machines', f'{machine}.cfg'
        )
    else:
        machine_config = None

    if update_spack:
        make_spack_env(
            spack_path=spack_branch_base,
            env_name=spack_env,
            spack_specs=specs,
            compiler=compiler,
            mpi=mpi,
            machine=machine,
            config_file=machine_config,
            include_e3sm_lapack=include_e3sm_lapack,
            include_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
            yaml_template=yaml_template,
            tmpdir=tmpdir,
        )

        _set_ld_library_path(options, spack_branch_base, spack_env)

    spack_script = get_spack_script(
        spack_path=spack_branch_base,
        env_name=spack_env,
        compiler=compiler,
        mpi=mpi,
        shell='sh',
        machine=machine,
        config_file=machine_config,
        include_e3sm_lapack=include_e3sm_lapack,
        include_e3sm_hdf5_netcdf=e3sm_hdf5_netcdf,
        yaml_template=yaml_template,
    )

    spack_view = (
        f'{spack_branch_base}/var/spack/environments/'
        f'{spack_env}/.spack-env/view'
    )
    env_vars = f'{env_vars}export PIO={spack_view}\n'
    if albany != 'None':
        albany_flag_filename = f'{spack_view}/export_albany.in'
        if not os.path.exists(albany_flag_filename):
            raise ValueError(
                f'Missing Albany linking flags in '
                f'{albany_flag_filename}.\n Maybe your Spack '
                f'environment may need to be rebuilt with '
                f'Albany?'
            )
        with open(albany_flag_filename, 'r') as f:
            albany_flags = f.read()
        if platform.system() == 'Darwin':
            stdcxx = '-lc++'
        else:
            stdcxx = '-lstdc++'
        if mpi == 'openmpi' and machine in ['anvil', 'chrysalis']:
            mpicxx = '-lmpi_cxx'
        else:
            mpicxx = ''
        env_vars = (
            f'{env_vars}'
            f'export {albany_flags}\n'
            f'export MPAS_EXTERNAL_LIBS="${{MPAS_EXTERNAL_LIBS}} '
            f'${{ALBANY_LINK_LIBS}} {stdcxx} {mpicxx}"\n'
        )

    if lapack != 'None':
        env_vars = (
            f'{env_vars}export LAPACK={spack_view}\nexport USE_LAPACK=true\n'
        )

    if metis != 'None':
        env_vars = f'{env_vars}export METIS_ROOT={spack_view}\n'

    if parmetis != 'None':
        env_vars = f'{env_vars}export PARMETIS_ROOT={spack_view}\n'

    if petsc != 'None':
        env_vars = (
            f'{env_vars}export PETSC={spack_view}\nexport USE_PETSC=true\n'
        )

    return spack_script, env_vars


def _set_ld_library_path(options, spack_branch_base, spack_env):
    """
    Set the ``LD_LIBRARY_PATH environment variable for the given spack branch
    and environment
    """

    commands = (
        f'source {spack_branch_base}/share/spack/setup-env.sh && '
        f'spack env activate {spack_env} && '
        f'spack config add modules:prefix_inspections:lib:[LD_LIBRARY_PATH] && '  # noqa: E501
        f'spack config add modules:prefix_inspections:lib64:[LD_LIBRARY_PATH]'
    )
    check_call(commands, logger=options['logger'])


def _write_load_polaris(options, prefix, spack_script, env_vars):
    """
    Write the Polaris load (activation) script
    """

    env_type = options['env_type']
    conda_env_name = options['conda_env_name']
    source_path = options['source_path']
    machine = options['machine']
    conda_env_only = options['conda_env_only']
    without_openmp = options['without_openmp']
    template_path = options['conda_template_path']
    polaris_version = options['polaris_version']
    conda_base = options['conda_base']
    activ_path = options['activ_path']
    activ_suffix = options['activ_suffix']

    os.makedirs(name=activ_path, exist_ok=True)

    if prefix.endswith(activ_suffix):
        # avoid a redundant activation script name if the suffix is already
        # part of the environment name
        script_filename = f'{activ_path}/{prefix}.sh'
    else:
        script_filename = f'{activ_path}/{prefix}{activ_suffix}.sh'

    if not conda_env_only:
        env_vars = f'{env_vars}\nexport USE_PIO2=true'
    if without_openmp:
        env_vars = f'{env_vars}\nexport OPENMP=false'
    else:
        env_vars = f'{env_vars}\nexport OPENMP=true'

    env_vars = (
        f'{env_vars}\n'
        f'export HDF5_USE_FILE_LOCKING=FALSE\n'
        f'export LOAD_POLARIS_ENV={script_filename}'
    )
    if machine is not None and not machine.startswith('conda'):
        env_vars = f'{env_vars}\nexport POLARIS_MACHINE={machine}'

    filename = f'{template_path}/load_polaris.template'
    with open(filename, 'r') as f:
        template = Template(f.read())

    if env_type == 'dev':
        update_polaris = """
            if [[ -z "${NO_POLARIS_REINSTALL}" && -f "./pyproject.toml" && \\
                  -d "polaris" ]]; then
               # safe to assume we're in the polaris repo
               # update the polaris installation to point here
               mkdir -p deploy_tmp/logs
               echo Reinstalling polaris package in edit mode...
               python -m pip install --no-deps --no-build-isolation -e . \\
                   &> deploy_tmp/logs/install_polaris.log
               echo Done.
               echo
            fi
            """  # noqa: E501
    else:
        update_polaris = ''

    script = template.render(
        conda_base=conda_base,
        polaris_env=conda_env_name,
        env_vars=env_vars,
        spack=spack_script,
        update_polaris=update_polaris,
        env_type=env_type,
        polaris_source_path=source_path,
        polaris_version=polaris_version,
    )

    # strip out redundant blank lines
    lines = list()
    prev_line = ''
    for line in script.split('\n'):
        line = line.strip()
        if line != '' or prev_line != '':
            lines.append(line)
        prev_line = line

    lines.append('')

    script = '\n'.join(lines)

    print(f'Writing:\n   {script_filename}\n')
    with open(script_filename, 'w') as handle:
        handle.write(script)

    return script_filename


def _check_env(options, script_filename, conda_env_name):
    """
    Check that polaris has been installed correctly
    """

    logger = options['logger']
    print(f'Checking the environment {conda_env_name}')

    activate = f'source {script_filename}'

    imports = ['geometric_features', 'mpas_tools', 'jigsawpy', 'polaris']
    commands = [
        ['gpmetis', '--help'],
        ['ffmpeg', '--help'],
        ['polaris', 'list'],
        ['polaris', 'setup', '--help'],
        ['polaris', 'suite', '--help'],
    ]

    for import_name in imports:
        command = f'{activate} && python -c "import {import_name}"'
        _test_command(command, os.environ, import_name, logger)

    for command_list in commands:
        package = command_list[0]
        command = f'{activate} && {" ".join(command_list)}'
        _test_command(command, os.environ, package, logger)


def _test_command(command, env, package, logger):
    """
    Test package commands and print status of each command to logger
    """

    try:
        check_call(command, env=env, logger=logger)
    except subprocess.CalledProcessError as e:
        print(f'  {package} failed')
        raise e
    print(f'  {package} passes')


def _update_permissions(options, directories):  # noqa: C901
    """
    Update permissions in given directories
    """

    config = options['config']
    env_type = options['env_type']
    activ_path = options['activ_path']

    if not config.has_option('e3sm_unified', 'group'):
        return

    group = config.get('e3sm_unified', 'group')

    new_uid = os.getuid()
    new_gid = grp.getgrnam(group).gr_gid

    print('changing permissions on activation scripts')

    read_perm = (
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IRGRP
        | stat.S_IWGRP
        | stat.S_IROTH
    )
    exec_perm = (
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IWGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )

    mask = stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO

    if env_type != 'dev':
        activation_files = glob.glob(f'{activ_path}/*_polaris*.sh')
        for file_name in activation_files:
            os.chmod(file_name, read_perm)
            os.chown(file_name, new_uid, new_gid)

    print('changing permissions on environments')

    # first the base directories that don't seem to be included in
    # os.walk()
    for directory in directories:
        dir_stat = _safe_stat(directory)
        if dir_stat is None:
            continue

        perm = dir_stat.st_mode & mask

        if dir_stat.st_uid != new_uid:
            # current user doesn't own this dir so let's move on
            continue

        if perm == exec_perm and dir_stat.st_gid == new_gid:
            continue

        try:
            os.chown(directory, new_uid, new_gid)
            os.chmod(directory, exec_perm)
        except OSError:
            continue

    files_and_dirs = []
    for base in directories:
        for _, dirs, files in os.walk(base):
            files_and_dirs.extend(dirs)
            files_and_dirs.extend(files)

    widgets = [
        progressbar.Percentage(),
        ' ',
        progressbar.Bar(),
        ' ',
        progressbar.ETA(),
    ]
    bar = progressbar.ProgressBar(
        widgets=widgets, maxval=len(files_and_dirs)
    ).start()
    progress = 0
    for base in directories:
        for root, dirs, files in os.walk(base):
            for directory in dirs:
                progress += 1
                try:
                    bar.update(progress)
                except ValueError:
                    pass

                directory = os.path.join(root, directory)

                dir_stat = _safe_stat(directory)
                if dir_stat is None:
                    continue

                if dir_stat.st_uid != new_uid:
                    # current user doesn't own this dir so let's move on
                    continue

                perm = dir_stat.st_mode & mask

                if perm == exec_perm and dir_stat.st_gid == new_gid:
                    continue

                try:
                    os.chown(directory, new_uid, new_gid)
                    os.chmod(directory, exec_perm)
                except OSError:
                    continue

            for file_name in files:
                progress += 1
                try:
                    bar.update(progress)
                except ValueError:
                    pass
                file_name = os.path.join(root, file_name)
                file_stat = _safe_stat(file_name)
                if file_stat is None:
                    continue

                if file_stat.st_uid != new_uid:
                    # current user doesn't own this file so let's move on
                    continue

                perm = file_stat.st_mode & mask

                if perm & stat.S_IXUSR:
                    # executable, so make sure others can execute it
                    new_perm = exec_perm
                else:
                    new_perm = read_perm

                if perm == new_perm and file_stat.st_gid == new_gid:
                    continue

                try:
                    os.chown(file_name, new_uid, new_gid)
                    os.chmod(file_name, new_perm)
                except OSError:
                    continue

    bar.finish()
    print('  done.')


def _parse_unsupported(machine, source_path):
    """
    Get the unsupported compilers and MPI variants for the given machine
    """

    with open(
        os.path.join(source_path, 'deploy', 'unsupported.txt'), 'r'
    ) as f:
        content = f.readlines()
    content = [
        line.strip() for line in content if not line.strip().startswith('#')
    ]
    unsupported = list()
    for line in content:
        if line.strip() == '':
            continue
        parts = [part.strip() for part in line.split(',')]
        if len(parts) != 3:
            raise ValueError(f'Bad line in "unsupported.txt" {line}')
        if parts[0] != machine:
            continue
        compiler = parts[1]
        mpi = parts[2]
        unsupported.append((compiler, mpi))

    return unsupported


def _check_supported(library, machine, compiler, mpi, source_path):
    """
    Check that the given library is supported for the given machine, compiler,
    and MPI variant
    """

    filename = os.path.join(source_path, 'deploy', f'{library}_supported.txt')
    with open(filename, 'r') as f:
        content = f.readlines()
    content = [
        line.strip() for line in content if not line.strip().startswith('#')
    ]
    for line in content:
        if line.strip() == '':
            continue
        supported = [part.strip() for part in line.split(',')]
        if len(supported) != 3:
            raise ValueError(f'Bad line in "{library}_supported.txt" {line}')
        if (
            machine == supported[0]
            and compiler == supported[1]
            and mpi == supported[2]
        ):
            return

    raise ValueError(
        f'{compiler} with {mpi} is not supported with {library} on {machine}'
    )


def _ignore_file_errors(f):
    """
    Ignore any permission and missing file errors, but pass others on
    """

    def _wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except (PermissionError, FileNotFoundError):
            pass

    return _wrapper


@_ignore_file_errors
def _safe_rmtree(path):
    shutil.rmtree(path)


@_ignore_file_errors
def _safe_stat(path):
    return os.stat(path)


def _discover_machine(quiet=False):
    """
    Figure out the machine from the host name

    Parameters
    ----------
    quiet : bool, optional
        Whether to print warnings if the machine name is ambiguous

    Returns
    -------
    machine : str
        The name of the current machine
    """

    machine = mache_discover_machine(quiet=quiet)
    if machine is None:
        possible_hosts = _get_possible_hosts()
        hostname = socket.gethostname()
        for possible_machine, hostname_contains in possible_hosts.items():
            if hostname_contains in hostname:
                machine = possible_machine
                break
    return machine


def _get_possible_hosts():
    """
    Get a list of possible hosts from the existing machine config files
    """

    here = os.path.abspath(os.path.dirname(__file__))
    files = sorted(
        glob.glob(os.path.join(here, '..', 'polaris', 'machines', '*.cfg'))
    )

    possible_hosts = dict()
    for filename in files:
        machine = os.path.splitext(os.path.split(filename)[1])[0]
        config = ConfigParser(interpolation=ExtendedInterpolation())
        config.read(filename)
        if config.has_section('discovery') and config.has_option(
            'discovery', 'hostname_contains'
        ):
            hostname_contains = config.get('discovery', 'hostname_contains')
            possible_hosts[machine] = hostname_contains

    return possible_hosts


if __name__ == '__main__':
    main()
