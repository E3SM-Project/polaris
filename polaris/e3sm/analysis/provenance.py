import glob
import os
import re
import shlex
import shutil
from datetime import datetime

from lxml import etree

from polaris.analysis.page import PageStep
from polaris.e3sm.analysis.case import MODELS

#: The subdirectory of the step's work directory the files are copied into
FILES_DIRNAME = 'files'

#: The files of the run directory published, if the run has them: each
#: model's namelist and streams, the driver's namelist and maps, and
#: Albany's input
RUN_FILES = (
    [f'{model}_in' for model in MODELS]
    + [streams for _, streams in MODELS.values()]
    + ['drv_in', 'seq_maps.rc', 'albany_input.yaml']
)

#: The files CIME writes in the build directory that record the source
#: and the environment it was built in, and how the code section labels
#: those it only links to
BUILD_FILES = {
    'GIT_DESCRIBE': None,
    'GIT_LOG': None,
    'GIT_DIFF': None,
    'GIT_STATUS': 'git status',
    'GIT_SUBMODULE_STATUS': 'submodules',
    'GIT_REMOTE': 'remotes',
    'build_environment.txt': 'build modules and libraries',
}

#: The files of the case directory published, if the case has them, and
#: how the case section labels those it only links to
CASE_FILES = {
    'replay.sh': None,
    'README.case': 'README.case',
    'software_environment.txt': 'run modules and libraries',
}

#: The environment dumps CIME writes, of which only the loaded modules and
#: the variables :py:data:`PUBLISHED_VARIABLES` matches are published
ENVIRONMENT_FILES = ['build_environment.txt', 'software_environment.txt']

#: The environment variables published from an environment dump: the
#: compilers and the locations of the libraries the build uses.  The rest
#: of the shell's environment is left out, since it can hold tokens and
#: addresses that a public page must not show.
PUBLISHED_VARIABLES = re.compile(
    r'(CC|CXX|FC|F77|F90|MPICC|MPICXX|MPIFC|MPIF77|MPIF90'
    r'|(ADIOS2|Albany|ALBANY|Blosc2|BLOSC2|HDF5|Kokkos|KOKKOS|MKL|MOAB'
    r'|NETCDF|NETCDF_C|NETCDF_FORTRAN|PETSC|PNETCDF|SZ|TBB|Trilinos'
    r'|TRILINOS|ZFP)_?(ROOT|PATH|DIR))'
)

#: What looks like a secret in a published file: a token, secret or
#: password, in any case, or a secure-shell or session variable, in the
#: upper case of an environment variable, given a value.  The case matters
#: for the latter because ``ssh`` is also the sea-surface height in
#: MPAS-Ocean's options.  A published file that has one stops the step
#: rather than being published.
SECRET = re.compile(
    r'\b(?:\w*(?i:token|secret|passw(?:or)?d)\w*'
    r'|[A-Z0-9_]*(?:SSH_[A-Z0-9_]+|SESSION_ID)[A-Z0-9_]*)\s*[=:]'
)

#: The user and password in a URL, as in ``https://user:token@host``
_URL_CREDENTIALS = re.compile(r'(://)[^/@\s]+@')

#: The libraries whose location the build environment records
LIBRARIES = {'Albany': 'Albany_ROOT', 'Trilinos': 'Trilinos_ROOT'}

#: The namelist each component's user namelist changes, in the run
#: directory
USER_NAMELIST_TARGETS = {'cpl': 'drv_in'}

#: A restart's date in the driver's restart pointer
_RESTART_DATE = re.compile(r'\.r\.(\d{4,}-\d\d-\d\d-\d{5})\.nc')


