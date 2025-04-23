import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for the nonhydro
    and the hydro vs nonhydro test cases.
    """

    def __init__(self, component, name='init', indir=None):
        """
        Create the step

        Parameters
        ----------
        test_case : compass.TestCase
        """
        super().__init__(component=component, name=name, indir=indir)

    def setup(self):
        super().setup()
        output_filenames = ['base_mesh.nc', 'culled_mesh.nc', 'init.nc']
        model = self.config.get('ocean', 'model')
        if model == 'mpas-ocean':
            output_filenames.append('culled_graph.info')
        for filename in output_filenames:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger

        section = config['overflow']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=True, nonperiodic_y=False
        )
        self.write_model_dataset(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        self.write_model_dataset(ds_mesh, 'culled_mesh.nc')

        max_bottom_depth = section.getfloat('max_bottom_depth')
        shelf_depth = section.getfloat('shelf_depth')
        x_slope = section.getfloat('x_slope')
        l_slope = section.getfloat('l_slope')

        ds = ds_mesh.copy()
        ds['bottomDepth'] = shelf_depth + 0.5 * (
            max_bottom_depth - shelf_depth
        ) * (
            1.0
            + np.tanh(
                (ds.xCell - ds.xCell.min() - x_slope * 1.0e3)
                / (l_slope * 1.0e3)
            )
        )
        # ssh
        ds['ssh'] = xr.zeros_like(ds.xCell)

        init_vertical_coord(config, ds)

        # initial salinity and temperature
        salinity = section.getfloat('salinity')
        ds['salinity'] = salinity * xr.ones_like(ds.zMid)

        # T = Tref - (rho - rhoRef)/alpha
        x_dense = section.getfloat('x_dense')
        lower_temperature = section.getfloat('lower_temperature')
        higher_temperature = section.getfloat('higher_temperature')
        _, x = np.meshgrid(np.zeros(ds.sizes['nVertLevels']), ds.xCell)
        temperature = np.where(
            (x - ds.xCell.min().values) < x_dense * 1.0e3,
            lower_temperature,
            higher_temperature,
        )
        ds['temperature'] = (
            (
                'Time',
                'nCells',
                'nVertLevels',
            ),
            np.expand_dims(temperature, axis=0),
        )

        # initial velocity on edges
        ds['normalVelocity'] = (
            (
                'Time',
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([1, ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )

        # Coriolis parameter
        ds['fCell'] = (
            (
                'nCells',
                'nVertLevels',
            ),
            np.zeros([ds.sizes['nCells'], ds.sizes['nVertLevels']]),
        )
        ds['fEdge'] = (
            (
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )
        ds['fVertex'] = (
            (
                'nVertices',
                'nVertLevels',
            ),
            np.zeros([ds.sizes['nVertices'], ds.sizes['nVertLevels']]),
        )

        # finalize and write file
        self.write_model_dataset(ds, 'init.nc')
