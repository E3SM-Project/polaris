import numpy as np
import xarray as xr

from polaris.ocean.eos import compute_density
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.overflow.init_utils import (
    build_overflow_mesh,
    compute_bottom_depth,
    compute_initial_temperature,
)


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for overflow test cases.
    """

    def __init__(self, component, name='init', indir=None):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        indir : str
            The name of the directory the task will be set up in
        """
        super().__init__(component=component, name=name, indir=indir)

    def setup(self):
        super().setup()
        self.add_output_files_for_ocean_model_input(
            horiz_mesh_filename='culled_mesh.nc',
            base_mesh_filename='base_mesh.nc',
            graph_filename='culled_graph.info',
        )

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config

        ds_mesh = build_overflow_mesh(self)

        ds = ds_mesh.copy()

        # Form a continental shelf-like bathymetry
        ds['bottomDepth'] = compute_bottom_depth(config, ds.xCell)

        # ssh is zero
        ds['ssh'] = xr.zeros_like(ds.xCell)

        init_vertical_coord(config, ds)

        # initial temperature is constant except for a block of cold water on
        # the shelf
        temp_cell = compute_initial_temperature(config, ds.xCell)
        temperature = np.broadcast_to(
            temp_cell.values[:, np.newaxis],
            (ds.sizes['nCells'], ds.sizes['nVertLevels']),
        )
        ds['temperature'] = (
            (
                'Time',
                'nCells',
                'nVertLevels',
            ),
            np.expand_dims(temperature, axis=0),
        )

        # initial salinity is constant
        salinity = config.getfloat('overflow', 'salinity')
        ds['salinity'] = salinity * xr.ones_like(ds.temperature)

        ds['density'] = compute_density(config, ds.temperature, ds.salinity)

        # initial velocity on edges is stationary
        ds['normalVelocity'] = (
            (
                'Time',
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([1, ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(ds, 'init.nc', config)