class CaseProvenance(PageStep):
    """
    A step that records what made an E3SM case's run on a page of its own:
    the code and libraries it was built from, how the case was created and
    changed, the options set in its user namelists, the files under
    ``SourceMods``, and copies of the namelists, streams and other inputs
    the models read

    The files are copied when the step runs, so they are those of the
    run's most recent job.

    Attributes
    ----------
    case : polaris.e3sm.analysis.case.E3smCase
        The case
    """

    def __init__(self, component, subdir, case):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        case : polaris.e3sm.analysis.case.E3smCase
            The case
        """
        super().__init__(
            component=component,
            name='provenance',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
            page_name='provenance',
            page_title='Provenance of the E3SM run',
        )
        self.case = case

    def run(self):
        """
        Gather the case's provenance and write the page
        """
        case = self.case
        files_path = self.work_path(FILES_DIRNAME)
        if os.path.isdir(files_path):
            shutil.rmtree(files_path)
        os.makedirs(files_path)

        build_dir = case.get_value('EXEROOT')
        hrefs = dict()
        for directory, names in [
            (build_dir, list(BUILD_FILES)),
            (case.case_dir, list(CASE_FILES)),
            (case.run_dir, RUN_FILES),
        ]:
            for name in names:
                href = self._copy(os.path.join(directory, name), name)
                if href is not None:
                    hrefs[name] = href
        user_namelists = sorted(
            glob.glob(os.path.join(case.case_dir, 'user_nl_*'))
        )
        for filename in user_namelists:
            name = os.path.basename(filename)
            hrefs[name] = self._copy(filename, name)

        self._add_code(build_dir, hrefs)
        self._add_case(hrefs)
        self._add_user_namelists(user_namelists, hrefs)
        self._add_source_mods()
        self._add_files(hrefs)
        self.write_page()

    def _copy(self, source, name):
        """Copy a file the page publishes, returning its link, or ``None``
        if there is no such file"""
        if not os.path.isfile(source):
            return None
        local = os.path.join(FILES_DIRNAME, name)
        if name in ENVIRONMENT_FILES:
            text = summarize_environment(source)
        else:
            with open(source, errors='replace') as original:
                text = _URL_CREDENTIALS.sub(r'\1', original.read())
        match = SECRET.search(text)
        if match is not None:
            raise ValueError(
                f'{source} has what looks like a secret, '
                f'"{match.group(0)}", so the provenance page would publish '
                f'it.  Leave the file out or remove what it holds.'
            )
        with open(self.work_path(local), 'w') as copy:
            copy.write(text)
        # a published name ending in .txt is shown by a browser rather than
        # downloaded
        published_name = name if name.endswith('.txt') else f'{name}.txt'
        return self.page.add_file(local, published_name)

    def _add_code(self, build_dir, hrefs):
        """The section on the code the run was built from"""
        case = self.case
        entries: list[tuple] = []
        describe = _read_first_line(os.path.join(build_dir, 'GIT_DESCRIBE'))
        if describe is not None:
            entries.append(('E3SM version', describe, hrefs['GIT_DESCRIBE']))
        log = _read_first_line(os.path.join(build_dir, 'GIT_LOG'))
        if log is not None:
            entries.append(('E3SM commit', log, hrefs['GIT_LOG']))
        diff = os.path.join(build_dir, 'GIT_DIFF')
        if os.path.isfile(diff):
            changes = 'yes' if has_local_changes(diff) else 'none'
            entries.append(('local changes', changes, hrefs['GIT_DIFF']))
        entries.append(('E3SM source', _value(case, 'SRCROOT')))
        environment = os.path.join(build_dir, 'build_environment.txt')
        if os.path.isfile(environment):
            roots = read_environment(environment)
            for library, variable in LIBRARIES.items():
                if variable in roots:
                    entries.append((library, roots[variable]))
        for label, name in [
            ('machine', 'MACH'),
            ('compiler', 'COMPILER'),
            ('MPI library', 'MPILIB'),
        ]:
            entries.append((label, _value(case, name)))
        entries += _links(BUILD_FILES, hrefs)
        self.page.add_section(
            'Code',
            text=(
                'As CIME recorded it when the model was built.  The '
                'Polaris that made this page is in the footer.'
            ),
            entries=entries,
        )

    def _add_case(self, hrefs):
        """The section on how the case was created and changed"""
        case = self.case
        entries = [
            (label, _value(case, name))
            for label, name in [
                ('case', 'CASE'),
                ('compset', 'COMPSET'),
                ('grid', 'GRID'),
                ('run type', 'RUN_TYPE'),
                ('start date', 'RUN_STARTDATE'),
            ]
        ]
        entries += [
            ('case directory', case.case_dir),
            ('run directory', case.run_dir),
        ]
        entries += _links(CASE_FILES, hrefs)
        self.page.add_section('Case', entries=entries)

        replay = os.path.join(case.case_dir, 'replay.sh')
        if not os.path.isfile(replay):
            self.page.add_section(
                'Commands',
                text=(
                    'The case has no replay.sh, so the commands that created '
                    'and changed it are not known.'
                ),
            )
            return
        commands = read_case_commands(replay)
        self.page.add_section(
            'Commands',
            text=(
                'The commands that created and changed the case, as its '
                'replay.sh records them.'
            ),
            entries=[('replay.sh', 'the whole file', hrefs['replay.sh'])],
            code='\n'.join(commands),
        )
        variables = xmlchange_variables(commands)
        if variables:
            entries_by_id = read_case_entries(case.case_dir)
            self.page.add_section(
                'Case variables changed',
                text=(
                    'Each case variable an xmlchange above set, with its '
                    'value now, giving each where the jobs or components '
                    'have different values.'
                ),
                table={
                    'columns': ['variable', 'value'],
                    'rows': [
                        [name, _current_value(case, name, entries_by_id)]
                        for name in variables
                    ],
                },
            )

    def _add_user_namelists(self, user_namelists, hrefs):
        """A section for the options set in each user namelist"""
        for filename in user_namelists:
            name = os.path.basename(filename)
            component = name[len('user_nl_') :]
            options = read_user_namelist(filename)
            if not options:
                continue
            target = USER_NAMELIST_TARGETS.get(component, f'{component}_in')
            groups = dict()
            namelist = os.path.join(self.case.run_dir, target)
            if os.path.isfile(namelist):
                groups = read_namelist_groups(namelist)
            self.page.add_section(
                f'Options set in {name}',
                text=(
                    'The options set explicitly; some may have the value '
                    'they would have had anyway.'
                ),
                entries=[(name, 'the whole file', hrefs[name])],
                table={
                    'columns': ['namelist group', 'option', 'value'],
                    'rows': [
                        [groups.get(option.lower(), ''), option, value]
                        for option, value in options
                    ],
                },
            )

    def _add_source_mods(self):
        """The section on the files under SourceMods"""
        rows = []
        pattern = os.path.join(self.case.case_dir, 'SourceMods', '*', '*')
        for source in sorted(glob.glob(pattern)):
            name = os.path.basename(source)
            if name == 'README' or not os.path.isfile(source):
                continue
            directory = os.path.basename(os.path.dirname(source))
            href = self._copy(source, f'SourceMods_{directory}_{name}')
            rows.append([directory, (name, href)])
        if rows:
            self.page.add_section(
                'SourceMods',
                text='The files the case puts in place of the defaults.',
                table={'columns': ['directory', 'file'], 'rows': rows},
            )

    def _add_files(self, hrefs):
        """The section listing the files the models read"""
        restart = read_restart_date(
            os.path.join(self.case.run_dir, 'rpointer.drv')
        )
        copied = datetime.now().astimezone().isoformat(timespec='minutes')
        text = f'Copied from the run directory at {copied}'
        if restart is not None:
            text = f'{text}, when its latest restart was for {restart}'
        entries = [
            (name, os.path.join(self.case.run_dir, name), hrefs[name])
            for name in RUN_FILES
            if name in hrefs
        ]
        self.page.add_section(
            'Files the models read', text=f'{text}.', entries=entries
        )


def read_case_commands(filename):
    """
    Read the commands that created and changed a case from its
    ``replay.sh``

    Parameters
    ----------
    filename : str
        The case's ``replay.sh``

    Returns
    -------
    commands : list of str
        The commands, in order, without comments, blank lines and the
        script's own setup
    """
    commands = []
    with open(filename) as script:
        for line in script:
            line = line.strip()
            if not line or line.startswith('#') or line == 'set -e':
                continue
            commands.append(line)
    return commands


def xmlchange_variables(commands):
    """
    Get the case variables that ``xmlchange`` commands set

    Parameters
    ----------
    commands : list of str
        The commands, as :py:func:`read_case_commands` returns them

    Returns
    -------
    variables : list of str
        The variables, each once, in the order they were first set
    """
    variables: dict = dict()
    for command in commands:
        try:
            words = shlex.split(command)
        except ValueError:
            continue
        if not words or os.path.basename(words[0]) != 'xmlchange':
            continue
        arguments = words[1:]
        if '--id' in arguments:
            index = arguments.index('--id')
            if index + 1 < len(arguments):
                variables[arguments[index + 1]] = None
            continue
        for argument in arguments:
            if argument.startswith('-') or '=' not in argument:
                continue
            for pair in argument.split(','):
                name = pair.split('=', 1)[0]
                if re.fullmatch(r'[A-Za-z_]\w*', name):
                    variables[name] = None
    return list(variables)


def read_user_namelist(filename):
    """
    Read the options a user namelist sets

    Parameters
    ----------
    filename : str
        A ``user_nl_*`` file

    Returns
    -------
    options : list of tuple
        Each option and its value, as written, in order
    """
    options = []
    with open(filename) as namelist:
        for line in namelist:
            line = _strip_comment(line).strip()
            if '=' not in line:
                continue
            option, value = line.split('=', 1)
            options.append((option.strip(), value.strip()))
    return options


def read_namelist_groups(filename):
    """
    Find the group of each option in a namelist

    Parameters
    ----------
    filename : str
        A namelist, such as ``mpaso_in``

    Returns
    -------
    groups : dict
        The group of each option, keyed by the option in lower case
    """
    groups = dict()
    group = None
    with open(filename) as namelist:
        for line in namelist:
            line = _strip_comment(line).strip()
            if line.startswith('&'):
                group = line[1:].split()[0]
            elif line == '/':
                group = None
            elif group is not None and '=' in line:
                option = line.split('=', 1)[0].strip().lower()
                groups[option] = group
    return groups


def read_environment(filename):
    """
    Read the environment variables a build environment records

    Parameters
    ----------
    filename : str
        CIME's ``build_environment.txt``

    Returns
    -------
    variables : dict
        The value of each variable, as ``NAME=value`` lines give them
    """
    variables = dict()
    with open(filename) as environment:
        for line in environment:
            match = re.match(r'([A-Za-z_]\w*)=(.*)$', line.rstrip('\n'))
            if match is not None:
                variables[match.group(1)] = match.group(2)
    return variables


def read_case_entries(case_dir):
    """
    Read every value of each case variable, with the group or component
    it is for, since a variable such as ``JOB_WALLCLOCK_TIME`` has a value
    for each job and one such as ``NTASKS`` for each component

    Parameters
    ----------
    case_dir : str
        The case directory

    Returns
    -------
    entries : dict
        A list of ``(group, value)`` for each variable, as the
        ``env_*.xml`` files give them, unexpanded, where the group is the
        component for a value given per component
    """
    entries: dict = dict()
    for filename in sorted(glob.glob(os.path.join(case_dir, 'env_*.xml'))):
        for entry in etree.parse(filename).iter('entry'):
            values = entries.setdefault(entry.attrib['id'], [])
            value = entry.attrib.get('value')
            if value is None:
                for child in entry.iter('value'):
                    if 'compclass' in child.attrib:
                        values.append(
                            (child.attrib['compclass'], child.text or '')
                        )
                continue
            group = entry.getparent()
            group_id = None if group is None else group.attrib.get('id')
            values.append((group_id, value))
    return entries


def summarize_environment(filename):
    """
    Summarize an environment dump CIME wrote, keeping only what is safe to
    publish: the loaded modules and the variables
    :py:data:`PUBLISHED_VARIABLES` matches

    Parameters
    ----------
    filename : str
        ``build_environment.txt`` or ``software_environment.txt``

    Returns
    -------
    text : str
        The summary
    """
    modules: list = []
    variables: list = []
    in_modules = False
    with open(filename, errors='replace') as environment:
        for line in environment:
            line = line.rstrip('\n')
            if line.startswith('Currently Loaded Modules'):
                in_modules = True
            elif in_modules and not line.strip():
                in_modules = False
            if in_modules:
                modules.append(line)
                continue
            match = re.match(r'([A-Za-z_]\w*)=(.*)$', line)
            if match is not None and PUBLISHED_VARIABLES.fullmatch(
                match.group(1)
            ):
                variables.append(line)
    lines = [
        f'# From {os.path.basename(filename)}: the loaded modules, the '
        f'compilers and the',
        '# libraries; the rest of the environment is left out.',
        '',
    ]
    lines += modules + [''] + sorted(variables)
    return '\n'.join(lines) + '\n'


def has_local_changes(filename):
    """
    Whether CIME's ``GIT_DIFF`` shows changes, rather than only the names
    of the submodules it went through

    Parameters
    ----------
    filename : str
        The build's ``GIT_DIFF``

    Returns
    -------
    changed : bool
        Whether any file differs from its commit
    """
    with open(filename) as diff:
        return any(line.startswith('diff ') for line in diff)


def read_restart_date(filename):
    """
    Read the date of a run's latest restart from the driver's restart
    pointer

    Parameters
    ----------
    filename : str
        The run directory's ``rpointer.drv``

    Returns
    -------
    date : str or None
        The date, such as ``0006-01-01-00000``, or ``None`` if there is no
        pointer
    """
    if not os.path.isfile(filename):
        return None
    with open(filename) as pointer:
        match = _RESTART_DATE.search(pointer.read())
    return None if match is None else match.group(1)


def _read_first_line(filename):
    """The first line of a file, or ``None`` if there is no such file"""
    if not os.path.isfile(filename):
        return None
    with open(filename) as text:
        return text.readline().strip()


def _strip_comment(line):
    """A namelist line without its comment, leaving a ``!`` in quotes"""
    quote = None
    for index, character in enumerate(line):
        if quote is not None:
            if character == quote:
                quote = None
        elif character in '\'"':
            quote = character
        elif character == '!':
            return line[:index]
    return line


def _links(files, hrefs):
    """Entries linking to the copied files that have a label"""
    return [
        (label, 'copy', hrefs[name])
        for name, label in files.items()
        if label is not None and name in hrefs
    ]


def _current_value(case, name, entries_by_id):
    """A case variable's value now, giving each where it has several"""
    entries = entries_by_id.get(name, [])
    if not entries and '_' in name:
        # a variable given per component, such as NTASKS_GLC
        base, component = name.rsplit('_', 1)
        entries = [
            (group, value)
            for group, value in entries_by_id.get(base, [])
            if group == component
        ]
    values = {value for _, value in entries}
    if len(values) > 1:
        return '; '.join(f'{group}: {value}' for group, value in entries)
    value = _value(case, name)
    if value == '—' and values:
        return values.pop()
    return value


def _value(case, name):
    """A case variable's value, or a dash if the case does not have it"""
    try:
        return case.get_value(name)
    except KeyError:
        return '—'
