"""
Check netCDF files for CF compliance with the CF checker (``cfchecker``)
"""

import glob
import os
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from polaris.step import Step

# the CF tables the checker needs, as (config option prefix, local filename)
CF_TABLES: List[Tuple[str, str]] = [
    ('standard_name_table', 'cf-standard-name-table.xml'),
    ('area_type_table', 'cf-area-type-table.xml'),
    ('region_name_table', 'cf-region-name-table.xml'),
]


def add_cf_tables(step: 'Step') -> None:
    """
    Add the CF standard-name, area-type and region-name tables as inputs of
    a step.  They are downloaded at the versions pinned in the ``[cf]``
    config section into the ``cf/tables`` database, so a table is fetched
    once per machine rather than once per run.

    Parameters
    ----------
    step : polaris.Step
        The step that will run a CF check
    """
    config = step.config
    for option, filename in CF_TABLES:
        version = config.get('cf', f'{option}_version')
        url = config.get('cf', f'{option}_url').format(version=version)
        base, ext = os.path.splitext(filename)
        step.add_input_file(
            filename=filename,
            target=f'{base}.{version}{ext}',
            database='tables',
            database_component='cf',
            url=url,
        )


def resolve_cf_check_files(patterns: List[str], work_dir: str) -> List[str]:
    """
    Resolve the file patterns registered for a CF check to the files to
    check.  A pattern with wildcards stands for a series of files with the
    same metadata (a time series from one output stream), so only its first
    match is checked.  A pattern with no match is kept so the check can
    report it as missing.

    Parameters
    ----------
    patterns : list of str
        Filenames or glob patterns, relative to ``work_dir`` unless absolute

    work_dir : str
        The step's work directory

    Returns
    -------
    filenames : list of str
        The files to check, relative to ``work_dir`` where possible
    """
    filenames: List[str] = []
    for pattern in patterns:
        path = os.path.join(work_dir, pattern)
        if glob.has_magic(pattern):
            matches = sorted(glob.glob(path))
            if matches:
                path = matches[0]
        filename = os.path.relpath(path, work_dir)
        if filename.startswith('..'):
            filename = path
        if filename not in filenames:
            filenames.append(filename)
    return filenames


def check_cf_compliance(
    filenames: List[str], work_dir: str
) -> List[Dict[str, Any]]:
    """
    Run the CF checker on each file.  A file passes when the checker
    reports no errors; warnings and informational messages are recorded
    but do not fail it.

    Parameters
    ----------
    filenames : list of str
        The files to check, relative to ``work_dir`` unless absolute

    work_dir : str
        The step's work directory, where the CF tables were linked

    Returns
    -------
    results : list of dict
        One entry per file with the keys ``filename``, ``passed``,
        ``errors`` (a list of strings), ``warnings`` (an int) and
        ``report`` (the full text of the checker's output)
    """
    # cfchecker pulls in cfunits and udunits, which nothing else in the
    # framework needs, so it is imported only when a check runs
    from cfchecker.cfchecks import CFChecker, CFVersion, FatalCheckerError

    tables = {
        option: os.path.join(work_dir, filename)
        for option, filename in CF_TABLES
    }

    results: List[Dict[str, Any]] = []
    for filename in filenames:
        path = os.path.join(work_dir, filename)
        if not os.path.exists(path):
            results.append(
                dict(
                    filename=filename,
                    passed=False,
                    errors=['file not found'],
                    warnings=0,
                    report=f'{filename}: file not found\n',
                )
            )
            continue
        # a new checker per file, because an auto-detected CF version
        # sticks to the checker object after its first file
        checker = CFChecker(
            cfStandardNamesXML=tables['standard_name_table'],
            cfAreaTypesXML=tables['area_type_table'],
            cfRegionNamesXML=tables['region_name_table'],
            version=CFVersion(),
            silent=True,
        )
        try:
            checker.checker(path)
        except FatalCheckerError:
            pass
        results.append(_summarize(filename, checker.results))
    return results


def _summarize(filename: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce the checker's nested results to one entry for the file."""
    errors: List[str] = []
    warnings = 0
    lines = [f'{filename}:']
    sections = [('global', raw['global'])]
    sections.extend(raw['variables'].items())
    for name, messages in sections:
        for message in messages['FATAL'] + messages['ERROR']:
            errors.append(f'{name}: {message}')
        warnings += len(messages['WARN'])
        for category in ('FATAL', 'ERROR', 'WARN', 'INFO'):
            for message in messages[category]:
                lines.append(f'  {category} {name}: {message}')
    return dict(
        filename=filename,
        passed=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        report='\n'.join(lines) + '\n',
    )
