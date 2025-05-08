import os

import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib import cm

from polaris.step import Step
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep


class VizCombinedStep(Step):
    """
    A step for visualizing the combined topography dataset

    Attributes
    ----------
    combine_step : polaris.tasks.e3sm.init.topo.combine.CombineStep
        The combine step to use for visualization

    """

    def __init__(self, component, combine_step):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs

        combine_step : polaris.tasks.e3sm.init.topo.combine.CombineStep
            The combine step to use for visualization
        """
        super().__init__(
            component=component,
            name='viz_combine_topo',
            subdir=os.path.join(CombineStep.get_subdir(), 'viz'),
            cpus_per_task=128,
            min_cpus_per_task=1,
        )
        self.combine_step = combine_step

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
            'bathymetry': 'cmo.deep_r',
            'thickness': 'cmo.ice_r',
            'ice_draft': 'cmo.deep_r',
            'ice_mask': 'cmo.amp_r',
            'grounded_mask': 'cmo.amp_r',
            'ocean_mask': 'cmo.amp_r',
        }

        ds_data = xr.open_dataset('topography.nc')

        # Use one field to define the valid mask (they all share indexing)
        valid_mask = np.isfinite(ds_data['bathymetry'].values)

        # Build mesh only once
        vertices, tris = self._load_trimesh_geometry(
            'cubed_sphere.g', valid_mask
        )

        # Plot each field
        for field in colormaps:
            self.logger.info(f'Plotting field: {field}')
            colors = self._cmap_to_colors(colormaps[field])
            data = ds_data[field].values[valid_mask]
            self._plot_field(vertices, tris, data, field, colors)

    @staticmethod
    def _load_trimesh_geometry(exodus_path, valid_mask):
        ds_mesh = xr.open_dataset(exodus_path, decode_coords=False)
        coords = ds_mesh['coord'].values
        conn = ds_mesh['connect1'].values - 1  # 0-based

        x, y, z = coords[0], coords[1], coords[2]
        r = np.sqrt(x**2 + y**2 + z**2)
        lat_nodes = np.degrees(np.arcsin(z / r))
        lon_nodes = np.mod(np.degrees(np.arctan2(y, x)), 360)

        # Apply element mask to connectivity
        # shape (n_cells, 4)
        conn_valid = conn[valid_mask]

        # Split each quad into 2 triangles: [0, 1, 2] and [0, 2, 3]
        tris1 = conn_valid[:, [0, 1, 2]]
        tris2 = conn_valid[:, [0, 2, 3]]
        # shape (2 * n_cells, 3)
        tris = np.vstack((tris1, tris2))

        # Convert to DataFrame: each row is a triangle with 3 vertex indices
        tris = pd.DataFrame(tris, columns=['v0', 'v1', 'v2'])

        # Convert vertices to DataFrame: each row is a vertex with lon/lat
        vertices = pd.DataFrame({'lon': lon_nodes, 'lat': lat_nodes})

        return vertices, tris

    def _plot_field(self, vertices, tris, field_data, field_name, colors):
        """
        Rasterize and save a trisurf-style field image using Datashader.
        """
        try:
            import datashader
            from datashader import transfer_functions
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
            x_range=(0, 360),
            y_range=(-90, 90),
        )

        agg = canvas.trimesh(
            simplices=tris, vertices=vertices, agg=datashader.mean('value')
        )

        img = transfer_functions.shade(agg, cmap=colors, how='linear')
        img.to_pil().save(image_filename)

    @staticmethod
    def _cmap_to_colors(cmap, n=256):
        """
        Convert a matplotlib colormap to a list of hex colors for Datashader.
        """
        if isinstance(cmap, str):
            cmap = cm.get_cmap(cmap)
        return [mcolors.rgb2hex(cmap(i / (n - 1))) for i in range(n)]
