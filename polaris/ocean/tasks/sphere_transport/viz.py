import datetime

import cmocean  # noqa: F401
import numpy as np
import xarray as xr

from polaris import Step
from polaris.remap import MappingFileStep
from polaris.viz.globe import plot_global


class VizMap(MappingFileStep):
    """
    A step for making a mapping file for cosine bell viz

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """
    def __init__(self, component, name, subdir, base_mesh, mesh_name):
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
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         ntasks=128, min_tasks=1)
        self.mesh_name = mesh_name
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc')

    def runtime_setup(self):
        """
        Set up the source and destination grids for this step
        """
        config = self.config
        section = config['sphere_transport_viz']
        dlon = section.getfloat('dlon')
        dlat = section.getfloat('dlat')
        method = section.get('remap_method')
        self.src_from_mpas(filename='mesh.nc', mesh_name=self.mesh_name)
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
    def __init__(self, component, name, subdir, base_mesh, init, forward,
                 viz_map, mesh_name):
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

        viz_map : polaris.ocean.tasks.sphere_transport.viz.VizMap
            The step for creating a mapping files, also used to remap data
            from the MPAS mesh to a lon-lat grid

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
        self.add_dependency(viz_map, name='viz_map')
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
        run_duration = config.getfloat('spherical_convergence_forward',
                                       'run_duration')

        viz_map = self.dependencies['viz_map']

        remapper = viz_map.get_remapper()

        variables_to_plot = self.variables_to_plot
        ds_init = xr.open_dataset('initial_state.nc')
        ds_init = ds_init[variables_to_plot.keys()].isel(Time=0, nVertLevels=0)
        ds_init = remapper.remap(ds_init)
        ds_init.to_netcdf('remapped_init.nc')

        ds_out = xr.open_dataset('output.nc')
        seconds_per_day = 86400.0

        # Visualization at halfway around the globe (provided run duration is
        # set to the time needed to circumnavigate the globe)
        tidx = _time_index_from_xtime(ds_out.xtime.values,
                                      run_duration * seconds_per_day / 2.)
        ds_mid = ds_out[variables_to_plot.keys()].isel(Time=tidx,
                                                       nVertLevels=0)
        ds_mid = remapper.remap(ds_mid)
        ds_mid.to_netcdf('remapped_mid.nc')

        # Visualization at all the way around the globe
        tidx = _time_index_from_xtime(ds_out.xtime.values,
                                      run_duration * seconds_per_day)
        ds_final = ds_out[variables_to_plot.keys()].isel(Time=tidx,
                                                         nVertLevels=0)
        ds_final = remapper.remap(ds_final)
        ds_final.to_netcdf('remapped_final.nc')

        for var, section_name in variables_to_plot.items():
            colormap_section = f'sphere_transport_viz_{section_name}'
            plot_global(ds_init.lon.values, ds_init.lat.values,
                        ds_init[var].values,
                        out_filename=f'{var}_init.png', config=config,
                        colormap_section=colormap_section,
                        title=f'{mesh_name} {var} at init', plot_land=False)
            plot_global(ds_init.lon.values, ds_init.lat.values,
                        ds_mid[var].values,
                        out_filename=f'{var}_mid.png', config=config,
                        colormap_section=colormap_section,
                        title=f'{mesh_name} {var} after {run_duration / 2.:g} '
                              'days',
                        plot_land=False)
            plot_global(ds_init.lon.values, ds_init.lat.values,
                        ds_final[var].values,
                        out_filename=f'{var}_final.png', config=config,
                        colormap_section=colormap_section,
                        title=f'{mesh_name} {var} after {run_duration:g} days',
                        plot_land=False)
            plot_global(ds_init.lon.values, ds_init.lat.values,
                        ds_final[var].values - ds_init[var].values,
                        out_filename=f'{var}_diff.png', config=config,
                        colormap_section=f'{colormap_section}_diff',
                        title=f'Difference in {mesh_name} {var} from initial '
                              f'condition after {run_duration:g} days',
                        plot_land=False)


def _time_index_from_xtime(xtime, dt_target):
    """
    Determine the time index at which to evaluate convergence

    Parameters
    ----------
    xtime : list of str
        Times in the dataset

    dt_target : float
        Time in seconds at which to evaluate convergence

    Returns
    -------
    tidx : int
        Index in xtime that is closest to dt_target
    """
    t0 = datetime.datetime.strptime(xtime[0].decode(),
                                    '%Y-%m-%d_%H:%M:%S')
    dt = np.zeros((len(xtime)))
    for idx, xt in enumerate(xtime):
        t = datetime.datetime.strptime(xt.decode(),
                                       '%Y-%m-%d_%H:%M:%S')
        dt[idx] = (t - t0).total_seconds()
    return np.argmin(np.abs(np.subtract(dt, dt_target)))
