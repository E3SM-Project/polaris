import cmocean  # noqa: F401

from polaris.ocean.model import OceanIOStep
from polaris.viz import plot_global_mpas_field


class Viz(OceanIOStep):
    """
    A step for plotting fields from the cosine bell output

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """
    def __init__(self, component, name, subdir, base_mesh, init, forward,
                 mesh_name):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory in the test case's work directory for the step

        base_mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        forward : polaris.Step
            The init step

        mesh_name : str
            The name of the mesh
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc')
        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            work_dir_target=f'{forward.path}/output.nc')
        self.mesh_name = mesh_name
        self.add_output_file('init.png')
        self.add_output_file('final.png')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        mesh_name = self.mesh_name
        run_duration = config.getfloat('convergence_forward', 'run_duration')

        ds_init = self.open_model_dataset('initial_state.nc')
        da = ds_init['tracer1'].isel(Time=0, nVertLevels=0)

        plot_global_mpas_field(
            mesh_filename='mesh.nc', da=da, out_filename='init.png',
            config=config, colormap_section='cosine_bell_viz',
            title=f'{mesh_name} tracer at init', plot_land=False,
            central_longitude=180.)

        ds_out = self.open_model_dataset('output.nc')
        da = ds_out['tracer1'].isel(Time=-1, nVertLevels=0)

        plot_global_mpas_field(
            mesh_filename='mesh.nc', da=da, out_filename='final.png',
            config=config, colormap_section='cosine_bell_viz',
            title=f'{mesh_name} tracer after {run_duration / 24.:g} days',
            plot_land=False, central_longitude=180.)
