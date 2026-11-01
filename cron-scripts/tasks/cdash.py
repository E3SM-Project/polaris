"""
Turn a Polaris suite run into a CDash ``Test.xml`` alongside an Omega build
that CTest recorded, so the two can be submitted together.

CTest writes ``Testing/TAG`` and ``Testing/<tag>/Build.xml`` when Omega is
built through ``omega_ctest.py --dashboard``.  Polaris writes each task's
result to ``<suite>_results.json`` and its output under ``case_outputs/``:
one log per task from ``polaris serial``, one per step from
``polaris parallel``.  This module reads both and writes ``Test.xml`` into
the same tag directory, copying the ``<Site>`` attributes from ``Build.xml``
so CDash files both under one build.
"""

import json
import os
import re
import time
import xml.etree.ElementTree as ET

_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def tag_dir(build_dir):
    """
    The ``Testing/<tag>`` directory of a build that CTest recorded.

    Parameters
    ----------
    build_dir : str
        The Omega build directory

    Returns
    -------
    tag_dir : str
        The directory holding ``Build.xml`` and, after
        :py:func:`write_test_xml`, ``Test.xml``
    """
    tag_path = os.path.join(build_dir, 'Testing', 'TAG')
    with open(tag_path, 'r', encoding='utf-8') as f:
        tag = f.readline().strip()
    if tag == '':
        raise ValueError(f'{tag_path} is empty; was the build recorded?')
    return os.path.join(build_dir, 'Testing', tag)


def site_attributes(tag_dir):
    """
    The attributes of the ``<Site>`` element in ``Build.xml``.

    Parameters
    ----------
    tag_dir : str
        The ``Testing/<tag>`` directory

    Returns
    -------
    attributes : dict
        ``BuildName``, ``BuildStamp``, ``Name`` and the rest
    """
    build_xml = os.path.join(tag_dir, 'Build.xml')
    site = ET.parse(build_xml).getroot()
    if site.tag != 'Site':
        raise ValueError(f'{build_xml} does not start with a <Site> element')
    return dict(site.attrib)


def task_results(suite_dir, suite, step_paths):
    """
    Read the result of each Polaris task in a suite run, with its output.

    Parameters
    ----------
    suite_dir : str
        The work directory of the suite

    suite : str
        The name of the suite

    step_paths : dict of dict
        The path of each step relative to ``suite_dir``, keyed by its task's
        path and then its name, for finding the logs of tasks whose steps ran
        with ``polaris parallel``

    Returns
    -------
    results : list of dict
        For each task, in the order the suite lists them: ``name``,
        ``passed`` and ``output``.  The list is empty if the suite wrote no
        results file.
    """
    results_file = os.path.join(suite_dir, f'{suite}_results.json')
    if not os.path.exists(results_file):
        return []
    with open(results_file, 'r', encoding='utf-8') as f:
        tasks = json.load(f)['tasks']

    results = []
    for task in tasks:
        path = task['path']
        if task['log'] is not None:
            logs = [task['log']]
        else:
            paths = step_paths.get(path, {})
            logs = [
                _step_log(paths.get(name, f'{path}/{name}'))
                for name in task['steps_to_run'] or []
            ]
        results.append(
            {
                # the name the task's log had before the suite ran its steps
                # in parallel, so CDash keeps each test's history
                'name': path.replace('/', '_'),
                'passed': task['status'] == 'pass',
                'output': _read_logs(suite_dir, logs),
            }
        )
    return results


def write_test_xml(results, tag_dir, attributes, start_time, end_time):
    """
    Write ``Test.xml`` for a suite run into a CTest tag directory.

    Parameters
    ----------
    results : list of dict
        From :py:func:`task_results`

    tag_dir : str
        The ``Testing/<tag>`` directory to write into

    attributes : dict
        The ``<Site>`` attributes, from :py:func:`site_attributes`

    start_time : float
        When the suite started, in seconds since the epoch

    end_time : float
        When the suite finished, in seconds since the epoch

    Returns
    -------
    test_xml : str
        The path to the file written
    """
    site = ET.Element('Site', attrib=attributes)
    testing = ET.SubElement(site, 'Testing')
    ET.SubElement(testing, 'StartDateTime').text = _cdash_time(start_time)
    ET.SubElement(testing, 'StartTestTime').text = str(int(start_time))

    test_list = ET.SubElement(testing, 'TestList')
    for result in results:
        ET.SubElement(test_list, 'Test').text = f'./{result["name"]}'

    for result in results:
        status = 'passed' if result['passed'] else 'failed'
        test = ET.SubElement(testing, 'Test', Status=status)
        ET.SubElement(test, 'Name').text = result['name']
        ET.SubElement(test, 'Path').text = '.'
        ET.SubElement(test, 'FullName').text = f'./{result["name"]}'
        ET.SubElement(test, 'FullCommandLine').text = 'polaris parallel'
        measurements = ET.SubElement(test, 'Results')
        completion = ET.SubElement(
            measurements,
            'NamedMeasurement',
            type='text/string',
            name='Completion Status',
        )
        ET.SubElement(completion, 'Value').text = 'Completed'
        measurement = ET.SubElement(measurements, 'Measurement')
        ET.SubElement(measurement, 'Value').text = result['output']

    ET.SubElement(testing, 'EndDateTime').text = _cdash_time(end_time)
    ET.SubElement(testing, 'EndTestTime').text = str(int(end_time))

    test_xml = os.path.join(tag_dir, 'Test.xml')
    ET.ElementTree(site).write(
        test_xml, encoding='UTF-8', xml_declaration=True
    )
    return test_xml


def _step_log(step_path):
    """Where ``polaris parallel`` writes a step's log."""
    return os.path.join('case_outputs', f'{step_path.replace("/", "_")}.log')


def _read_logs(suite_dir, logs):
    """Read a task's logs, each headed by its name if there are several."""
    outputs = []
    for log in logs:
        log_path = os.path.join(suite_dir, log)
        if not os.path.exists(log_path):
            outputs.append(f'{log} was not written; the step did not run.')
            continue
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            output = _ANSI_ESCAPE.sub('', f.read())
        if len(logs) > 1:
            output = f'==> {log} <==\n{output}'
        outputs.append(output)
    if not outputs:
        return 'The task wrote no logs.'
    return '\n'.join(outputs)


def _cdash_time(seconds):
    return time.strftime('%b %d %H:%M %Z', time.localtime(seconds))
