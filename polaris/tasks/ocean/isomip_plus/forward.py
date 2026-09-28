from polaris.ocean.model import OceanModelStep, get_time_interval_string
from polaris.tasks.ocean.isomip_plus.cell_count import estimate_cell_count


class Forward(OceanModelStep):
    """
    A step for performing a forward ocean component run with melt fluxes and
    restoring as part of ISOMIP+ tasks

    Attributes
    ----------
    resolution : float
        The horizontal resolution (km) of the mesh
    """

    def __init__(self, component, indir, resolution, init, ssh_adjust):
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
        replacements = dict(
            dt=get_time_interval_string(seconds=dt_per_km * self.resolution),
            run_duration=run_duration_str,
            output_interval=run_duration_str,
        )

        self.add_yaml_file('polaris.tasks.ocean.isomip_plus', 'physics.yaml')
        self.add_yaml_file(
            'polaris.tasks.ocean.isomip_plus',
            'forward.yaml',
            template_replacements=replacements,
        )
