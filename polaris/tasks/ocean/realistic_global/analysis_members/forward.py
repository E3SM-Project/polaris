from polaris.tasks.ocean.realistic_global.forward import (
    Forward as RealisticGlobalForward,
)

#: The durations of the runs: a ``short`` one whose length is set per mesh,
#: and a ``1_year`` one that writes the monthly output the ocean analysis
#: reads
DURATIONS = ['short', '1_year']

# The one-year run starts on 0001-01-01, so the first monthly file is written
# at the start of February.  Omega names a file for the time it is written,
# which for a time mean is the end of the month it averages
# (E3SM-Project/Omega#554), so the twelve files covering year 1 are named
# 0001-02 through 0002-01.  The monthly snapshots are named the same way, for
# the instant they are taken.
START_YEAR = 1
MONTHS = 12


class Forward(RealisticGlobalForward):
    """
    A forward run for the ``analysis_members`` tasks, with the time steps
    and momentum viscosities of its mesh

    The ``short`` run writes daily output and global statistics.  The
    ``1_year`` run layers ``monthly_output.yaml`` over the shared
    ``realistic_global`` yaml file, replacing the ``History`` stream with
    monthly snapshots, turning on the ``MonthlyAverages`` and ``MOC``
    analysis groups and writing restarts monthly, which Omega requires of a
    run with a monthly reduction.  It supports only Omega, since the ocean
    analysis reads only Omega output.

    Attributes
    ----------
    duration : str
        The duration of the run, one of ``DURATIONS``
    """

    def __init__(
        self,
        component,
        indir,
        mesh_name,
        mpaso_id,
        omega_id,
        ncells,
        duration,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step goes in

        mesh_name : str
            The name of the mesh, e.g. ``'QU.240km'``

        mpaso_id : int
            The ID of the MPAS-Ocean initial condition in the Polaris input
            database

        omega_id : int
            The ID of the Omega initial condition in the Polaris input
            database

        ncells : int
            The approximate number of cells in the mesh, used to constrain
            resources

        duration : str
            The duration of the run, one of ``DURATIONS``
        """
        # the time steps, the short run's duration and the MOC bins come
        # from the per-mesh config options in setup()
        replacements = {
            'time_integrator': 'SplitExplicitRK2',
            'output_interval': '0001_00:00:00',
            'output_freq': '1',
        }
        if duration == 'short':
            replacements['output_freq_units'] = 'days'
            output_filenames = None
        elif duration == '1_year':
            # Omega's TimeInterval parser understands only DDDD_HH:MM:SS, so
            # the duration is given in days: 365 on the No Leap calendar
            replacements['run_duration'] = '0365_00:00:00'
            replacements['output_freq_units'] = 'months'
            # every monthly file is declared as an output so that a run
            # whose analysis groups did not write is reported as a missing
            # output rather than found later by the analysis
            output_filenames = []
            for template in [
                'output/ocn.hist.{year:04d}-{month:02d}.nc',
                'monthly_means_1MonthTimeStats.{year:04d}-{month:02d}.nc',
                'moc_1MonthTimeStats.{year:04d}-{month:02d}.nc',
            ]:
                output_filenames.extend(_monthly_filenames(template))
        else:
            raise ValueError(f'Unexpected duration {duration}')

        super().__init__(
            component=component,
            package='polaris.tasks.ocean.realistic_global',
            indir=indir,
            mesh_name=mesh_name,
            mpaso_id=mpaso_id,
            omega_id=omega_id,
            ncells=ncells,
            replacements=replacements,
            output_filenames=output_filenames,
        )
        self.duration = duration
        if duration == '1_year':
            self.stream_dirs.append('output')

    def setup(self):
        """
        Fill in the per-mesh time steps, the short run's duration and the
        MOC bins from the config options, add the monthly output of the
        one-year run over the shared yaml file, then the per-mesh momentum
        viscosities
        """
        if (
            self.duration == '1_year'
            and self.config.get('ocean', 'model') != 'omega'
        ):
            raise ValueError(
                'The 1_year analysis_members task runs only Omega, since the '
                'ocean analysis reads only Omega output.'
            )
        section = self.config['analysis_members']
        self.replacements['dt'] = section.get('dt')
        self.replacements['btr_dt'] = section.get('btr_dt')
        if self.duration == 'short':
            self.replacements['run_duration'] = section.get(
                'short_run_duration'
            )
        else:
            self.replacements['moc_num_bins'] = section.getint('moc_num_bins')
        super().setup()
        if self.duration == '1_year':
            self.add_yaml_file(
                package='polaris.tasks.ocean.realistic_global.'
                'analysis_members',
                yaml='monthly_output.yaml',
                template_replacements=self.replacements,
            )
        options = {
            'config_mom_del2': section.getfloat('mom_del2'),
            'config_mom_del4': section.getfloat('mom_del4'),
        }
        self.add_model_config_options(options=options, config_model='ocean')


def _monthly_filenames(template):
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
