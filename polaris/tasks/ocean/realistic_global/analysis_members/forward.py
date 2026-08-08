import os

from polaris.ocean.model import OceanModelStep


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


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case
    """

    def __init__(
        self,
        component,
        package,
        mesh_name,
        mpaso_id,
        omega_id,
        ncells=None,
        name='forward',
        indir=None,
        subdir=None,
        update_eos=False,
        output_filenames=None,
        ntasks=None,
        min_tasks=None,
        options=None,
        replacements=None,
        validate_vars=None,
        check_properties=None,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        output_filenames : list of str, optional
            The files the run writes, relative to the step's work directory,
            each declared as an output; ``output.nc`` by default
        """
        if output_filenames is None:
            output_filenames = ['output.nc']
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            subdir=subdir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            update_eos=update_eos,
            openmp_threads=1,
            graph_target=f'graph.info.{mpaso_id}',
        )
        self.mesh_name = mesh_name
        self.mpaso_id = mpaso_id
        self.omega_id = omega_id
        self.ncells = ncells
        self.replacements = replacements
        self.package = package
        # the directories Omega's streams write into, which Omega does not
        # create itself; a subclass whose streams write elsewhere adds to it
        self.stream_dirs = ['restart']
        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        if options is not None:
            for config_model in options:
                self.add_model_config_options(
                    options=options[config_model], config_model=config_model
                )

        # TODO replace validate_vars with all model-specific state vars
        for output_filename in output_filenames:
            self.add_output_file(
                filename=output_filename,
                validate_vars=validate_vars,
                check_properties=check_properties,
            )

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        config = self.config
        model = config.get('ocean', 'model')
        # This attribute is used by OceanModelStep
        target_location = f'realistic_global/{model}/{self.mesh_name}'
        self.target_location = target_location
        super().setup()
        # TODO: remove as soon as Omega no longer hard-codes this file
        input_filename = f'ocean.{self.mesh_name}.{self.mpaso_id}'
        if model == 'omega':
            # Currently, only TEOS-10 is supported
            eos_type = 'teos10'
            input_filename = f'{input_filename}.{eos_type}.{self.omega_id}.nc'
            self.add_input_file(
                target=input_filename,
                filename='mesh.nc',
                database=target_location,
            )
            self.add_input_file(
                target=input_filename,
                filename='vert_coord.nc',
                database=target_location,
            )
            self.add_input_file(
                target=input_filename,
                filename='init.nc',
                database=target_location,
            )
        else:
            self.replacements['time_integrator'] = 'split_explicit'
            input_filename = f'{input_filename}.zerovel.nc'
            self.add_input_file(
                target=input_filename,
                filename='mesh.nc',
                database=target_location,
            )
            self.add_input_file(
                target=input_filename,
                filename='init.nc',
                database=target_location,
            )
        self.add_yaml_file(
            package=self.package,
            yaml='forward.yaml',
            template_replacements=self.replacements,
        )
        self._make_stream_dirs()

    def runtime_setup(self):
        """
        Make sure the stream directories exist before the model runs
        """
        super().runtime_setup()
        self._make_stream_dirs()

    def _make_stream_dirs(self):
        """
        Create the directories Omega's streams write into, ``restart`` for
        the ``RestartWrite`` stream unless a subclass adds more.

        Omega does not create them, so without this the restart write fails
        at the end of the run and the run cannot be continued.  MPAS-Ocean
        needs no equivalent: the MPAS framework creates stream directories
        itself (``xml_stream_parser.c``).  The paths match the ``Filename``
        of each stream under ``IOStreams`` in the step's yaml files.
        """
        if self.config.get('ocean', 'model') != 'omega':
            return
        for dirname in self.stream_dirs:
            os.makedirs(os.path.join(self.work_dir, dirname), exist_ok=True)

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        if self.ncells is None:
            raise ValueError(
                'Cell count is required for realistic_global tests'
            )
        return self.ncells


class AnalysisMembersForward(Forward):
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
            package='polaris.tasks.ocean.realistic_global.analysis_members',
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
