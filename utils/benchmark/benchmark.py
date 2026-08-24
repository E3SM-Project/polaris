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
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitrepo  # noqa: E402
import polaris_run  # noqa: E402
from shared import get_logger, to_abs  # noqa: E402

#: The name of the file that marks a completed benchmark work directory
COMPLETE_MARKER = '.polaris_benchmark_complete'


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

    wall_time = section.get('wall_time', fallback='').strip()

    shared_component_path = section.get('component_path', fallback='').strip()
    if shared_component_path:
        shared_component_path = to_abs(shared_component_path, config_path)
    else:
        shared_component_path = None

    polaris_run.check_setup_command(setup_command)

    baseline, test = _resolve_sides(
        config=config,
        config_path=config_path,
        args=args,
        primary_path=primary_path,
        work_base=work_base,
        load_script_name=load_script_name,
        shared_component_path=shared_component_path,
    )

    _check_guardrails(
        baseline, test, load_script_name, args, shared_component_path
    )

    run_dir = _get_run_dir(work_base, baseline, test, setup_command)
    baseline_dir = _get_baseline_dir(
        work_base,
        baseline,
        setup_command,
        polaris_config,
        shared_component_path,
    )
    test_dir = os.path.join(run_dir, 'test')

    logger = None
    if not args.dry_run:
        os.makedirs(run_dir, exist_ok=True)
        logger = get_logger(
            'benchmark', os.path.join(run_dir, 'benchmark.log')
        )

    setup_config = _get_setup_config(
        run_dir=run_dir,
        polaris_config=polaris_config,
        wall_time=wall_time,
        dry_run=args.dry_run,
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
        'wall_time': wall_time or None,
        'polaris_config_file': polaris_config,
        'setup_config_file': setup_config,
        'component_path': shared_component_path,
        'differing_repos': gitrepo.check_single_variable(baseline, test),
        'baseline': baseline.provenance(),
        'test': test.provenance(),
    }

    baseline_job = _run_baseline(
        baseline=baseline,
        baseline_dir=baseline_dir,
        run_dir=run_dir,
        shared_component_path=shared_component_path,
        setup_command=setup_command,
        run_command=run_command,
        polaris_config=setup_config,
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
        component_path=_get_component_path(
            shared_component_path, run_dir, 'test'
        ),
        baseline_dir=baseline_dir,
        config_file=setup_config,
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

    config_file = os.path.abspath(args.config_file)
    if not os.path.exists(config_file):
        raise FileNotFoundError(f'No such config file: {config_file}')
    config_path = os.path.dirname(config_file)

    try:
        config = read_config(config_file)
        manifest = benchmark(config, config_path, args)
    except (ValueError, configparser.Error) as exc:
        print('')
        print(f'Error: {exc}')
        sys.exit(1)

    print('')
    print(72 * '-')
    print('Benchmark summary')
    print(72 * '-')
    _print_summary(manifest)


def read_config(config_file):
    """
    Read a benchmark config file, substituting environment variables

    ``configparser`` has no notion of environment variables, so any
    ``${NAME}`` that the config file does not define as an option is
    replaced with the environment variable of that name before the file
    is parsed.  An option therefore always wins over a variable, and a
    name that is neither is left alone so that interpolation reports it.

    Parameters
    ----------
    config_file : str
        The path to the config file

    Returns
    -------
    config : configparser.ConfigParser
        The parsed config options
    """
    with open(config_file) as handle:
        text = handle.read()

    raw = configparser.ConfigParser(interpolation=None)
    raw.read_string(text, source=config_file)
    options = set()
    for section in raw.sections():
        options.update(raw.options(section))

    for name in sorted(set(re.findall(r'\$\{([^}]+)\}', text))):
        if ':' in name or name.lower() in options:
            # a reference to a config option, not to a variable
            continue
        if name in os.environ:
            text = text.replace(f'${{{name}}}', os.environ[name])

    config = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    config.read_string(text, source=config_file)
    return config


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


def _resolve_sides(
    config,
    config_path,
    args,
    primary_path,
    work_base,
    load_script_name,
    shared_component_path,
):
    """
    Resolve both sides, reporting every problem with either of them

    Neither side is built or run until both have resolved, so stopping on
    the first problem only means the developer fixes it and meets the
    next one on the next dry run.  Both sides are therefore resolved
    before anything is raised.

    Returns
    -------
    baseline, test : gitrepo.SourceState
        The two resolved sides
    """
    states = {}
    problems = []
    # with one shared build, only the baseline is ever the side polaris
    # builds from, so the test side needs no model source of its own
    needs_model_source = {
        'baseline': True,
        'test': shared_component_path is None,
    }
    for name in ['baseline', 'test']:
        try:
            states[name] = _resolve_side(
                name,
                config,
                config_path,
                args,
                primary_path,
                work_base,
                load_script_name,
                needs_model_source=needs_model_source[name],
            )
        except ValueError as exc:
            problems.append(str(exc))

    if problems:
        raise ValueError('\n\n'.join(problems))

    baseline = states['baseline']
    test = states['test']
    if shared_component_path is not None:
        test.component_source = baseline.component_branch_path or ''
    return baseline, test


def _resolve_side(
    name,
    config,
    config_path,
    args,
    primary_path,
    work_base,
    load_script_name,
    needs_model_source=True,
):
    """Provision or adopt one side of the benchmark."""
    section = config[name]
    model = section['model']
    if model not in gitrepo.MODELS:
        raise ValueError(
            f'Unsupported model "{model}" in the [{name}] section; expected '
            f'one of {", ".join(gitrepo.MODELS)}.  Polaris only builds the '
            f'models it knows about automatically, which a benchmark relies '
            f'on.  Use "{gitrepo.NO_MODEL}" for a task or suite that runs '
            f'no model at all.'
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
            needs_model_source=needs_model_source,
        )

    if source == 'existing':
        _check_no_fork_keys(name, section)
        return gitrepo.adopt(
            name=name,
            path=to_abs(section['path'], config_path),
            model=model,
            load_script_name=load_script_name,
            allow_dirty=args.allow_dirty,
            needs_model_source=needs_model_source,
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
        needs_model_source=needs_model_source,
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


def _check_guardrails(
    baseline, test, load_script_name, args, shared_component_path
):
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

    if args.clean_build or args.rebuild:
        for side in [baseline, test]:
            if side.model == gitrepo.NO_MODEL:
                raise ValueError(
                    f'The [{side.name}] section uses model = '
                    f'{gitrepo.NO_MODEL}, so there is no component to '
                    f'build.  Drop --clean-build and --rebuild.'
                )

    if shared_component_path is not None:
        if baseline.model == gitrepo.NO_MODEL:
            raise ValueError(
                f'component_path is set, but model = {gitrepo.NO_MODEL}, so '
                f'there is no component to build or to find.  Drop '
                f'component_path.'
            )
        if args.clean_build:
            raise ValueError(
                f'--clean-build would delete the shared component_path '
                f"{shared_component_path}, which is not this benchmark's "
                f'to remove, and would then build it twice over.  Clean it '
                f'yourself, or drop component_path to build each side in '
                f'its own directory.'
            )
        key = gitrepo.MODEL_SUBMODULES[baseline.model]
        baseline_sha = baseline.compare_shas[key]
        test_sha = test.compare_shas[key]
        if baseline_sha != test_sha:
            raise ValueError(
                f'component_path is set, so both sides would run one build '
                f'of {baseline.model}, but they pin different {key} commits '
                f'({baseline_sha[:7]} and {test_sha[:7]}).  One of the two '
                f"sides would run the other's model.  Drop component_path "
                f'so that each side builds its own.'
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
    shared_component_path,
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
        component_path=_get_component_path(
            shared_component_path, run_dir, 'baseline'
        ),
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


def _get_component_path(shared_component_path, run_dir, side):
    """
    Get the path passed to ``polaris setup`` with ``-p`` for one side

    Each side builds in its own directory within the run directory unless
    a shared ``component_path`` was configured.  Polaris builds the model
    only when it does not find one at ``-p``, so a shared path means the
    first side to be set up builds it and the second one finds it and
    skips, which is the point of the option.

    Parameters
    ----------
    shared_component_path : str or None
        The configured ``component_path``, if there is one
    run_dir : str
        The run directory for this benchmark
    side : str
        Either ``baseline`` or ``test``

    Returns
    -------
    component_path : str
        The path to build the component in or find an existing build at
    """
    if shared_component_path is not None:
        return shared_component_path
    return os.path.join(run_dir, f'build_{side}')


def _get_setup_config(run_dir, polaris_config, wall_time, dry_run):
    """
    Get the polaris config file to pass on with ``-f``

    ``polaris setup`` takes a single config file, so a ``wall_time`` from
    the benchmark config is merged with ``polaris_config_file`` into one
    generated file in the run directory.  Both sides are given the same
    file, since a benchmark has to compare like with like.

    ``wall_time`` wins over a ``[job] wall_time`` in
    ``polaris_config_file``, and comments do not survive the merge, so the
    user's own file is the one recorded in the manifest.

    Parameters
    ----------
    run_dir : str
        The run directory, which the generated file is written to
    polaris_config : str or None
        The user's ``polaris_config_file``, if there is one
    wall_time : str
        The requested wall-clock time, or an empty string for none
    dry_run : bool
        Whether to report the file that would be written without writing
        it

    Returns
    -------
    config_file : str or None
        The config file to pass on with ``-f``
    """
    if not wall_time:
        return polaris_config

    config_file = os.path.join(run_dir, 'polaris_benchmark.cfg')
    if dry_run:
        return config_file

    # configparser rather than appending text, since polaris reads the
    # file strictly and a [job] section may already be in it
    config = configparser.ConfigParser(interpolation=None)
    if polaris_config is not None:
        config.read(polaris_config)
    if not config.has_section('job'):
        config.add_section('job')
    config.set('job', 'wall_time', wall_time)
    with open(config_file, 'w') as handle:
        config.write(handle)
    return config_file


def _get_run_dir(work_base, baseline, test, setup_command):
    """
    Get the deterministic run directory for this pair of sides.

    The suite name comes first, since it is what tells one benchmark from
    another: two benchmarks of the *same* pair of commits are set up under
    different suite names and must not share a work directory.  Without
    it, benchmarking one branch two ways on one day silently overwrote the
    first run's test work directory, build directory, manifest and log.

    The ``opts-<key>`` that names the baseline is deliberately left out.
    A baseline is a cache, so reusing one that was built with a different
    config file or load script would be wrong; a run directory is only
    where this run's output lands, and the suite name already tells one
    from another.

    Every repository that differs appears next.  Benchmarking a submodule
    change holds polaris fixed on both sides, so the polaris hashes alone
    would be the same for every such benchmark run on a given day.
    """
    date = datetime.now().strftime('%Y%m%d')
    parts = [
        date,
        polaris_run.get_suite_name(setup_command),
        f'polaris-{baseline.polaris_sha[:7]}-{test.polaris_sha[:7]}',
    ]
    baseline_shas = baseline.compare_shas
    test_shas = test.compare_shas
    for key in gitrepo.SUBMODULE_PATHS:
        baseline_sha = baseline_shas[key]
        test_sha = test_shas[key]
        if baseline_sha != test_sha:
            parts.append(f'{key}-{baseline_sha[:7]}-{test_sha[:7]}')
    name = _slugify('-'.join(parts))
    if baseline.dirty or test.dirty:
        name = f'dirty-{name}'
    return os.path.join(work_base, 'runs', name)


def _get_baseline_dir(
    work_base,
    baseline,
    setup_command,
    polaris_config,
    shared_component_path=None,
):
    """
    Get the cacheable baseline work directory.

    The name covers everything a baseline depends on, so that a baseline
    is only ever reused by a benchmark it is actually comparable with.
    That is polaris plus the submodule the model is built from: a
    submodule that is never built cannot change the results, so bumping
    the hash polaris pins for it should not throw a baseline away.  The
    manifest still records every hash, and the one-variable guardrail
    still compares all of them.

    Every hash is labelled with what it names, since the reader would
    otherwise have to know the order they are written in.

    A dirty baseline is never cached or reused, since it cannot be
    reproduced from the recorded commit hashes.
    """
    shas = baseline.compare_shas
    setup_key = _setup_key(
        setup_command, polaris_config, baseline, shared_component_path
    )
    parts = [
        polaris_run.get_suite_name(setup_command),
        baseline.model,
        f'opts-{setup_key}',
        f'polaris-{shas["polaris"][:7]}',
    ]
    key = gitrepo.MODEL_SUBMODULES.get(baseline.model)
    if key is not None and shas[key]:
        parts.append(f'{key}-{shas[key][:7]}')
    name = '_'.join(parts)
    if baseline.dirty:
        name = f'dirty_{name}_{datetime.now().strftime("%Y%m%d%H%M%S")}'
    return os.path.join(work_base, 'baselines', name)


def _setup_key(
    setup_command, polaris_config, baseline, shared_component_path=None
):
    """
    Get a short hash of what a baseline depends on besides the commits.

    ``polaris setup`` always reports the suite name ``custom``, so the
    tasks only appear here.  The polaris config file and the load script
    change the results too, so they are included as well.

    A shared ``component_path`` is included because the driver cannot tell
    what was built there: the directory names the submodule hash the
    baseline pins, but the executable found at ``component_path`` was
    built by whoever created it.  Pointing somewhere else therefore has to
    invalidate the cached baseline rather than silently reuse it.
    """
    parts = [
        ' '.join(setup_command.split()),
        os.path.basename(baseline.load_script),
    ]
    if shared_component_path is not None:
        parts.append(shared_component_path)
    if polaris_config is not None:
        with open(polaris_config) as handle:
            parts.append(handle.read())
    text = '\n'.join(parts)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:7]


def _slugify(name):
    """Get a filesystem-safe version of a run directory name."""
    return re.sub(r'[^A-Za-z0-9_.-]', '-', name)


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
        print(f'  model:   {side["model"]}')
        # an uninitialized submodule is still pinned by the polaris
        # commit, and that pin is what the guardrail compares, so report
        # it rather than leaving the side looking as though it differs
        for key in sorted(
            set(side['submodule_shas']) | set(side['pinned_shas'])
        ):
            sha = side['submodule_shas'].get(key, '')
            suffix = ''
            if not sha:
                sha = side['pinned_shas'].get(key, '')
                suffix = ' (pinned, not checked out)'
            if sha:
                print(f'  {key}: {sha[:7]}{suffix}')
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
    for name in ['baseline', 'test']:
        side = manifest[name]
        if side['untracked']:
            listed = '\n'.join(f'    {entry}' for entry in side['untracked'])
            print('')
            print(
                f'Note: the {name} worktree carries untracked files outside '
                f'the polaris\n  package, which nothing a task runs reads, '
                f'so they do not make it dirty:\n{listed}'
            )

    if manifest['component_path'] is not None:
        print('')
        print(
            f'Both sides share one build at\n  '
            f'{manifest["component_path"]}\nbuilt from\n  '
            f'{manifest["baseline"]["component_branch_path"]}\nPolaris '
            f'builds the model only when it does not find one there, so '
            f'the first side set up builds it and the second reuses it.  '
            f'The test worktree needs no submodule of its own.'
        )
    print('')
    print(f'differing:    {", ".join(manifest["differing_repos"])}')
    print(f'reproducible: {manifest["reproducible"]}')
    print(f'baseline dir: {manifest["baseline_dir"]}')
    print(f'test dir:     {manifest["test_dir"]}')


if __name__ == '__main__':
    main()
