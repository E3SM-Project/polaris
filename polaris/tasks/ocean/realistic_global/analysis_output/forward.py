from typing import List

from polaris.tasks.ocean.realistic_global.forward import (
    Forward,
    InitialCondition,
)

#: The monthly files the run writes, relative to the step's work directory
MONTHLY_FILE_TEMPLATES = [
    'output/ocn.hist.{year:04d}-{month:02d}.nc',
    'monthly_means_1MonthTimeStats.{year:04d}-{month:02d}.nc',
    'moc_1MonthTimeStats.{year:04d}-{month:02d}.nc',
]

# The run starts on 0001-01-01, so the first monthly file is written at the
# start of February.  Omega names a file for the time it is written, which for
# a time mean is the end of the month it averages (E3SM-Project/Omega#554), so
# the twelve files covering year 1 are named 0001-02 through 0002-01.  The
# monthly snapshots are named the same way, for the instant they are taken.
START_YEAR = 1
MONTHS = 12


class AnalysisOutputForward(Forward):
    """
    A one-year Omega run that writes what the ocean analysis reads

    The run is an ordinary realistic_global forward step, with
    ``monthly_output.yaml`` layered over the forward step's yaml.  That file
    replaces the ``History`` stream with monthly snapshots, turns on the
    ``MonthlyAverages`` and ``MOC`` analysis groups and writes restarts
    monthly, which Omega requires of a run with a monthly reduction.  Every
    monthly file is declared as an output, so that a run whose analysis groups
    did not write is reported as a missing output rather than found later by
    the analysis.  The number of MOC latitude bins is the ``moc_num_bins``
    option in the mesh's ``[analysis_output]`` config section.  The step
    supports only Omega, since the ocean analysis reads only Omega output.
    """

    def __init__(
        self,
        component,
        init_condition: InitialCondition,
        subdir: str,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        init_condition : InitialCondition
            The source of the model input files

        subdir : str
            The subdirectory for the step
        """
        output_filenames: List[str] = []
        for template in MONTHLY_FILE_TEMPLATES:
            output_filenames.extend(get_monthly_filenames(template))
        super().__init__(
            component=component,
            init_condition=init_condition,
            name='forward',
            subdir=subdir,
            output_filenames=output_filenames,
        )
        self.stream_dirs.append('output')

    def setup(self):
        """
        Raise unless the model is Omega, then set up the step
        """
        if self.config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The 1_year analysis_output task runs only Omega, since the '
                'ocean analysis reads only Omega output.'
            )
        super().setup()

    def dynamic_model_config(self, at_setup):
        """
        Add the monthly output over the forward step's own model config

        Parameters
        ----------
        at_setup : bool
            Whether this is being run during setup of the step, as opposed to
            at run time.
        """
        super().dynamic_model_config(at_setup=at_setup)
        self.add_yaml_file(
            'polaris.tasks.ocean.realistic_global.analysis_output',
            'monthly_output.yaml',
            template_replacements=dict(
                moc_num_bins=self.config.getint(
                    'analysis_output', 'moc_num_bins'
                )
            ),
        )


def get_monthly_filenames(template: str) -> List[str]:
    """
    Get the names of the monthly files the one-year run writes, which are
    named for the month after the one they cover; see the note on
    ``START_YEAR``

    Parameters
    ----------
    template : str
        The file name, with ``{year}`` and ``{month}`` in it

    Returns
    -------
    filenames : list of str
        The file names
    """
    year = START_YEAR
    month = 1
    filenames = []
    for _ in range(MONTHS):
        month += 1
        if month > 12:
            month = 1
            year += 1
        filenames.append(template.format(year=year, month=month))
    return filenames
