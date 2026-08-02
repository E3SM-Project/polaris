import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.coriolis import add_coriolis_to_dataset
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.seamount.init_utils import compute_tracers


class Init(OceanIOStep):
    """
    A step for creating a mesh and initial condition for seamount test cases.
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
        logger = self.logger

        section = config['seamount']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=False, nonperiodic_y=False
        )
        self.write_model_dataset(ds_mesh, 'base_mesh.nc', config)

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        self.write_horiz_mesh_dataset(ds_mesh, 'culled_mesh.nc', config)

        # from overflow. Delete when not needed.
        max_bottom_depth = section.getfloat('max_bottom_depth')

        seamount_height = section.getfloat('seamount_height')
        seamount_width = section.getfloat('seamount_width')

        ds = ds_mesh.copy()

        x_mid_global = (ds.xCell.max() - ds.xCell.min()) / 2.0 + ds.xCell.min()
        y_mid_global = (ds.yCell.max() - ds.yCell.min()) / 2.0 + ds.yCell.min()
        # Set bottomDepth.
        # See Beckmann and Haidvogel 1993 eqn 12, Shchepetkin 2003 eqn 4.2
        radius = np.sqrt(
            (ds.xCell - x_mid_global) ** 2 + (ds.yCell - y_mid_global) ** 2
        )
        ds['bottomDepth'] = max_bottom_depth - seamount_height * np.exp(
            -(radius**2) / seamount_width**2
        )

        # ssh is zero
        ds['ssh'] = xr.zeros_like(ds.xCell)

        init_vertical_coord(config, ds)

        # Set the configured stratification -- Beckmann and Haidvogel 1993
        # eqn 15-16, or a profile linear in pressure -- carried entirely by
        # temperature since salinity is constant.  The tracers keep the Time
        # dimension that zMid carries, matching layerThickness and the other
        # state variables; TEOS-10 requires its inputs to be aligned, and the
        # linear EOS did not.  layerThickness is what the linear-in-pressure
        # profile integrates the hydrostatic balance over; ssh is zero here,
        # so the surface pressure it starts from is zero as well.
        temperature, salinity = compute_tracers(
            config,
            ds.zMid,
            layer_thickness=ds.layerThickness,
            logger=logger,
        )

        ds['temperature'] = temperature
        ds['salinity'] = salinity
        ds['normalVelocity'] = (
            (
                'Time',
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([1, ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )
        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        # the tracers are in the convention implied by eos_type, so
        # write_initial_state_dataset() converts them to the model's
        # convention on its own
        self.write_initial_state_dataset(ds, 'init.nc', config)
