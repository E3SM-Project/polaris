import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.coriolis import add_coriolis_to_dataset
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for barotropic channel
    tasks

    Attributes
    ----------
    """

    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='init', indir=indir)

    def setup(self):
        super().setup()
        self.add_output_files_for_ocean_model_input(
            horiz_mesh_filename='culled_mesh.nc',
            base_mesh_filename='base_mesh.nc',
            graph_filename='culled_graph.info',
        )

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger

        section = config['barotropic_channel']
        resolution = section.getfloat('resolution')
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        u = section.getfloat('zonal_velocity')
        v = section.getfloat('meridional_velocity')
        u_wind = section.getfloat('zonal_wind_stress')
        v_wind = section.getfloat('meridional_wind_stress')

        # these could be hard-coded as functions of specific supported
        # resolutions but it is preferable to make them algorithmic like here
        # for greater flexibility
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        ny = 4
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=False, nonperiodic_y=True
        )
        self.write_model_dataset(ds_mesh, 'base_mesh.nc', config)

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        self.write_horiz_mesh_dataset(ds_mesh, 'culled_mesh.nc', config)

        ds = ds_mesh.copy()

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        y_min = ds.yCell.min().values
        y_max = ds.yCell.max().values
        y_cell = ds.yCell
        frac = xr.where((y_cell <= y_min) | (y_cell >= y_max), 2.0 / 3.0, 1.0)
        ds['bottomDepth'] = bottom_depth * frac
        ds['ssh'] = xr.zeros_like(ds.xCell)
        init_vertical_coord(config, ds)
        cell_field = xr.ones_like(ds.xCell)
        cell_field, _ = xr.broadcast(cell_field, ds.refBottomDepth)
        ds['temperature'] = cell_field.expand_dims(dim='Time', axis=0)
        ds['salinity'] = 35.0 * cell_field.expand_dims(dim='Time', axis=0)
        # temperature and salinity must be set before this call:
        # write_vert_coord_dataset converts restingThickness to
        # RefPseudoThickness via pseudothickness_from_ds, which requires T/S
        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        normal_velocity = u * np.cos(ds_mesh.angleEdge) + v * np.sin(
            ds_mesh.angleEdge
        )
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        ds['normalVelocity'] = normal_velocity.expand_dims(dim='Time', axis=0)

        # set the wind stress forcing
        wind_stress_zonal = u_wind * xr.ones_like(ds.xCell)
        wind_stress_meridional = v_wind * xr.ones_like(ds.xCell)
        ds['windStressZonal'] = wind_stress_zonal.expand_dims(
            dim='Time', axis=0
        )
        ds['windStressMeridional'] = wind_stress_meridional.expand_dims(
            dim='Time', axis=0
        )
        self.write_initial_state_dataset(ds, 'init.nc', config)
