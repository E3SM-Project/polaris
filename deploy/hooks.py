"""Example deployment hooks for `mache deploy run`.

This file is **example-only**:
- Hooks run arbitrary Python code from this repository.
- Hooks are disabled unless you opt-in via `deploy/config.yaml.j2`.

To enable, add a `hooks` section like:

  hooks:
    file: "deploy/hooks.py"  # default
    entrypoints:
      pre_pixi: "pre_pixi"          # optional
      post_pixi: "post_pixi"        # optional
      post_publish: "post_publish"  # optional

"""

from __future__ import annotations

import os
import shlex
from typing import TYPE_CHECKING, Any, Dict

from packaging.version import Version

if TYPE_CHECKING:
    # This import is only for static type checking; at runtime, `mache` is
    # already installed in the bootstrap environment when hooks are executed.
    from mache.deploy.hooks import DeployContext


def pre_pixi(ctx: DeployContext) -> dict[str, Any] | None:
    """Run before the pixi environment is created/updated.

    Preferred pattern:
    - Compute derived values and store them in `ctx.runtime` via a returned
      dict (instead of mutating `ctx.config`).

    Returns
    -------
    dict | None
      Optional mapping merged into `ctx.runtime` by mache.
    """

    polaris_version = _get_version()
    mpi = _get_pixi_mpi(ctx.machine, ctx.machine_config, ctx.args)

    updates: Dict[str, Any] = {
        'project': {'version': polaris_version},
        'pixi': {'mpi': mpi},
    }

    return updates


def pre_spack(ctx: DeployContext) -> dict[str, Any] | None:
    """Run before the spack environment is created/updated.

    Preferred pattern:
    - Compute derived values and store them in `ctx.runtime` via a returned
      dict (instead of mutating `ctx.config`).

    Returns
    -------
    dict | None
      Optional mapping merged into `ctx.runtime` by mache.
    """

    spack_path = _get_spack_path(
        ctx.config, ctx.machine, ctx.machine_config, ctx.args
    )

    if spack_path is None:
        ctx.logger.info(
            'No supported shared Spack environment was detected for this '
            'run; disabling Spack and relying on Pixi dependencies instead.'
        )
        return {
            'spack': {
                'supported': False,
                'software': {'supported': False},
            }
        }

    return {'spack': {'spack_path': spack_path}}


def post_publish(ctx: DeployContext) -> None:
    """Install Git hooks from the deployed Pixi environment."""

    pixi = ctx.config.get('pixi', {})
    if not isinstance(pixi, dict) or not pixi.get(
        'install_dev_software', False
    ):
        return

    _install_pre_commit(ctx)


def _install_pre_commit(ctx: DeployContext) -> None:
    pre_commit_config = os.path.join(ctx.repo_root, '.pre-commit-config.yaml')
    if not os.path.exists(pre_commit_config):
        ctx.logger.info(
            'Skipping pre-commit install because %s was not found.',
            pre_commit_config,
        )
        return

    git_dir = os.path.join(ctx.repo_root, '.git')
    if not os.path.exists(git_dir):
        ctx.logger.info(
            'Skipping pre-commit install because %s is not a Git checkout.',
            ctx.repo_root,
        )
        return

    load_script = _get_load_script(ctx)
    if load_script is None:
        ctx.logger.info(
            'Skipping pre-commit install because no load script was recorded.'
        )
        return

    ctx.logger.info('Installing pre-commit hooks in %s', ctx.repo_root)
    from mache.deploy.bootstrap import check_call

    check_call(
        (
            f'source {shlex.quote(load_script)} && '
            f'cd {shlex.quote(ctx.repo_root)} && '
            'pre-commit install'
        ),
        log_filename=_get_deploy_log_filename(ctx),
        quiet=ctx.args.quiet,
    )


def _get_load_script(ctx: DeployContext) -> str | None:
    load_scripts = ctx.runtime.get('load_scripts')
    if not isinstance(load_scripts, list) or len(load_scripts) == 0:
        return None

    for script in load_scripts:
        if isinstance(script, str) and os.path.exists(script):
            return script

    return None


def _get_deploy_log_filename(ctx: DeployContext) -> str:
    return os.path.join(ctx.work_dir, 'logs', 'mache_deploy_run.log')


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
        polaris_version = main_ns['__version__']

    return polaris_version


def _get_pixi_mpi(machine, machine_config, args):
    """
    Get the MPI implementation for pixi from environment variable
    """
    if machine is not None and not getattr(args, 'no_spack', False):
        # On supported machines with spack enabled, we use the system MPI
        # through spack rather than installing an MPI stack in pixi.
        mpi = 'nompi'
    else:
        # For unknown machines, and for explicit --no-spack deployments on
        # known machines, pixi must provide the MPI-aware dependency stack.
        if not machine_config.has_section('deploy'):
            raise ValueError("Missing 'deploy' section in machine config")
        section = machine_config['deploy']
        compiler = section.get('compiler')
        if compiler is None:
            raise ValueError("Missing 'compiler' option in 'deploy' section")
        compiler_underscore = compiler.replace('-', '_')
        mpi_option = f'mpi_{compiler_underscore}'
        mpi = section.get(mpi_option)
        if mpi is None:
            raise ValueError(
                f"Missing '{mpi_option}' option in 'deploy' section"
            )
    return mpi


def _get_spack_path(config, machine, machine_config, args):
    """
    Get the Spack path from CLI, config or machine config
    """
    spack_path = getattr(args, 'spack_path', None)
    if spack_path is not None and str(spack_path).strip():
        return spack_path

    spack_path = config.get('spack', {}).get('spack_path')
    if spack_path is not None and str(spack_path).strip().lower() not in (
        '',
        'none',
        'null',
    ):
        return spack_path

    if machine is None:
        return None

    polaris_version = _get_version()

    # Use PEP 440 parsing to strip any pre/dev/post release tags and keep only
    # the base release version.
    release_version = Version(polaris_version).base_version
    spack_env = f'dev_polaris_{release_version}'

    if not machine_config.has_section('deploy'):
        return None
    section = machine_config['deploy']
    spack_base = section.get('spack')
    if spack_base is None or not spack_base.strip():
        return None
    spack_path = os.path.join(spack_base, spack_env)
    return spack_path
