from polaris.tasks.ocean.realistic_global.forward import (
    Forward as RealisticGlobalForward,
)

#: The durations of the runs: a ``short`` one whose length is set per mesh
DURATIONS = ['short']

# The baroclinic and barotropic time steps of each mesh and the length of its
# short run.  For QU.240km the time steps are E3SM's MPAS-Ocean values for
# oQU240: a 2-hour step gave a growing surface hotspot along the Aleutians in
# a one-year run.
MESH_INFO = {
    'QU.240km': dict(
        dt='01:00:00',
        btr_dt='00:03:00',
        short_duration='0005_00:00:00',
    ),
    'EC30to60E2r2': dict(
        dt='00:30:00',
        btr_dt='00:01:00',
        short_duration='0001_00:00:00',
    ),
}


class Forward(RealisticGlobalForward):
    """
    A forward run for the ``analysis_members`` tasks, with the time steps
    and momentum viscosities of its mesh

    The ``short`` run writes daily output and global statistics.

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
        mesh_info = MESH_INFO[mesh_name]
        replacements = {
            'time_integrator': 'SplitExplicitRK2',
            'dt': mesh_info['dt'],
            'btr_dt': mesh_info['btr_dt'],
            'output_interval': '0001_00:00:00',
            'output_freq': '1',
        }
        if duration == 'short':
            replacements['run_duration'] = mesh_info['short_duration']
            replacements['output_freq_units'] = 'days'
            output_filenames = None
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

    def setup(self):
        """
        Add the per-mesh momentum viscosities from the config options
        """
        super().setup()
        section = self.config['analysis_members']
        options = {
            'config_mom_del2': section.getfloat('mom_del2'),
            'config_mom_del4': section.getfloat('mom_del4'),
        }
        self.add_model_config_options(options=options, config_model='ocean')
