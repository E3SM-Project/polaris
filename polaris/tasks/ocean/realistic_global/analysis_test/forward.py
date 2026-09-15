from polaris.tasks.ocean.realistic_global.forward import (
    Forward as RealisticGlobalForward,
)

# the cached initial conditions and cell counts of the realistic global
# meshes, as in polaris.tasks.ocean.realistic_global
MESH_INFO = {
    'QU.240km': dict(
        mpaso_id=151209, omega_id=260807, ncells=7153, dt='00:10:00'
    ),
}

# The run starts on 0001-01-01 and lasts a year, so the first monthly file
# is written at the start of February.  Omega names a file for the time it
# is written, which for a time mean is the end of the month it averages
# (E3SM-Project/Omega#554), so the twelve files covering year 1 are named
# 0001-02 through 0002-01.  The monthly snapshots are named the same way,
# for the instant they are taken.
START_YEAR = 1
MONTHS = 12


class Forward(RealisticGlobalForward):
    """
    A one-year forward run whose Omega streams write the monthly output the
    ocean analysis reads

    The step layers its own yaml file over the shared ``realistic_global``
    one, replacing the ``History`` stream with monthly snapshots, turning on
    the ``MonthlyAverages`` and ``MOC`` analysis groups and writing restarts
    monthly, which Omega requires of a run with a monthly reduction.  Only
    Omega is supported, since the analysis reads only Omega output.
    """

    def __init__(self, component, subdir, mesh_name):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        mesh_name : str
            The name of the mesh, e.g. ``'QU.240km'``
        """
        mesh_info = MESH_INFO[mesh_name]
        replacements = {
            'time_integrator': 'RungeKutta4',
            # Omega's TimeInterval parser understands only DDDD_HH:MM:SS, so
            # the duration is given in days: 365 on the No Leap calendar
            'run_duration': '0365_00:00:00',
            'dt': mesh_info['dt'],
            # the MPAS-Ocean output stream, which is not used
            'output_interval': '0001_00:00:00',
            'output_freq': '1',
            'output_freq_units': 'months',
        }
        # every monthly file is declared as an output so that a run whose
        # analysis groups did not write is reported as a missing output
        # rather than found later by the analysis
        output_filenames = []
        for template in [
            'output/ocn.hist.{year:04d}-{month:02d}.nc',
            'monthly_means_1MonthTimeStats.{year:04d}-{month:02d}.nc',
            'moc_1MonthTimeStats.{year:04d}-{month:02d}.nc',
        ]:
            output_filenames.extend(_monthly_filenames(template))
        super().__init__(
            component=component,
            package='polaris.tasks.ocean.realistic_global',
            subdir=subdir,
            mesh_name=mesh_name,
            mpaso_id=mesh_info['mpaso_id'],
            omega_id=mesh_info['omega_id'],
            ncells=mesh_info['ncells'],
            replacements=replacements,
            output_filenames=output_filenames,
        )
        self.stream_dirs.append('output')

    def setup(self):
        """
        Add this step's yaml file over the shared one
        """
        if self.config.get('ocean', 'model') != 'omega':
            raise ValueError(
                'The analysis_test task runs only Omega, since the ocean '
                'analysis reads only Omega output.'
            )
        super().setup()
        self.add_yaml_file(
            package='polaris.tasks.ocean.realistic_global.analysis_test',
            yaml='forward.yaml',
            template_replacements=self.replacements,
        )


def _monthly_filenames(template):
    """
    Get the names of the monthly files the run writes, which are named for
    the month after the one they cover; see the note on ``START_YEAR``

    Parameters
    ----------
    template : str
        The file name, with ``{year}`` and ``{month}`` in it

    Returns
    -------
    filenames : list of str
        The file names, relative to the step's work directory
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
