#!/usr/bin/env python3
"""
Benchmark a Polaris, Omega or E3SM branch against a baseline.

The driver resolves two "sides" of a benchmark -- a baseline and a test
-- sets each of them up with the same Polaris task or suite, and gives
the test side the baseline work directory with ``-b`` so that Polaris'
own validation compares them.

Each side is either *provisioned* (a detached ``git worktree`` created
from a requested fork and ref) or *adopted* (an existing Polaris
worktree, used read-only and never modified).

Run with ``--dry-run`` first: it resolves every commit hash and prints
the exact commands that would be run without building anything.
"""

import argparse
import configparser
import hashlib
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitrepo  # noqa: E402
import polaris_run  # noqa: E402
from shared import get_logger, to_abs  # noqa: E402

#: The name of the file that marks a completed benchmark work directory
COMPLETE_MARKER = '.polaris_benchmark_complete'

#: Environment variables that config files may refer to as ``${NAME}``
CONFIG_ENV_VARS = ['USER', 'HOME', 'SCRATCH']


def benchmark(config, config_path, args):
    """
    Run a benchmark of a test configuration against a baseline

    Parameters
    ----------
    config : configparser.ConfigParser
        The benchmark config options
    config_path : str
        The directory the config file lives in, used to resolve relative
        paths
    args : argparse.Namespace
        The parsed command-line arguments

    Returns
    -------
    manifest : dict
        A description of everything that was resolved and run
    """
    section = config['benchmark']
    work_base = to_abs(section['work_base'], config_path)
    primary_path = to_abs(
        section.get('primary_path', fallback=config_path), config_path
    )
    load_script_name = section['load_script']
    setup_command = section['setup_command']
    run_command = section.get('run_command', fallback='polaris serial')
    submit = section.getboolean('submit', fallback=False)

    polaris_config = section.get('polaris_config_file', fallback='')
    if polaris_config:
        polaris_config = to_abs(polaris_config, config_path)
        if not os.path.exists(polaris_config):
            raise ValueError(f'No such polaris_config_file: {polaris_config}')
    else:
        polaris_config = None

    polaris_run.check_setup_command(setup_command)

    baseline = _resolve_side(
        'baseline',
        config,
        config_path,
        args,
        primary_path,
        work_base,
        load_script_name,
    )
    test = _resolve_side(
        'test',
        config,
        config_path,
        args,
        primary_path,
        work_base,
        load_script_name,
    )

    _check_guardrails(baseline, test, load_script_name, args)

    run_dir = _get_run_dir(work_base, baseline, test)
    baseline_dir = _get_baseline_dir(
        work_base, baseline, setup_command, polaris_config
    )
    test_dir = os.path.join(run_dir, 'test')

    logger = None
    if not args.dry_run:
        os.makedirs(run_dir, exist_ok=True)
        logger = get_logger(
            'benchmark', os.path.join(run_dir, 'benchmark.log')
        )

    manifest = {
        'created': datetime.now().isoformat(timespec='seconds'),
        'reproducible': not (baseline.dirty or test.dirty),
        'run_dir': run_dir,
        'baseline_dir': baseline_dir,
        'test_dir': test_dir,
        'setup_command': setup_command,
        'run_command': run_command,
        'submit': submit,
        'differing_repos': gitrepo.check_single_variable(baseline, test),
        'baseline': baseline.provenance(),
        'test': test.provenance(),
    }

    baseline_job = _run_baseline(
        baseline=baseline,
        baseline_dir=baseline_dir,
        run_dir=run_dir,
        setup_command=setup_command,
        run_command=run_command,
        polaris_config=polaris_config,
        submit=submit,
        args=args,
        logger=logger,
        manifest=manifest,
    )

    manifest['test_job_id'] = polaris_run.setup_and_run(
        state=test,
        setup_command=setup_command,
        run_command=run_command,
        work_dir=test_dir,
        component_path=os.path.join(run_dir, 'build_test'),
        baseline_dir=baseline_dir,
        config_file=polaris_config,
        clean_build=args.clean_build,
        rebuild=args.rebuild,
        submit=submit,
        dependency=baseline_job,
        dry_run=args.dry_run,
        logger=logger,
    )
    manifest['baseline_job_id'] = baseline_job

    if not args.dry_run:
        if not submit:
            _mark_complete(test_dir)
        _write_manifest(run_dir, manifest)

    return manifest


