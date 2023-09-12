import time

from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case

    Attributes
    ----------
    resolution : int
        The resolution of the (uniform) mesh in km

    mesh_name : str
        The name of the mesh
    """

    def __init__(self, component, name, subdir, resolution, mesh_name):
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

        resolution : int
            The resolution of the (uniform) mesh in km

        mesh_name : str
            The name of the mesh
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         openmp_threads=1)

        self.resolution = resolution
        self.mesh_name = mesh_name

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')
        self.add_yaml_file(
            'polaris.ocean.tasks.cosine_bell',
            'forward.yaml')

        self.add_input_file(
            filename='init.nc',
            target=f'../../init/{mesh_name}/initial_state.nc')
        self.add_input_file(
            filename='graph.info',
            target=f'../../../base_mesh/{mesh_name}/graph.info')

        self.add_output_file(filename='output.nc',
                             validate_vars=['normalVelocity', 'tracer1'])

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        # use a heuristic based on QU30 (65275 cells) and QU240 (10383 cells)
        cell_count = 6e8 / self.resolution**2
        return cell_count

    def dynamic_model_config(self, at_setup):
        """
        Set the model time step from config options at setup and runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config

        vert_levels = config.getfloat('vertical_grid', 'vert_levels')
        if not at_setup and vert_levels == 1:
            self.add_yaml_file('polaris.ocean.config', 'single_layer.yaml')
            self.add_yaml_file(
                'polaris.ocean.tasks.cosine_bell',
                'forward.yaml')

        # dt is proportional to resolution: default 30 seconds per km
        dt_per_km = config.getfloat('cosine_bell', 'dt_per_km')

        dt = dt_per_km * self.resolution
        # https://stackoverflow.com/a/1384565/7728169
        dt_str = time.strftime('%H:%M:%S', time.gmtime(dt))

        options = dict(config_dt=dt_str)
        self.add_model_config_options(options)
