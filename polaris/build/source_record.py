import os
from typing import Any, Dict, Optional

# the records that polaris/build/build_omega.template and
# polaris/build/build_mpas_ocean.template write into the build directory
SOURCE_RECORD_FILENAMES = ('omega_source.txt', 'mpas_ocean_source.txt')


def read_source_record(build_dir: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Read the record of the source that Polaris built a model from.

    Polaris's build scripts write the record into the build directory before
    configuring the build, so it names the commit that was built even if the
    source tree has moved since.

    Parameters
    ----------
    build_dir : str, optional
        The build directory of Omega or MPAS-Ocean

    Returns
    -------
    record : dict, optional
        The record, with the source tree's path (``source``), its full hash
        (``hash``), the output of ``git describe`` (``describe``), whether
        the build started from an empty build directory (``clean_build``)
        and its last five first-parent commits (``log``), or ``None`` if the
        build directory has no record
    """
    if not build_dir:
        return None

    for filename in SOURCE_RECORD_FILENAMES:
        path = os.path.join(build_dir, filename)
        if os.path.exists(path):
            return _parse_source_record(path)

    return None


def _parse_source_record(path: str) -> Optional[Dict[str, Any]]:
    record: Dict[str, Any] = {
        'source': None,
        'hash': None,
        'describe': None,
        'clean_build': False,
        'log': [],
    }
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    in_log = False
    for line in lines:
        if in_log and line.startswith(' '):
            record['log'].append(line.strip())
            continue
        in_log = False
        key, separator, value = line.partition(':')
        if separator == '':
            continue
        key = key.strip()
        value = value.strip()
        if key == 'log':
            in_log = True
        elif key == 'clean_build':
            record['clean_build'] = value == 'true'
        elif key in record:
            record[key] = value or None

    return record
