import os

import numpy as np
from mpas_tools.io import open_dataset

from polaris.ocean.model import OceanModelStep, get_time_interval_string
from polaris.tasks.ocean.isomip_plus.cell_count import estimate_cell_count
from polaris.tasks.ocean.isomip_plus.xtime import get_record_times


class Forward(OceanModelStep):
    """
    A step for performing a forward ocean component run with melt fluxes and
    restoring as part of ISOMIP+ tasks

    Attributes
    ----------
    resolution : float
        The horizontal resolution (km) of the mesh

    thin_film : bool
        Whether a thin film is present under grounded ice, in which case the
        land-ice pressure and fractions vary in time

    restart_test : {'full', 'restart'} or None
        In a restart test, whether this is the full run, which writes a
        restart halfway, or the run that restarts from it
    """

    def __init__(
        self,
        component,
        indir,
        resolution,
        init,
        ssh_adjust,
        thin_film,
        restart_test=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` will be appended

        resolution : float
            The horizontal resolution (km) of the mesh

        init : polaris.Step
            The step that produced the mesh, graph file and forcing

        ssh_adjust : polaris.Step
            The last SSH-adjustment step, which produced the initial condition

        thin_film : bool
            Whether a thin film is present under grounded ice, in which case
            the land-ice pressure and fractions vary in time

        restart_test : {'full', 'restart'}, optional
            In a restart test, whether this is the full run, which writes a
            restart halfway, or the run that restarts from it
        """
        if restart_test not in [None, 'full', 'restart']:
            raise ValueError(f'Unexpected restart_test: {restart_test}')
        name = 'restart' if restart_test == 'restart' else 'forward'
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            ntasks=None,
            min_tasks=None,
            openmp_threads=1,
            graph_target=f'{init.path}/culled_graph.info',
            update_eos=True,
        )
        self.resolution = resolution
        self.thin_film = thin_film
        self.restart_test = restart_test

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_horiz_mesh_input_file(work_dir_target=f'{init.path}/mesh.nc')
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_init_input_file(
            work_dir_target=f'{ssh_adjust.path}/output.nc'
        )
        self.add_input_file(
            filename='forcing_data.nc',
            work_dir_target=f'{init.path}/forcing.nc',
        )
        if thin_film:
            self.add_input_file(
                filename='land_ice_forcing.nc',
                work_dir_target=f'{init.path}/land_ice_forcing.nc',
            )

        self.add_output_file(
            filename='output.nc',
            validate_vars=[
                'temperature',
                'salinity',
                'layerThickness',
                'normalVelocity',
            ],
        )
        self.add_output_file(
            filename='land_ice_fluxes.nc',
            validate_vars=[
                'ssh',
                'landIcePressure',
                'landIceDraft',
                'landIceFraction',
                'landIceMask',
                'landIceFrictionVelocity',
                'topDrag',
                'topDragMagnitude',
                'landIceFreshwaterFlux',
                'landIceHeatFlux',
                'heatFluxToLandIce',
                'landIceBoundaryLayerTemperature',
                'landIceBoundaryLayerSalinity',
                'landIceHeatTransferVelocity',
                'landIceSaltTransferVelocity',
                'landIceInterfaceTemperature',
                'landIceInterfaceSalinity',
                'accumulatedLandIceMass',
                'accumulatedLandIceHeat',
            ],
        )

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        return estimate_cell_count(self.config, self.resolution)

    def dynamic_model_config(self, at_setup):
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        section = self.config['isomip_plus_forward']
        time_integrator = section.get('time_integrator')
        if time_integrator == 'RK4':
            dt_per_km = section.getfloat('rk4_dt_per_km')
        else:
            dt_per_km = section.getfloat('split_dt_per_km')
        btr_dt_per_km = section.getfloat('btr_dt_per_km')

        s_per_hour = 3600.0
        restart_replacements = None
        if self.restart_test is None:
            run_duration = section.getfloat('run_duration') * s_per_hour
            output_option = section.get('output_interval')
            if output_option == 'none':
                output_interval = run_duration
            else:
                output_interval = float(output_option) * s_per_hour
        else:
            # the full run writes a restart halfway, where the restart run
            # starts, and each run writes output only at its end
            full_duration = self.config.getfloat(
                'isomip_plus_restart', 'run_duration'
            )
            half_duration = 0.5 * full_duration * s_per_hour
            if self.restart_test == 'full':
                run_duration = 2.0 * half_duration
            else:
                run_duration = half_duration
            output_interval = run_duration
            restart_replacements = _get_restart_replacements(
                self.restart_test, half_duration
            )
        run_duration_str = get_time_interval_string(seconds=run_duration)
        output_interval_str = get_time_interval_string(seconds=output_interval)
        replacements = dict(
            time_integrator=time_integrator,
            dt=get_time_interval_string(seconds=dt_per_km * self.resolution),
            btr_dt=get_time_interval_string(
                seconds=btr_dt_per_km * self.resolution
            ),
            run_duration=run_duration_str,
            output_interval=output_interval_str,
        )

        self.add_yaml_file('polaris.tasks.ocean.isomip_plus', 'physics.yaml')
        self.add_yaml_file(
            'polaris.tasks.ocean.isomip_plus',
            'forward.yaml',
            template_replacements=replacements,
        )

        if self.thin_film:
            self.add_yaml_file(
                'polaris.tasks.ocean.isomip_plus',
                'thin_film.yaml',
                template_replacements=dict(
                    forcing_interval=self._get_forcing_interval(at_setup)
                ),
            )

        if restart_replacements is not None:
            self.add_yaml_file(
                'polaris.tasks.ocean.isomip_plus',
                'restart.yaml',
                template_replacements=restart_replacements,
            )

    def _get_forcing_interval(self, at_setup):
        """
        Get the spacing of the land-ice forcing records, which MPAS-Ocean
        needs to find them.  The forcing file is only available at runtime,
        so a placeholder is used at setup.
        """
        if at_setup:
            return 'none'
        filename = os.path.join(self.work_dir, 'land_ice_forcing.nc')
        with open_dataset(filename) as ds:
            record_times = get_record_times(ds.xtime.values)
        spacings = np.unique(np.diff(record_times))
        if len(spacings) != 1:
            raise ValueError(
                f'The land-ice forcing records must be evenly spaced, but '
                f'they are at {record_times} s'
            )
        return get_time_interval_string(seconds=float(spacings[0]))


def _get_restart_replacements(restart_test, half_duration):
    """
    Get the template replacements for a step of a restart test, which starts
    at the beginning of the simulation or, for the restart run, halfway
    """
    if half_duration >= 86400.0 or half_duration % 1.0 != 0.0:
        raise ValueError(
            f'Half the restart test must be a whole number of seconds less '
            f'than a day, not {half_duration} s.'
        )
    if restart_test == 'restart':
        do_restart = 'true'
        seconds = int(half_duration)
    else:
        do_restart = 'false'
        seconds = 0
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return dict(
        do_restart=do_restart,
        start_time=f'0001-01-01_{hours:02d}:{minutes:02d}:{seconds:02d}',
        restart_interval=get_time_interval_string(seconds=half_duration),
    )
