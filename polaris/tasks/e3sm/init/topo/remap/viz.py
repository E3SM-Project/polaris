import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.viz import plot_global_mpas_field


class VizRemappedTopoStep(Step):
    """
    A step for plotting fields from a remapped topography dataset

    Attributes
    ----------
    mesh_name : str
        The name of the mesh

    remap_step : polaris.tasks.e3sm.init.topo.remap.step.RemapTopoStep
        The step for remapping the topography to the MPAS mesh
    """

    def __init__(self, component, name, subdir, remap_step):
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

        remap_step : polaris.tasks.e3sm.init.topo.remap.step.RemapTopoStep
            The step for remapping the topography to the MPAS mesh
        """
        base_mesh_step = remap_step.base_mesh_step
        config = remap_step.config
        super().__init__(component=component, name=name, subdir=subdir)
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh_step.path}/base_mesh.nc',
        )
        self.add_input_file(
            filename='topography.nc',
            work_dir_target=f'{remap_step.path}/topography_remapped.nc',
        )
        self.mesh_name = base_mesh_step.mesh_name
        self.remap_step = remap_step
        self.set_shared_config(config, link='remap_topo.cfg')

    def run(self):
        """
        Run this step of the test case
        """
        remapping_done = self.remap_step.do_remapping

        if not remapping_done:
            # if the remapping step was not run, then we don't have
            # a remapped topography file to plot
            return

        logger = self.logger
        config = self.config
        mesh_name = self.mesh_name

        ds = xr.open_dataset('topography.nc')

        descriptor = None

        for field in ds.data_vars:
            logger.info(f'Plotting {field}')
            if self.remap_step.smoothing:
                title = f'{mesh_name} {field} smoothed'
            else:
                title = f'{mesh_name} {field}'

            if field.endswith('frac'):
                section = 'viz_remapped_topo_frac'
            else:
                section = f'viz_remapped_topo_{field}'

            descriptor = plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds[field],
                out_filename=f'{field}.png',
                config=config,
                colormap_section=section,
                title=title,
                plot_land=False,
                central_longitude=180.0,
                descriptor=descriptor,
            )
