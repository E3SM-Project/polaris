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

    smoothing : bool
        Whether the topography was smoothed
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
        self.smoothing = remap_step.smoothing
        self.set_shared_config(config, link='remap_topo.cfg')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        mesh_name = self.mesh_name

        fields = [
            'bed_elevation',
            'landIceThkObserved',
            'landIcePressureObserved',
            'landIceDraftObserved',
            'landIceFracObserved',
            'bathyFracObserved',
            'landIceGroundedFracObserved',
            'oceanFracObserved',
        ]
        ds = xr.open_dataset('topography.nc')

        for field in fields:
            if self.smoothing:
                title = f'{mesh_name} {field} smoothed'
            else:
                title = f'{mesh_name} {field}'
            plot_global_mpas_field(
                mesh_filename='mesh.nc',
                da=ds[field],
                out_filename=f'{field}.png',
                config=config,
                colormap_section=f'viz_remapped_topo_{field}',
                title=title,
                plot_land=False,
                central_longitude=180.0,
            )
