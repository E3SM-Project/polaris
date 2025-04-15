import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_mpas_field


class Viz(Step):
    """
    A step for plotting fields from the cosine bell output

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """

    def __init__(
        self, component, name, subdir, base_mesh, init, forward, mesh_name
    ):
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
            work_dir_target=f'{base_mesh.path}/base_mesh.nc',
        )
        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/initial_state.nc',
        )
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{forward.path}/output.nc'
        )
        self.mesh_name = mesh_name

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        mesh_name = self.mesh_name
        run_duration = (
            config.getfloat('convergence_forward', 'run_duration') / 24.0
        )

        colormap_sections = dict(
            h='geostrophic_viz_h',
            u='geostrophic_viz_vel',
            v='geostrophic_viz_vel',
        )

        ds_init = xr.open_dataset('initial_state.nc')
        bottom_depth = ds_init.bottomDepth
        ds_init = self._process_ds(ds_init, bottom_depth, time_index=0)
        ds_init.to_netcdf('remapped_init.nc')

        for var, colormap_section in colormap_sections.items():
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds_init[var],
                out_filename=f'init_{var}.png',
                config=config,
                colormap_section=colormap_section,
                colorbar_label=config.get(colormap_section, 'label'),
                title=f'{mesh_name} {var} at init',
                plot_land=False,
            )

        ds_out = xr.open_dataset('output.nc')
        ds_out = self._process_ds(ds_out, bottom_depth, time_index=-1)
        ds_out.to_netcdf('remapped_final.nc')

        for var, colormap_section in colormap_sections.items():
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds_out[var],
                out_filename=f'final_{var}.png',
                config=config,
                colormap_section=colormap_section,
                colorbar_label=config.get(colormap_section, 'label'),
                title=f'{mesh_name} {var} after {run_duration:g} days',
                plot_land=False,
            )

        colormap_sections = dict(
            h='geostrophic_viz_diff_h',
            u='geostrophic_viz_diff_vel',
            v='geostrophic_viz_diff_vel',
        )

        for var, colormap_section in colormap_sections.items():
            diff = ds_out[var] - ds_init[var]
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=diff,
                out_filename=f'diff_{var}.png',
                config=config,
                colormap_section=colormap_section,
                colorbar_label=config.get(colormap_section, 'label'),
                title=f'{mesh_name} {var} change after {run_duration:g} days',
                plot_land=False,
            )

    @staticmethod
    def _process_ds(ds, bottom_depth, time_index):
        ds_out = ds.isel(Time=time_index, nVertLevels=0)
        ds_out['h'] = ds_out.ssh + bottom_depth
        ds_out = ds_out.rename(
            dict(
                velocityZonal='u',
                velocityMeridional='v',
            )
        )
        return ds_out