def main():
    """Parse arguments and run a benchmark."""
    args = parse_args()

    config = configparser.ConfigParser(
        defaults=environment_defaults(),
        interpolation=configparser.ExtendedInterpolation(),
    )
    config_file = os.path.abspath(args.config_file)
    if not os.path.exists(config_file):
        raise FileNotFoundError(f'No such config file: {config_file}')
    config.read(config_file)
    config_path = os.path.dirname(config_file)

    try:
        manifest = benchmark(config, config_path, args)
    except ValueError as exc:
        print('')
        print(f'Error: {exc}')
        sys.exit(1)

    print('')
    print(72 * '-')
    print('Benchmark summary')
    print(72 * '-')
    _print_summary(manifest)


def environment_defaults():
    """
    Get the environment variables config files may substitute

    ``configparser`` has no notion of environment variables, so the ones
    in ``CONFIG_ENV_VARS`` are added as defaults.  A config file can then
    write ``${USER}`` in a path and get the expected substitution.

    Returns
    -------
    defaults : dict
        The environment variables that are set, keyed by name
    """
    return {
        name: os.environ[name]
        for name in CONFIG_ENV_VARS
        if name in os.environ
    }


def parse_args():
    """
    Parse the command-line arguments

    Returns
    -------
    args : argparse.Namespace
        The parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Benchmark a polaris, Omega or E3SM branch against a '
        'baseline using a polaris task or suite'
    )
    parser.add_argument(
        '-f',
        '--config_file',
        dest='config_file',
        required=True,
        help='Configuration file with benchmark options.',
        metavar='FILE',
    )
    parser.add_argument(
        '--dry-run',
        dest='dry_run',
        action='store_true',
        help='Resolve commits and print the commands that would be run '
        'without building or running anything.',
    )
    parser.add_argument(
        '--allow-dirty',
        dest='allow_dirty',
        action='store_true',
        help='Permit an adopted worktree with uncommitted or untracked '
        'changes.  The run is recorded as not reproducible.',
    )
    parser.add_argument(
        '--allow-multiple-changes',
        dest='allow_multiple_changes',
        action='store_true',
        help='Permit the baseline and test to differ in more than one of '
        'polaris, Omega and E3SM.',
    )
    parser.add_argument(
        '--allow-env-mismatch',
        dest='allow_env_mismatch',
        action='store_true',
        help='Permit the two sides to use different load scripts.',
    )
    parser.add_argument(
        '--clean-build',
        dest='clean_build',
        action='store_true',
        help='Start from a clean build directory on both sides.',
    )
    parser.add_argument(
        '--rebuild',
        dest='rebuild',
        action='store_true',
        help='Force a build even if the component is already built.',
    )
    for side in ['baseline', 'test']:
        parser.add_argument(
            f'--{side}-existing',
            dest=f'{side}_existing',
            help=f'Adopt an existing polaris worktree for the {side}.',
            metavar='PATH',
        )
        parser.add_argument(
            f'--{side}-polaris-fork',
            dest=f'{side}_polaris_fork',
            help=f'The polaris fork to use for the {side}.',
            metavar='FORK',
        )
        parser.add_argument(
            f'--{side}-polaris-ref',
            dest=f'{side}_polaris_ref',
            help=f'The polaris branch, tag or hash for the {side}.',
            metavar='REF',
        )
        for key in gitrepo.SUBMODULE_PATHS:
            parser.add_argument(
                f'--{side}-{key}-fork',
                dest=f'{side}_{key}_fork',
                help=f'The {key} fork to use for the {side}.',
                metavar='FORK',
            )
            parser.add_argument(
                f'--{side}-{key}-ref',
                dest=f'{side}_{key}_ref',
                help=f'The {key} branch, tag or hash for the {side}.',
                metavar='REF',
            )

    return parser.parse_args()


def _resolve_side(
    name,
    config,
    config_path,
    args,
    primary_path,
    work_base,
    load_script_name,
):
    """Provision or adopt one side of the benchmark."""
    section = config[name]
    model = section['model']
    if model not in gitrepo.MODEL_SUBMODULES:
        raise ValueError(
            f'Unknown model "{model}" in the [{name}] section; expected one '
            f'of {", ".join(gitrepo.MODEL_SUBMODULES)}'
        )

    source = section.get('source', fallback='worktree')
    existing = getattr(args, f'{name}_existing')
    if existing is not None:
        # the command line overrides a config file that asks for a
        # worktree, so the fork and ref options there are simply unused
        return gitrepo.adopt(
            name=name,
            path=to_abs(existing, config_path),
            model=model,
            load_script_name=load_script_name,
            allow_dirty=args.allow_dirty,
        )

    if source == 'existing':
        _check_no_fork_keys(name, section)
        return gitrepo.adopt(
            name=name,
            path=to_abs(section['path'], config_path),
            model=model,
            load_script_name=load_script_name,
            allow_dirty=args.allow_dirty,
        )

    if source != 'worktree':
        raise ValueError(
            f'Unknown source "{source}" in the [{name}] section; expected '
            f'"worktree" or "existing"'
        )

    fork = _option(args, section, name, 'polaris', 'fork', 'E3SM-Project')
    ref = _option(args, section, name, 'polaris', 'ref', 'main')

    submodule_specs = {}
    for key in gitrepo.SUBMODULE_PATHS:
        sub_fork = _option(args, section, name, key, 'fork', '')
        sub_ref = _option(args, section, name, key, 'ref', '')
        if sub_ref:
            submodule_specs[key] = (sub_fork, sub_ref)
        elif sub_fork:
            raise ValueError(
                f'{key}_fork is set without {key}_ref in the [{name}] section'
            )

    return gitrepo.provision(
        name=name,
        primary_path=primary_path,
        work_base=work_base,
        fork=fork,
        ref=ref,
        model=model,
        load_script_name=load_script_name,
        submodule_specs=submodule_specs,
        dry_run=args.dry_run,
    )


def _option(args, section, name, repo, kind, default):
    """Get an option from the command line, then the config, then default."""
    value = getattr(args, f'{name}_{repo}_{kind}', None)
    if value is not None:
        return value
    return section.get(f'{repo}_{kind}', fallback=default)


def _check_no_fork_keys(name, section):
    """Raise if fork/ref keys are set for an adopted worktree."""
    found = [
        key
        for key in section
        if key.endswith(('_fork', '_ref')) and section[key]
    ]
    if found:
        raise ValueError(
            f'The [{name}] section uses source = existing, so the fork and '
            f'ref of the checkout are recorded rather than requested.  '
            f'Remove: {", ".join(sorted(found))}'
        )


def _check_guardrails(baseline, test, load_script_name, args):
    """Check the cross-cutting guardrails before anything is built."""
    if baseline.path == test.path:
        raise ValueError(
            'The baseline and test resolve to the same worktree, so there '
            'is nothing to compare.'
        )

    if baseline.model != test.model:
        raise ValueError(
            f'The baseline model "{baseline.model}" and test model '
            f'"{test.model}" differ, so the results are not comparable.'
        )

    differing = gitrepo.check_single_variable(baseline, test)
    if not differing:
        raise ValueError(
            'The baseline and test resolve to identical commits in polaris '
            'and all submodules, so there is nothing to compare.'
        )
    if len(differing) > 1 and not args.allow_multiple_changes:
        raise ValueError(
            f'The baseline and test differ in more than one repository '
            f'({", ".join(differing)}), so a difference could not be '
            f'attributed to a single change.  Rerun with '
            f'--allow-multiple-changes to proceed anyway.'
        )

    if not args.allow_env_mismatch:
        baseline_script = os.path.basename(baseline.load_script)
        test_script = os.path.basename(test.load_script)
        if baseline_script and test_script and baseline_script != test_script:
            raise ValueError(
                f'The baseline uses {baseline_script} but the test uses '
                f'{test_script}, so the machine, compiler or MPI library '
                f'may differ.  Rerun with --allow-env-mismatch to proceed.'
            )


def _run_baseline(
    baseline,
    baseline_dir,
    run_dir,
    setup_command,
    run_command,
    polaris_config,
    submit,
    args,
    logger,
    manifest,
):
    """Run the baseline unless a complete one can be reused."""
    if _is_complete(baseline_dir):
        manifest['baseline_reused'] = True
        message = f'Reusing the completed baseline at {baseline_dir}'
        if logger is None:
            print(message)
        else:
            logger.info(message)
        return None

    manifest['baseline_reused'] = False
    job_id = polaris_run.setup_and_run(
        state=baseline,
        setup_command=setup_command,
        run_command=run_command,
        work_dir=baseline_dir,
        component_path=os.path.join(run_dir, 'build_baseline'),
        baseline_dir=None,
        config_file=polaris_config,
        clean_build=args.clean_build,
        rebuild=args.rebuild,
        submit=submit,
        dry_run=args.dry_run,
        logger=logger,
    )
    if not args.dry_run and not submit:
        _mark_complete(baseline_dir)
    return job_id


def _get_run_dir(work_base, baseline, test):
    """Get the deterministic run directory for this pair of sides."""
    date = datetime.now().strftime('%Y%m%d')
    name = f'{date}-{baseline.polaris_sha[:7]}-{test.polaris_sha[:7]}'
    if baseline.dirty or test.dirty:
        name = f'dirty-{name}'
    return os.path.join(work_base, 'runs', name)


def _get_baseline_dir(work_base, baseline, setup_command, polaris_config):
    """
    Get the cacheable baseline work directory.

    The name covers everything a baseline depends on, so that a baseline
    is only ever reused by a benchmark it is actually comparable with.

    A dirty baseline is never cached or reused, since it cannot be
    reproduced from the recorded commit hashes.
    """
    suite = polaris_run.get_suite_name(setup_command)
    shas = baseline.compare_shas
    parts = [suite, baseline.model]
    parts.append(_setup_key(setup_command, polaris_config, baseline))
    parts.extend(sha[:7] for sha in shas.values() if sha)
    name = '_'.join(parts)
    if baseline.dirty:
        name = f'dirty_{name}_{datetime.now().strftime("%Y%m%d%H%M%S")}'
    return os.path.join(work_base, 'baselines', name)


def _setup_key(setup_command, polaris_config, baseline):
    """
    Get a short hash of what a baseline depends on besides the commits.

    ``polaris setup`` always reports the suite name ``custom``, so the
    tasks only appear here.  The polaris config file and the load script
    change the results too, so they are included as well.
    """
    parts = [
        ' '.join(setup_command.split()),
        os.path.basename(baseline.load_script),
    ]
    if polaris_config is not None:
        with open(polaris_config) as handle:
            parts.append(handle.read())
    text = '\n'.join(parts)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:7]


def _is_complete(work_dir):
    """Whether a work directory holds a completed run."""
    return os.path.exists(os.path.join(work_dir, COMPLETE_MARKER))


def _mark_complete(work_dir):
    """Mark a work directory as holding a completed run."""
    marker = os.path.join(work_dir, COMPLETE_MARKER)
    with open(marker, 'w') as handle:
        handle.write(datetime.now().isoformat(timespec='seconds') + '\n')


def _write_manifest(run_dir, manifest):
    """Write the manifest describing the benchmark to the run directory."""
    filename = os.path.join(run_dir, 'manifest.json')
    with open(filename, 'w') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')


def _print_summary(manifest):
    """Print a short summary of what was resolved and run."""
    for name in ['baseline', 'test']:
        side = manifest[name]
        print(f'{name}:')
        print(f'  mode:    {side["mode"]}')
        print(f'  path:    {side["path"]}')
        print(f'  polaris: {side["polaris_ref"]} {side["polaris_sha"][:7]}')
        for key, sha in sorted(side['submodule_shas'].items()):
            print(f'  {key}: {sha[:7]}')
    for name in ['baseline', 'test']:
        side = manifest[name]
        if not side['load_script_ready']:
            print('')
            print(
                f'Note: the {name} worktree does not exist yet, so its load '
                f'script\n  {side["load_script"]}\ncannot be checked.  It '
                f'must exist before the benchmark can run; see the load '
                f'script notes in utils/benchmark/README.md.'
            )
    print('')
    print(f'differing:    {", ".join(manifest["differing_repos"])}')
    print(f'reproducible: {manifest["reproducible"]}')
    print(f'baseline dir: {manifest["baseline_dir"]}')
    print(f'test dir:     {manifest["test_dir"]}')


if __name__ == '__main__':
    main()
