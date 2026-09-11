#!/usr/bin/env python3
"""
Run the nightly tasks for one machine.

For each compiler in ``machines/<machine>.cfg`` this deploys the Polaris
environment, then runs each task under it with the compiler's load script
sourced.  Everything is logged under ``<cron_root>/logs/<date>/``; nothing
is printed unless something failed, so that cron's mail carries only
failures.

Standard library only: this runs before any Polaris environment exists.
"""

import argparse
import configparser
import datetime
import glob
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TAIL_LINES = 30


def main():
    parser = argparse.ArgumentParser(
        description='Run the nightly Polaris cron tasks for one machine'
    )
    parser.add_argument(
        '-m', '--machine', required=True, help='The machine name'
    )
    parser.add_argument(
        '--dry_run',
        action='store_true',
        help='Log what would run without running it',
    )
    parser.add_argument(
        '--site',
        help='The site name shown on CDash (default: the machine); a test '
        'run should use its own so it does not replace the nightly rows',
    )
    args = parser.parse_args()
    machine = args.machine
    dry_run = args.dry_run

    cron_root = os.environ['POLARIS_CRON_ROOT']
    polaris_root = os.environ.get('POLARIS_ROOT', os.path.dirname(HERE))
    config = read_machine_config(machine)

    log_dir = make_log_dir(
        cron_root, config.getint('cron', 'keep_logs_days', fallback=30)
    )
    # pixi's cache must not be on /tmp: on Perlmutter login nodes /tmp is
    # RAM and counts against a per-user memory cap (#630).  Forced rather
    # than defaulted, because a login profile may export the /tmp path.
    os.environ['PIXI_CACHE_DIR'] = os.path.join(cron_root, 'pixi_cache')

    tasks = _list(config.get('cron', 'tasks'))
    account = config.get('cron', 'account', fallback=None)
    build_jobs = config.get('cron', 'build_jobs', fallback=None)
    compilers = _list(config.get('cron', 'compilers'))

    log = Log(os.path.join(log_dir, 'nightly.log'))
    log.write(f'python {sys.version.split()[0]} at {sys.executable}')
    log.write(f'machine {machine}, compilers {", ".join(compilers)}')
    log.write(f'tasks {", ".join(tasks)}')
    log.write(f'PIXI_CACHE_DIR {os.environ["PIXI_CACHE_DIR"]}')

    # deploy.py bootstraps the newest mache and rattler-build, which can write
    # a package index an older pixi cannot read, so bring pixi up to date
    # first.  A failed update (no route to GitHub, say) is logged and the
    # night goes on with the pixi it has.
    update_pixi(polaris_root, log_dir, log, dry_run)

    failures = []
    for index, compiler in enumerate(compilers):
        # one fresh environment per night; later compilers update it
        deploy = ['./deploy.py', '--machine', machine, '--compiler', compiler]
        if index == 0:
            deploy.append('--recreate')
        deploy_log = os.path.join(log_dir, f'deploy_{compiler}.log')
        if not run_logged(deploy, polaris_root, deploy_log, log, dry_run):
            failures.append((f'deploy ({compiler})', deploy_log))
            continue

        try:
            load_script = find_load_script(polaris_root, machine, compiler)
        except FileNotFoundError as error:
            if not dry_run:
                log.write(str(error))
                failures.append((f'deploy ({compiler})', deploy_log))
                continue
            load_script = f'load_polaris_{machine}_{compiler}_<mpi>.sh'

        for task in tasks:
            task_script = os.path.join(HERE, 'tasks', f'{task}.py')
            command = (
                f'source "{load_script}" && python "{task_script}" '
                f'--cron_root "{cron_root}"'
            )
            if account is not None:
                command = f'{command} --account {account}'
            if args.site is not None:
                command = f'{command} --site {args.site}'
            if build_jobs is not None:
                command = f'{command} --build_jobs {build_jobs}'
            task_log = os.path.join(log_dir, f'{task}_{compiler}.log')
            if not run_logged(
                ['bash', '-l', '-c', command],
                cron_root,
                task_log,
                log,
                dry_run,
            ):
                failures.append((f'{task} ({compiler})', task_log))

    log.write('done' if not failures else f'{len(failures)} failure(s)')
    if dry_run:
        print(f'Dry run; see {log.filename}')
    if failures:
        report_failures(machine, failures)
        sys.exit(1)


