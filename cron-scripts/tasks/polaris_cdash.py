#!/usr/bin/env python3
"""
Nightly task: run the ``omega_nightly`` suite against the Omega submodule
and submit the results to CDash.

The build goes through ``omega_ctest.py --dashboard --build_only`` so CTest
records it (in a job of its own with ``--build_in_job``), the suite's steps
run at the same time with ``polaris parallel`` in the job ``polaris suite``
writes, and the task results are turned into
``Test.xml`` beside the recorded build before the dashboard script's submit
stage sends both.  A build that fails is submitted on its own.  The build name,
``polaris_omega_nightly-<compiler>``, is what CDash's group rules file into
``Polaris_Omega_Nightly_Tests``.
"""

import glob
import os
import pickle
import shutil
import subprocess
import sys
import time

from cdash import site_attributes, tag_dir, task_results, write_test_xml
from common import (
    load_omega_ctest,
    machine_config,
    omega_ctest_command,
    parse_task_args,
    run,
    run_omega_ctest,
    submit_and_wait,
)

SUITE = 'omega_nightly'


def main():
    args = parse_task_args(
        f'Run the {SUITE} suite against the Omega submodule and submit the '
        'results to CDash'
    )
    omega_ctest = load_omega_ctest(args.polaris_root)

    work_dir = os.path.join(
        args.cron_root, 'tasks', 'polaris_cdash', args.compiler
    )
    os.makedirs(work_dir, exist_ok=True)

    build_name = f'polaris_{SUITE}-{args.compiler}'
    branch = os.path.join(args.polaris_root, 'e3sm_submodules', 'Omega')
    command = omega_ctest_command(
        polaris_root=args.polaris_root,
        args=args,
        branch=branch,
        build_name=build_name,
        # --cdash_submit with --build_only submits only a failed build; a
        # good one goes to CDash below, with the suite's results
        extra=['--build_only', '--cdash_submit'],
    )
    run_omega_ctest(
        command, work_dir, args, job_name=f'polaris_cdash_{args.compiler}'
    )
    build_dir = os.path.join(
        work_dir, 'build_omega', f'build_{args.machine}_{args.compiler}'
    )

    suite_dir = os.path.join(work_dir, 'suite')
    if os.path.isdir(suite_dir):
        shutil.rmtree(suite_dir)
    run(
        [
            'polaris',
            'suite',
            '-c',
            'ocean',
            '-t',
            SUITE,
            '--model',
            'omega',
            '-w',
            suite_dir,
            '-p',
            build_dir,
            '--parallel',
        ]
    )

    config = machine_config(args.machine)
    job_script = os.path.join(suite_dir, f'job_script.{SUITE}.sh')
    start_time = time.time()
    try:
        submit_and_wait(job_script, config)
    except subprocess.CalledProcessError as error:
        # a failed task fails the job; the results still go to CDash
        print(f'The suite job failed: {error}')
    end_time = time.time()

    results = task_results(suite_dir, SUITE, _step_paths(suite_dir))
    tag = tag_dir(build_dir)
    test_xml = write_test_xml(
        results=results,
        tag_dir=tag,
        attributes=site_attributes(tag),
        start_time=start_time,
        end_time=end_time,
    )
    failed = [result['name'] for result in results if not result['passed']]
    print(
        f'\n{len(results) - len(failed)} of {len(results)} tasks passed; '
        f'wrote {test_xml}'
    )

    dashboard = omega_ctest.DashboardOptions(
        site=args.site,
        build_name=build_name,
        model=args.model,
        submit_url=omega_ctest.CDASH_SUBMIT_URL,
        submit=True,
    )
    ctest_command = omega_ctest.dashboard_ctest_command(
        stage='submit', branch=branch, build_dir=build_dir, dashboard=dashboard
    )
    run(
        ['bash', '-c', f'source ./omega_env.sh && {ctest_command}'],
        cwd=build_dir,
    )

    if len(results) == 0:
        print(f'No task results found in {suite_dir}/{SUITE}_results.json')
        sys.exit(1)
    if failed:
        print('Failed tasks:')
        for name in failed:
            print(f'  {name}')
        job_outputs = glob.glob(os.path.join(suite_dir, f'polaris_{SUITE}.o*'))
        for job_output in job_outputs:
            print(f'Job output: {job_output}')
        sys.exit(1)


def _step_paths(suite_dir):
    """
    The path of each step of each task, keyed by the task's path and then
    the step's name.

    ``polaris parallel`` names each step's log for the step's path, and a
    shared step's path is not under its task's, so this comes from the suite
    that ``polaris suite`` pickled.
    """
    with open(os.path.join(suite_dir, f'{SUITE}.pickle'), 'rb') as f:
        suite = pickle.load(f)
    step_paths = {}
    for task in suite['tasks'].values():
        step_paths[task.path] = {
            name: step.path for name, step in task.steps.items()
        }
    return step_paths


if __name__ == '__main__':
    main()
