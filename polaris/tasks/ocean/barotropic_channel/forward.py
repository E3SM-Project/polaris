from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of barotropic channel
    test cases.

    Attributes
    ----------
    yaml_filename : str
       The name of the yaml file for this forward step
    """

    def __init__(
        self,
        component,
        graph_target='culled_graph.info',
        yaml_filename='forward.yaml',
        name='forward',
        subdir=None,
        indir=None,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
    ):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

        task_name : str
           The name of the task that this step belongs to

        yaml_filename : str
           The name of the yaml file for this forward step

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use

        nu : float, optional
            the viscosity (if different from the default for the test group)
        """
        if min_tasks is None:
            min_tasks = ntasks
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            graph_target=graph_target,
        )
        self.yaml_filename = yaml_filename

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(
            filename='init.nc',
            target='../init/initial_state.nc',
        )

        self.add_input_file(
            filename='forcing.nc',
            target='../init/forcing.nc',
        )

        self.add_output_file(
            filename='output.nc',
            validate_vars=[
                'layerThickness',
                'normalVelocity',
                'temperature',
            ],
        )

    def setup(self):
        """
        TEMP: symlink initial condition to name hard-coded in Omega
        """
        super().setup()
        model = self.config.get('ocean', 'model')
        # TODO: remove as soon as Omega no longer hard-codes this file
        if model == 'omega':
            self.add_input_file(filename='OmegaMesh.nc', target='init.nc')

    def dynamic_model_config(self, at_setup):
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        nu = config.getfloat('barotropic_channel', 'horizontal_viscosity')
        drag = config.getfloat('barotropic_channel', 'bottom_drag')
        replacements = dict(nu=nu, drag=drag)
        self.add_yaml_file(
            'polaris.tasks.ocean.barotropic_channel',
            self.yaml_filename,
            template_replacements=replacements,
        )
        model = config.get('ocean', 'model')
        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if model == 'mpas-ocean' and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['barotropic_channel']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        cell_count = nx * ny
        return cell_count
