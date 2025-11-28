#!/usr/bin/env python3
import os
import sys
from configparser import ConfigParser, ExtendedInterpolation

from deploy.shared import (
    check_call,
    get_conda_base,
    get_logger,
    install_miniforge,
    parse_args,
)


def main():
    """
    Entry point for the configure script
    """

    args = parse_args(bootstrap=False)
    source_path = os.getcwd()

    if args.tmpdir is not None:
        os.makedirs(name=args.tmpdir, exist_ok=True)

    config = _get_config(args.config_file)

    conda_base = get_conda_base(args.conda_base, config, warn=True)
    conda_base = os.path.abspath(conda_base)

    env_name = 'polaris_bootstrap'

    source_activation_scripts = f'source {conda_base}/etc/profile.d/conda.sh'

    activate_base = f'{source_activation_scripts} && conda activate'

    activate_install_env = (
        f'{source_activation_scripts} && conda activate {env_name}'
    )
    os.makedirs(name='deploy_tmp/logs', exist_ok=True)

    if args.verbose:
        logger = None
    else:
        logger = get_logger(
            log_filename='deploy_tmp/logs/prebootstrap.log', name=__name__
        )

    # install miniforge if needed
    install_miniforge(conda_base, activate_base, logger)

    local_mache = args.mache_fork is not None and args.mache_branch is not None

    packages = '--file deploy/spec-bootstrap.txt'
    if not local_mache:
        # we need to add the mache package, specifying a version,
        # since we won't be installing mache from a local clone of a branch
        mache_version = config.get('deploy', 'mache')
        packages = f'{packages} "mache={mache_version}"'

    _setup_install_env(
        env_name,
        activate_base,
        args.use_local,
        logger,
        args.recreate,
        conda_base,
        packages,
    )

    if local_mache:
        print('Clone and install local mache\n')
        commands = (
            f'{activate_install_env} && '
            f'rm -rf deploy_tmp/build_mache && '
            f'mkdir -p deploy_tmp/build_mache && '
            f'cd deploy_tmp/build_mache && '
            f'git clone -b {args.mache_branch} '
            f'git@github.com:{args.mache_fork}.git mache && '
            f'cd mache && '
            f'conda install -y --file spec-file.txt && '
            f'python -m pip install --no-deps --no-build-isolation .'
        )

        check_call(commands, logger=logger)

    # polaris only uses 'dev' environment type, but E3SM-Unified uses others
    env_type = config.get('deploy', 'env_type')
    if env_type not in ['dev', 'test_release', 'release']:
        raise ValueError(f'Unexpected env_type: {env_type}')

    if env_type == 'test_release' and args.use_local:
        local_conda_build = os.path.abspath(f'{conda_base}/conda-bld')
    else:
        local_conda_build = None

    _bootstrap(activate_install_env, source_path, local_conda_build)


def _get_config(config_file):
    """
    Read in the options from the config file and return the config object
    """

    # we can't load polaris so we find the config files
    here = os.path.abspath(os.path.dirname(__file__))
    default_config = os.path.join(here, 'deploy/default.cfg')
    config = ConfigParser(interpolation=ExtendedInterpolation())
    config.read(default_config)

    if config_file is not None:
        config.read(config_file)

    return config


def _setup_install_env(
    env_name, activate_base, use_local, logger, recreate, conda_base, packages
):
    """
    Setup a conda environment for installing polaris
    """

    env_path = os.path.join(conda_base, 'envs', env_name)

    if use_local:
        channels = '--use-local'
    else:
        channels = ''

    if recreate or not os.path.exists(env_path):
        print('Setting up a conda environment for installing polaris\n')
        conda_command = 'create'
    else:
        print('Updating conda environment for installing polaris\n')
        conda_command = 'install'
    commands = (
        f'{activate_base} && '
        f'conda {conda_command} -y -n {env_name} {channels} {packages}'
    )

    check_call(commands, logger=logger)


def _bootstrap(activate_install_env, source_path, local_conda_build):
    """
    Activate the environment for installing polaris and call bootstrap
    """

    print('Creating the polaris conda environment\n')
    bootstrap_command = f'{source_path}/deploy/bootstrap.py'
    command = (
        f'{activate_install_env} && '
        f'{bootstrap_command} {" ".join(sys.argv[1:])}'
    )
    if local_conda_build is not None:
        command = f'{command} --local_conda_build {local_conda_build}'
    check_call(command)


if __name__ == '__main__':
    main()
