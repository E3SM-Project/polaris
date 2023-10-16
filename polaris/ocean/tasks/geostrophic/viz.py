import cmocean  # noqa: F401
import xarray as xr

from polaris import Step
from polaris.remap import MappingFileStep
from polaris.viz import plot_global_field


class VizMap(MappingFileStep):
    """
    A step for making a mapping file for cosine bell viz

    Attributes
    ----------
    mesh_name : str
        The name of the mesh

    mesh_type : {'cell', 'edge', 'vertex'}
        Which type of MPAS mesh
    """
    def __init__(self, component, name, subdir, base_mesh, mesh_name,
                 mesh_type):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        base_mesh : polaris.Step
            The base mesh step

        mesh_name : str
            The name of the mesh

        mesh_type : {'cell', 'edge', 'vertex'}
            Which type of MPAS mesh
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         ntasks=128, min_tasks=1)
        self.mesh_name = mesh_name
        self.mesh_type = mesh_type
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc')

    def runtime_setup(self):
        """
        Set up the source and destination grids for this step
        """
        config = self.config
        section = config['geostrophic_viz']
        dlon = section.getfloat('dlon')
        dlat = section.getfloat('dlat')
        method = section.get('remap_method')
        self.src_from_mpas(filename='mesh.nc', mesh_name=self.mesh_name,
                           mesh_type=self.mesh_type)
        self.dst_global_lon_lat(dlon=dlon, dlat=dlat, lon_min=0.)
        self.method = method

        super().runtime_setup()


class Viz(Step):
    """
    A step for plotting fields from the cosine bell output

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """
    def __init__(self, component, name, subdir, init, forward,
                 viz_map_cell, viz_map_edge, mesh_name):
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

        init : polaris.Step
            The init step

        forward : polaris.Step
            The init step

        viz_map_cell : polaris.ocean.tasks.geostrophic.viz.VizMap
            The step for creating a mapping files, also used to remap data
            from the MPAS cells to a lon-lat grid

        viz_map_edge : polaris.ocean.tasks.geostrophic.viz.VizMap
            The step for creating a mapping files, also used to remap data
            from the MPAS edges to a lon-lat grid

        mesh_name : str
            The name of the mesh
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/initial_state.nc')
        self.add_input_file(
            filename='output.nc',
            work_dir_target=f'{forward.path}/output.nc')
        self.add_dependency(viz_map_cell, name='viz_map_cell')
        self.add_dependency(viz_map_edge, name='viz_map_edge')
        self.mesh_name = mesh_name

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        mesh_name = self.mesh_name
        run_duration = \
            config.getfloat('convergence_forward', 'run_duration') / 24.

        colormap_sections = dict(
            h='geostrophic_viz_h',
            u='geostrophic_viz_vel',
            v='geostrophic_viz_vel',
            norm_vel='geostrophic_viz_vel')

        ds_init = xr.open_dataset('initial_state.nc')
        bottom_depth = ds_init.bottomDepth
        ds_init = self._process_ds(ds_init, bottom_depth, time_index=0)
        ds_init.to_netcdf('remapped_init.nc')

        for var, colormap_section in colormap_sections.items():
            plot_global_field(
                ds_init.lon.values, ds_init.lat.values, ds_init[var].values,
                out_filename=f'init_{var}.png', config=config,
                colormap_section=colormap_section,
                title=f'{mesh_name} {var} at init', plot_land=False)

        ds_out = xr.open_dataset('output.nc')
        ds_out = self._process_ds(ds_out, bottom_depth, time_index=-1)
        ds_out.to_netcdf('remapped_final.nc')

        for var, colormap_section in colormap_sections.items():
            plot_global_field(
                ds_out.lon.values, ds_out.lat.values,
                ds_out[var].values, out_filename=f'final_{var}.png',
                config=config, colormap_section=colormap_section,
                title=f'{mesh_name} {var} after {run_duration:g} days',
                plot_land=False)

        colormap_sections = dict(
            h='geostrophic_viz_diff_h',
            u='geostrophic_viz_diff_vel',
            v='geostrophic_viz_diff_vel',
            norm_vel='geostrophic_viz_diff_vel')

        for var, colormap_section in colormap_sections.items():
            diff = ds_out[var] - ds_init[var]
            plot_global_field(
                ds_out.lon.values, ds_out.lat.values,
                diff, out_filename=f'diff_{var}.png',
                config=config, colormap_section=colormap_section,
                title=f'{mesh_name} {var} change after {run_duration:g} days',
                plot_land=False)

    def _process_ds(self, ds, bottom_depth, time_index):
        viz_map_cell = self.dependencies['viz_map_cell']
        viz_map_edge = self.dependencies['viz_map_edge']

        remapper_cell = viz_map_cell.get_remapper()
        remapper_edge = viz_map_edge.get_remapper()

        remap_cell_vars = ['ssh', 'velocityZonal', 'velocityMeridional']
        remap_edge_vars = ['normalVelocity']

        ds_cell = ds[remap_cell_vars].isel(Time=time_index, nVertLevels=0)
        ds_cell['h'] = ds_cell.ssh + bottom_depth
        ds_cell = ds_cell.rename(dict(velocityZonal='u',
                                      velocityMeridional='v',))
        ds_out = remapper_cell.remap(ds_cell)

        ds_edge = ds[remap_edge_vars].isel(Time=time_index, nVertLevels=0)
        ds_edge = ds_edge.rename(dict(normalVelocity='norm_vel'))
        ds_out_edge = remapper_edge.remap(ds_edge)
        ds_out['norm_vel'] = ds_out_edge['norm_vel']

        return ds_out
