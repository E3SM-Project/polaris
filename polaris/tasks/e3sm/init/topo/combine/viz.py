import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import Normalize
from mpl_toolkits.axes_grid1 import make_axes_locatable

from polaris.step import Step


class VizCombinedStep(Step):
    """
    A step for visualizing the combined topography dataset

    Attributes
    ----------
    combine_step : polaris.tasks.e3sm.init.topo.combine.CombineStep
        The combine step to use for visualization

    """

    def __init__(self, component, config, combine_step):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs

        config : polaris.config.PolarisConfigParser
            The config options for the step

        combine_step : polaris.tasks.e3sm.init.topo.combine.CombineStep
            The combine step to use for visualization
        """
        super().__init__(
            component=component,
            name='viz_combine_topo',
            subdir=os.path.join(combine_step.subdir, 'viz'),
            cpus_per_task=128,
            min_cpus_per_task=1,
        )
        self.combine_step = combine_step
        self.set_shared_config(config, link='combine_topo.cfg')

    def setup(self):
        """
        Set up the step in the work directory, including linking input files
        """
        combine_step = self.combine_step

        topo_filename = combine_step.combined_filename
        exodus_filename = combine_step.exodus_filename

        self.add_input_file(
            filename='topography.nc',
            work_dir_target=os.path.join(combine_step.path, topo_filename),
        )

        self.add_input_file(
            filename='cubed_sphere.g',
            work_dir_target=os.path.join(combine_step.path, exodus_filename),
        )

    def run(self):
        """
        Run this step
        """

        colormaps = {
            'base_elevation': 'cmo.deep_r',
            'ice_thickness': 'cmo.ice_r',
            'ice_draft': 'cmo.deep_r',
            'ice_mask': 'cmo.amp_r',
            'grounded_mask': 'cmo.amp_r',
        }

        ds_data = xr.open_dataset('topography.nc')

        # Use one field to define the valid mask (they all share indexing)
        valid_mask = np.isfinite(ds_data['base_elevation'].values)

        # Build mesh only once
        vertices, tris = self._load_trimesh_geometry(
            'cubed_sphere.g', valid_mask
        )

        # Plot each field
        for field, colormap in colormaps.items():
            self.logger.info(f'Plotting field: {field}')
            data = ds_data[field].values[valid_mask]
            self._plot_field(vertices, tris, data, field, colormap)

    @staticmethod
    def _load_trimesh_geometry(exodus_path, valid_mask):
        ds_mesh = xr.open_dataset(exodus_path, decode_coords=False)
        coords = ds_mesh['coord'].values
        # 0-based
        conn = ds_mesh['connect1'].values - 1

        x, y, z = coords[0], coords[1], coords[2]
        r = np.sqrt(x**2 + y**2 + z**2)
        lat_nodes = np.degrees(np.arcsin(z / r))
        lon_nodes = np.degrees(np.arctan2(y, x))

        # Apply element mask to connectivity
        # shape (n_cells, 4)
        conn_valid = conn[valid_mask]

        # Split each quad into 2 triangles: [0, 1, 2] and [0, 2, 3]
        tris = np.empty((2 * conn_valid.shape[0], 3), dtype=int)
        # lower triangle
        tris[0::2] = conn_valid[:, [0, 1, 2]]
        # upper triangle
        tris[1::2] = conn_valid[:, [0, 2, 3]]

        # Convert to DataFrame: each row is a triangle with 3 vertex indices
        tris = pd.DataFrame(tris, columns=['v0', 'v1', 'v2'])

        # Convert vertices to DataFrame: each row is a vertex with lon/lat
        vertices = pd.DataFrame({'lon': lon_nodes, 'lat': lat_nodes})

        return vertices, tris

    def _plot_field(self, vertices, tris, field_data, field_name, cmap):
        """
        Rasterize and save a trisurf-style field image using Datashader.
        """
        try:
            import datashader
        except ImportError as err:
            raise ImportError(
                'the datashader package is not installed. '
                'Please install in your conda environment so you can run '
                'the topography visualization step.'
            ) from err

        import numba

        numba.set_num_threads(self.cpus_per_task)

        image_filename = f'{field_name}.png'

        # Repeat each field value twice (for 2 triangles per quad)
        tris['value'] = np.repeat(field_data, 2)

        canvas = datashader.Canvas(
            plot_width=2000,
            plot_height=1000,
            x_range=(-180, 180),
            y_range=(-90, 90),
        )

        agg = canvas.trimesh(
            simplices=tris, vertices=vertices, agg=datashader.mean('value')
        )
        self._plot_with_colorbar(
            agg, cmap=cmap, field_name=field_name, filename=image_filename
        )

    def _plot_with_colorbar(
        self, agg, cmap, field_name, vmin=None, vmax=None, filename=None
    ):
        """
        Render a datashader aggregate with matplotlib colorbar.
        """
        # Convert the aggregate (xarray) to numpy and mask NaNs
        # mask background
        img_data = np.ma.masked_invalid(agg.data).astype('float32')

        # Normalize range
        norm = Normalize(
            vmin=np.nanmin(img_data) if vmin is None else vmin,
            vmax=np.nanmax(img_data) if vmax is None else vmax,
        )

        # Plot
        fig, ax = plt.subplots(figsize=(22, 10))
        im = ax.imshow(
            img_data, cmap=cmap, norm=norm, origin='lower', aspect='equal'
        )

        divider = make_axes_locatable(ax)
        cax = divider.append_axes('right', size='2%', pad=0.05)
        plt.colorbar(im, cax=cax, label=field_name)
        ax.axis('off')

        plt.savefig(filename, dpi=150, bbox_inches='tight')
        self.logger.info(f'  Plot with colorbar saved to {filename}')
        plt.close()
