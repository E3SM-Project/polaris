"""
Turn a Polaris suite run into a CDash ``Test.xml`` alongside an Omega build
that CTest recorded, so the two can be submitted together.

CTest writes ``Testing/TAG`` and ``Testing/<tag>/Build.xml`` when Omega is
built through ``omega_ctest.py --dashboard``.  Polaris writes one log per
task under ``case_outputs/`` with a ``POLARIS TASK: PASS`` or ``FAIL`` line
(and ``POLARIS BASELINE:`` when a baseline was compared).  This module reads
the logs and writes ``Test.xml`` into the same tag directory, copying the
``<Site>`` attributes from ``Build.xml`` so CDash files both under one build.
"""

import glob
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


def task_results(log_dir):
    """
    Read the result of each Polaris task from its log.

    Parameters
    ----------
    log_dir : str
        The ``case_outputs`` directory of a suite run

    Returns
    -------
    results : list of dict
        For each task, in name order: ``name``, ``passed`` and ``output``
    """
    results = []
    for log_file in sorted(glob.glob(os.path.join(log_dir, '*.log'))):
        name = os.path.splitext(os.path.basename(log_file))[0]
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            output = _ANSI_ESCAPE.sub('', f.read())

        passed = 'POLARIS TASK: PASS' in output
        if 'POLARIS BASELINE:' in output:
            passed = passed and 'POLARIS BASELINE: PASS' in output

        results.append({'name': name, 'passed': passed, 'output': output})
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
        ET.SubElement(
            test, 'FullCommandLine'
        ).text = f'polaris serial {result["name"]}'
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


def _cdash_time(seconds):
    return time.strftime('%b %d %H:%M %Z', time.localtime(seconds))
