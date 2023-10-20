import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.mpas import time_index_from_xtime
from polaris.viz import plot_global_mpas_field


class Viz(Step):
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
        variables_to_plot = dict({'tracer1': 'tracer',
                                  'tracer2': 'tracer',
                                  'tracer3': 'tracer',
                                  'layerThickness': 'h'})
        self.variables_to_plot = variables_to_plot
        for var in variables_to_plot.keys():
            self.add_output_file(f'{var}_init.png')
            self.add_output_file(f'{var}_final.png')
            self.add_output_file(f'{var}_diff.png')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        mesh_name = self.mesh_name
        run_duration = config.getfloat('convergence_forward',
                                       'run_duration')

        variables_to_plot = self.variables_to_plot
        ds_init = xr.open_dataset('initial_state.nc')
        ds_init = ds_init[variables_to_plot.keys()].isel(Time=0, nVertLevels=0)

        ds_out = xr.open_dataset('output.nc')
        s_per_hour = 3600.0

        # Visualization at halfway around the globe (provided run duration is
        # set to the time needed to circumnavigate the globe)
        tidx = time_index_from_xtime(ds_out.xtime.values,
                                     run_duration * s_per_hour / 2.)
        ds_mid = ds_out[variables_to_plot.keys()].isel(Time=tidx,
                                                       nVertLevels=0)

        # Visualization at all the way around the globe
        tidx = time_index_from_xtime(ds_out.xtime.values,
                                     run_duration * s_per_hour)
        ds_final = ds_out[variables_to_plot.keys()].isel(Time=tidx,
                                                         nVertLevels=0)

        for var, section_name in variables_to_plot.items():
            colormap_section = f'sphere_transport_viz_{section_name}'
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds_init[var],
                out_filename=f'{var}_init.png',
                config=config,
                colormap_section=colormap_section,
                title=f'{mesh_name} {var} at init',
                plot_land=False,
                central_longitude=180.)
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds_mid[var],
                out_filename=f'{var}_mid.png',
                config=config,
                colormap_section=colormap_section,
                title=f'{mesh_name} {var} after {run_duration / 48.:g} days',
                plot_land=False,
                central_longitude=180.)
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds_final[var],
                out_filename=f'{var}_final.png',
                config=config,
                colormap_section=colormap_section,
                title=f'{mesh_name} {var} after {run_duration / 24.:g} days',
                plot_land=False,
                central_longitude=180.)
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds_final[var] - ds_init[var],
                out_filename=f'{var}_diff.png',
                config=config,
                colormap_section=f'{colormap_section}_diff',
                title=f'Difference in {mesh_name} {var} from initial '
                      f'condition after {run_duration / 24.:g} days',
                plot_land=False,
                central_longitude=180.)
