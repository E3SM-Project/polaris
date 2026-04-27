import os

import xarray as xr

from polaris.mesh.spherical.coastline import (
    CONVENTIONS,
    _write_netcdf_with_fill_values,
    build_coastline_dataset,
    build_coastline_datasets,
)
from polaris.mesh.spherical.critical_transects import (
    load_default_critical_transects,
)
from polaris.step import Step

__all__ = [
    'CONVENTIONS',
    'PrepareCoastlineStep',
    'build_coastline_dataset',
    'build_coastline_datasets',
]


class PrepareCoastlineStep(Step):
    """
    Prepare coastline masks and signed-distance fields on a lat-lon grid.
    """

    def __init__(self, component, combine_step, subdir):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        combine_step : polaris.tasks.e3sm.init.topo.combine.CombineStep
            The step with combined topography on the target lat-lon grid

        subdir : str
            The subdirectory within the component's work directory
        """
        super().__init__(
            component=component,
            name='coastline',
            subdir=subdir,
            cpus_per_task=1,
            min_cpus_per_task=1,
        )
        self.combine_step = combine_step
        self.output_filenames = {
            convention: f'coastline_{convention}.nc'
            for convention in CONVENTIONS
        }

    def setup(self):
        """
        Set up the step in the work directory, including linking inputs.
        """
        combine_step = self.combine_step
        self.add_input_file(
            filename='topography.nc',
            work_dir_target=os.path.join(
                combine_step.path, combine_step.combined_filename
            ),
        )
        for filename in self.output_filenames.values():
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step.
        """
        section = self.config['coastline']
        resolution = section.getfloat('resolution_latlon')
        include_critical_transects = section.getboolean(
            'include_critical_transects'
        )
        mask_threshold = section.getfloat('mask_threshold')
        sea_level_elevation = section.getfloat('sea_level_elevation')
        distance_chunk_size = section.getint('distance_chunk_size')

        critical_transects = None
        if include_critical_transects:
            critical_transects = load_default_critical_transects()

        ds_topo = xr.open_dataset('topography.nc')
        ds_coastlines = build_coastline_datasets(
            ds_topo=ds_topo,
            resolution=resolution,
            mask_threshold=mask_threshold,
            sea_level_elevation=sea_level_elevation,
            distance_chunk_size=distance_chunk_size,
            workers=self.cpus_per_task,
            critical_transects=critical_transects,
        )
        for convention, ds_coastline in ds_coastlines.items():
            ds_coastline.attrs['source_topography'] = (
                self.combine_step.combined_filename
            )
            ds_coastline.attrs['source_topography_step'] = (
                self.combine_step.subdir
            )
            _write_netcdf_with_fill_values(
                ds_coastline, self.output_filenames[convention]
            )
