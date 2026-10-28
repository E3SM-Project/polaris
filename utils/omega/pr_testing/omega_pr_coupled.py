"""
The coupled CIME tests the Omega PR template asks for: set them up and
build them with ``create_test``, and summarize their ``TestStatus`` files
"""

import os
import re
import shlex
import subprocess
from typing import List, Optional, Tuple

import pr_test_setup as setup_tools
from pr_test_report import ReportError
from pr_test_rows import Row
from pr_test_setup import Job

from polaris.config import PolarisConfigParser
from polaris.job import is_job_active

#: the coupled tests a row runs by default: the exact-restart and PE-count
#: tests, with debug flags, that Omega's developer guide recommends for
#: every PR
COUPLED_TESTS = [
    'ERS_D.T62_oQU240.COMEGA-IAF',
    'PEM_D.T62_oQU240.COMEGA-IAF',
]

#: the script in a machine's E3SM-Unified directory that loads the Python
#: environment CIME commands need (with ``pyyaml`` for Omega's buildnml)
CIME_ENV_SCRIPT = 'load_latest_cime_env.sh'

#: where each case is set up and built, relative to the E3SM tree
CREATE_TEST_DIR = os.path.join('cime', 'scripts')

_TEST_STATUS = 'TestStatus'

_STATUS_LINE = re.compile(r'^(PASS|FAIL|PEND|DIFF)\s+(\S+)\s+(\S+)')


def get_cime_env_script(machine: str) -> str:
    """
    The script that loads the environment CIME commands need on a machine

    Parameters
    ----------
    machine : str
        The machine

    Returns
    -------
    script : str
        ``load_latest_cime_env.sh`` in the machine's E3SM-Unified directory
    """
    config = PolarisConfigParser()
    config.add_from_package('mache.machines', f'{machine}.cfg')
    if not config.has_option('e3sm_unified', 'base_path'):
        raise setup_tools.SetupError(
            f'mache does not know where E3SM-Unified is on {machine}, so '
            f'there is no {CIME_ENV_SCRIPT} to run CIME with.'
        )
    base_path = config.get('e3sm_unified', 'base_path')
    return os.path.join(base_path, CIME_ENV_SCRIPT)


def get_case_dir(coupled_dir: str, test: str, row: Row, test_id: str) -> str:
    """The case directory ``create_test`` makes for a test"""
    return os.path.join(
        coupled_dir, f'{test}.{row.machine}_{row.compiler}.{test_id}'
    )


def set_up_coupled_tests(
    row: Row,
    tree: str,
    coupled_dir: str,
    test_id: str,
    tests: List[str],
) -> Tuple[List[str], List[Job]]:
    """
    Set up and build the coupled tests with ``create_test --no-run``, in a
    clean login shell with the machine's CIME environment loaded, unless an
    earlier setup already did

    Parameters
    ----------
    row : pr_test_rows.Row
        The row

    tree : str
        The E3SM (Omega) tree to test, with all of its submodules

    coupled_dir : str
        Where the cases, their builds and their runs go

    test_id : str
        The id ``create_test`` appends to each case's name

    tests : list of str
        The tests, without the machine and compiler

    Returns
    -------
    case_dirs : list of str
        Each test's case directory

    jobs : list of pr_test_setup.Job
        A job for each case that built
    """
    env_script = get_cime_env_script(row.machine)
    case_dirs = [
        get_case_dir(coupled_dir, test, row, test_id) for test in tests
    ]
    new_tests = [
        test
        for test, case_dir in zip(tests, case_dirs, strict=True)
        if not os.path.exists(case_dir)
    ]
    if new_tests:
        os.makedirs(coupled_dir, exist_ok=True)
        args = ['./create_test'] + new_tests
        args.extend(['--machine', row.machine, '--compiler', row.compiler])
        args.extend(['--test-id', test_id, '--no-run'])
        args.extend(['--test-root', coupled_dir])
        args.extend(['--output-root', coupled_dir])
        scripts_dir = os.path.join(tree, CREATE_TEST_DIR)
        print(
            f'\nRunning in {scripts_dir}, with {env_script} sourced in a '
            f'clean login shell:\n  {shlex.join(args)}\n',
            flush=True,
        )
        # create_test exits with an error when a build fails, which the
        # case's TestStatus records for the report.  The shell starts clean
        # since the Polaris environment's variables, such as METIS_ROOT,
        # would change CIME's build.
        subprocess.run(
            setup_tools.get_clean_shell_command(env_script, scripts_dir, args),
            env=setup_tools.get_login_env(),
            check=False,
        )

    jobs = []
    for test, case_dir in zip(tests, case_dirs, strict=True):
        if phase_status(case_dir, 'MODEL_BUILD') == 'PASS':
            jobs.append(
                Job(
                    name=test,
                    work_dir=case_dir,
                    script='case.submit',
                    env_script=env_script,
                )
            )
        else:
            print(
                f'{test} did not build, so it will not be submitted; see '
                f'{os.path.join(case_dir, _TEST_STATUS)}',
                flush=True,
            )
    return case_dirs, jobs


def phase_status(case_dir: str, phase: str) -> Optional[str]:
    """A phase's status in a case's ``TestStatus``, if it has one"""
    for status, _, name in _read_status(case_dir):
        if name == phase:
            return status
    return None


def summarize_coupled_tests(
    case_dirs: List[str], jobs: List[Job], system: str
) -> Tuple[bool, str, str]:
    """
    Summarize the coupled tests from their ``TestStatus`` files

    Parameters
    ----------
    case_dirs : list of str
        Each test's case directory

    jobs : list of pr_test_setup.Job
        The cases' jobs

    system : str
        The machine's job scheduler

    Returns
    -------
    passed : bool
        Whether every test passed

    cell : str
        The row's cell in the table

    details : str
        Each test's ``TestStatus``, pasted unchanged
    """
    job_ids = {job.work_dir: job.job_id for job in jobs}
    failed = []
    sections = []
    for case_dir in case_dirs:
        name = os.path.basename(case_dir)
        lines = _read_status(case_dir)
        if not lines:
            raise ReportError(
                f'the coupled test {name} has no {_TEST_STATUS}; it was not '
                f'set up'
            )
        job_id = job_ids.get(case_dir)
        if job_id is None and phase_status(case_dir, 'MODEL_BUILD') == 'PASS':
            raise ReportError(
                f'the coupled test {name} was built but not submitted'
            )
        if job_id is not None and is_job_active(job_id, system):
            raise ReportError(
                f'the coupled test {name} has not finished (job {job_id})'
            )
        phases = [phase for status, _, phase in lines if status != 'PASS']
        if not phases and 'RUN' not in {phase for _, _, phase in lines}:
            # a job that ended before it started the test
            phases.append('RUN')
        if phases:
            failed.append(f'{name.split(".")[0]} ({", ".join(phases)})')
        with open(os.path.join(case_dir, _TEST_STATUS)) as f:
            text = f.read().strip()
        sections.append(f'`{name}`\n\n```\n{text}\n```')

    total = len(case_dirs)
    if failed:
        cell = f'{len(failed)} of {total} failed: {", ".join(failed)}'
    else:
        cell = f'{total} of {total} passed'
    details = '### Coupled CIME tests\n\n' + '\n\n'.join(sections)
    return not failed, cell, details


def _read_status(case_dir):
    """The status, test and phase of each line of a case's TestStatus"""
    path = os.path.join(case_dir, _TEST_STATUS)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [
            match.groups()
            for match in (_STATUS_LINE.match(line) for line in f)
            if match is not None
        ]