def update_pixi(polaris_root, log_dir, log, dry_run):
    """
    Update pixi to the current release if it is older, the way deploy.py
    finds it: on the path, or else in ``~/.pixi/bin``.
    """
    pixi = shutil.which('pixi')
    if pixi is None:
        pixi = os.path.expanduser('~/.pixi/bin/pixi')
    if not os.path.isfile(pixi):
        log.write(f'no pixi to update at {pixi}; deploy.py will say so')
        return
    pixi_log = os.path.join(log_dir, 'pixi_self_update.log')
    if not run_logged(
        [pixi, 'self-update'], polaris_root, pixi_log, log, dry_run
    ):
        log.write(
            'pixi self-update failed; continuing with the pixi installed'
        )
    if not dry_run:
        version = subprocess.run(
            [pixi, '--version'], capture_output=True, text=True, check=False
        ).stdout.strip()
        log.write(f'{version} at {pixi}')


def read_machine_config(machine):
    """
    Read ``machines/<machine>.cfg``.
    """
    filename = os.path.join(HERE, 'machines', f'{machine}.cfg')
    if not os.path.isfile(filename):
        raise FileNotFoundError(f'No cron config for {machine}: {filename}')
    config = configparser.ConfigParser()
    config.read(filename)
    return config


def make_log_dir(cron_root, keep_days):
    """
    Make today's log directory and remove those older than ``keep_days``.
    """
    logs = os.path.join(cron_root, 'logs')
    today = datetime.date.today()
    log_dir = os.path.join(logs, today.isoformat())
    os.makedirs(log_dir, exist_ok=True)

    for old in glob.glob(os.path.join(logs, '????-??-??')):
        try:
            date = datetime.date.fromisoformat(os.path.basename(old))
        except ValueError:
            continue
        if (today - date).days > keep_days:
            shutil.rmtree(old, ignore_errors=True)
    return log_dir


def find_load_script(polaris_root, machine, compiler):
    """
    The load script ``deploy.py`` wrote for this compiler.
    """
    pattern = os.path.join(
        polaris_root, f'load_polaris_{machine}_{compiler}_*.sh'
    )
    matches = glob.glob(pattern)
    if len(matches) != 1:
        raise FileNotFoundError(
            f'Expected one load script matching {pattern}, '
            f'found {len(matches)}'
        )
    return matches[0]


def run_logged(command, cwd, log_file, log, dry_run=False):
    """
    Run a command, writing its timestamped output to ``log_file``.

    Returns
    -------
    ok : bool
        Whether the command succeeded
    """
    start = time.time()
    log.write(f'running {" ".join(command)}')
    log.write(f'   in {cwd}, logging to {log_file}')
    if dry_run:
        return True
    with open(log_file, 'w', encoding='utf-8') as f:
        f.write(f'[{_now()}] {" ".join(command)}\n[{_now()}] in {cwd}\n')
        # python children write to a pipe here, so without this their output
        # would arrive in blocks rather than as it happens
        env = dict(os.environ, PYTHONUNBUFFERED='1')
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors='replace',
        )
        assert process.stdout is not None
        for line in process.stdout:
            f.write(f'[{_now()}] {line}')
        returncode = process.wait()
        f.write(f'[{_now()}] exit {returncode}\n')
    minutes = (time.time() - start) / 60
    log.write(f'   exit {returncode} after {minutes:.0f} min')
    return returncode == 0


def report_failures(machine, failures):
    """
    Print what failed and the end of each log; cron mails this.
    """
    print(f'Polaris nightly on {machine}: {len(failures)} failure(s)\n')
    for what, log_file in failures:
        print(f'{what} failed; see {log_file}')
    for _, log_file in failures:
        print(f'\n===== last {TAIL_LINES} lines of {log_file} =====')
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        sys.stdout.write(''.join(lines[-TAIL_LINES:]))


class Log:
    """
    The orchestrator's own log, one timestamped line per event.
    """

    def __init__(self, filename):
        self.filename = filename

    def write(self, message):
        with open(self.filename, 'a', encoding='utf-8') as f:
            f.write(f'[{_now()}] {message}\n')


def _list(value):
    return [item.strip() for item in value.split(',') if item.strip()]


def _now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


if __name__ == '__main__':
    main()
