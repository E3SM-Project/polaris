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
    """

    def __init__(
        self, component, indir, resolution, init, ssh_adjust, thin_film
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
        """
        super().__init__(
            component=component,
            name='forward',
            indir=indir,
            ntasks=None,
            min_tasks=None,
            openmp_threads=1,
            graph_target=f'{init.path}/culled_graph.info',
            update_eos=True,
        )
        self.resolution = resolution
        self.thin_film = thin_film

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
        run_duration = section.getfloat('run_duration')
        dt_per_km = section.getfloat('rk4_dt_per_km')

        s_per_hour = 3600.0
        run_duration_str = get_time_interval_string(
            seconds=run_duration * s_per_hour
        )
        output_interval = section.get('output_interval')
        if output_interval == 'none':
            output_interval_str = run_duration_str
        else:
            output_interval_str = get_time_interval_string(
                seconds=float(output_interval) * s_per_hour
            )
        replacements = dict(
            dt=get_time_interval_string(seconds=dt_per_km * self.resolution),
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
