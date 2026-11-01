import glob
import os
import re

from lxml import etree

from polaris.streams import find_stream_files, get_stream, read_file

#: For each model, its component's name in the short-term archive and its
#: streams file in the run directory
MODELS = {
    'mpaso': ('ocn', 'streams.ocean'),
    'mali': ('glc', 'streams.landice'),
}

#: A reference to an environment variable, as CIME writes it, or to another
#: case variable
_REFERENCE = re.compile(r'\$ENV\{(\w+)\}|\$\{(\w+)\}|\$(\w+)')


class E3smCase:
    """
    An E3SM case, read from the XML files in its case directory without
    CIME

    Attributes
    ----------
    case_dir : str
        The absolute path to the case directory
    """

    def __init__(self, case_dir):
        """
        Read the case's variables

        Parameters
        ----------
        case_dir : str
            The case directory, holding ``env_run.xml`` and the other
            ``env_*.xml`` files
        """
        self.case_dir = os.path.abspath(case_dir)
        filenames = sorted(glob.glob(os.path.join(self.case_dir, 'env_*.xml')))
        if not filenames:
            raise FileNotFoundError(
                f'{self.case_dir} has no env_*.xml files, so it is not an '
                f'E3SM case directory.'
            )
        self._values = dict()
        for filename in filenames:
            for entry in etree.parse(filename).iter('entry'):
                value = entry.attrib.get('value')
                if value is not None:
                    self._values[entry.attrib['id']] = value

    def get_value(self, name):
        """
        Get a case variable, with references to other case variables and to
        environment variables expanded

        Parameters
        ----------
        name : str
            The name of the case variable, such as ``RUNDIR``

        Returns
        -------
        value : str
            The expanded value
        """
        return self._expand(name, seen=[])

    @property
    def case_name(self):
        """The case's name"""
        return self.get_value('CASE')

    @property
    def run_dir(self):
        """The case's run directory"""
        return self.get_value('RUNDIR')

    @property
    def archive_dir(self):
        """The root of the case's short-term archive"""
        return self.get_value('DOUT_S_ROOT')

    @property
    def landice_mode(self):
        """MALI's mode: ``prognostic``, ``static`` or ``data``"""
        return self.get_value('MALI_PROGNOSTIC_MODE').lower()

    def read_streams(self, model):
        """
        Read the streams file a model read in the run directory

        Parameters
        ----------
        model : {'mpaso', 'mali'}
            The model

        Returns
        -------
        tree : lxml.etree
            The model's streams
        """
        _, streams_filename = _model(model)
        return read_file(os.path.join(self.run_dir, streams_filename))

    def find_stream_files(self, model, stream_name):
        """
        Find the files a model's stream wrote, in the short-term archive or
        in the run directory

        Parameters
        ----------
        model : {'mpaso', 'mali'}
            The model

        stream_name : str
            The name of the stream, such as
            ``timeSeriesStatsMonthlyOutput``

        Returns
        -------
        stream_files : list of polaris.streams.StreamFile
            The files found, in order of their dates, taken from the archive
            where a file is in both
        """
        component, _ = _model(model)
        stream = get_stream(self.read_streams(model), stream_name)
        directories = [
            os.path.join(self.archive_dir, component, 'hist'),
            self.run_dir,
        ]
        return find_stream_files(
            stream.attrib['filename_template'], directories
        )

    def find_logs(self, component):
        """
        Find a component's logs, compressed or not, in the short-term
        archive or in the run directory

        Parameters
        ----------
        component : str
            The component whose logs to find, such as ``cpl`` for the
            coupler

        Returns
        -------
        logs : list of str
            The logs found, sorted by name, which sorts them by the job and
            time that wrote them.  A log in both places is taken from the
            archive.
        """
        found: dict = dict()
        for directory in [
            os.path.join(self.archive_dir, 'logs'),
            self.run_dir,
        ]:
            pattern = os.path.join(directory, f'{component}.log.*')
            for path in glob.glob(pattern):
                found.setdefault(os.path.basename(path), path)
        return [found[name] for name in sorted(found)]

    def _expand(self, name, seen):
        """Expand a case variable, guarding against references in a loop"""
        if name in seen:
            raise ValueError(
                f'The case variables {" -> ".join(seen + [name])} refer to '
                f'each other in a loop.'
            )
        if name in self._values:
            value = self._values[name]
        elif name in os.environ:
            return os.environ[name]
        else:
            raise KeyError(
                f'{name} is neither a variable of the case in '
                f'{self.case_dir} nor an environment variable.'
            )

        return _REFERENCE.sub(
            lambda match: self._replace(match, seen + [name]), value
        )

    def _replace(self, match, seen):
        """Replace one reference in a case variable's value"""
        env_name, name, bare_name = match.groups()
        if env_name is not None:
            if env_name not in os.environ:
                raise KeyError(
                    f'The case in {self.case_dir} refers to the environment '
                    f'variable {env_name}, which is not set.'
                )
            return os.environ[env_name]
        return self._expand(name or bare_name, seen)


def _model(model):
    """Get a model's archive component and streams file"""
    if model not in MODELS:
        raise ValueError(
            f'Unknown model {model}; the models are {", ".join(MODELS)}.'
        )
    return MODELS[model]
