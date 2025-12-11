import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord


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

        section = config['seamount']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution
        ds_mesh = make_planar_hex_mesh(
            nx=nx, ny=ny, dc=dc, nonperiodic_x=False, nonperiodic_y=False
        )
        self.write_model_dataset(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(
            ds_mesh, graphInfoFileName='culled_graph.info', logger=logger
        )
        self.write_model_dataset(ds_mesh, 'culled_mesh.nc')

        # from overflow. Delete when not needed.
        max_bottom_depth = section.getfloat('max_bottom_depth')

        seamount_stratification_type = section.get(
            'seamount_stratification_type'
        )
        seamount_density_coef_linear = section.getfloat(
            'seamount_density_coef_linear'
        )
        seamount_density_coef_exp = section.getfloat(
            'seamount_density_coef_exp'
        )
        seamount_density_gradient_linear = section.getfloat(
            'seamount_density_gradient_linear'
        )
        seamount_density_gradient_exp = section.getfloat(
            'seamount_density_gradient_exp'
        )
        seamount_density_depth_linear = section.getfloat(
            'seamount_density_depth_linear'
        )
        seamount_density_depth_exp = section.getfloat(
            'seamount_density_depth_exp'
        )
        eos_linear_rhoref = self.config.getfloat('ocean', 'eos_linear_rhoref')
        eos_linear_tref = self.config.getfloat('ocean', 'eos_linear_tref')
        eos_linear_alpha = self.config.getfloat('ocean', 'eos_linear_alpha')
        seamount_height = section.getfloat('seamount_height')
        seamount_width = section.getfloat('seamount_width')
        constant_salinity = section.getfloat('constant_salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')

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
        z_mid = ds.zMid.squeeze('Time')

        # Set stratification using temperature.
        # See Beckmann and Haidvogel 1993 eqn 15-16.
        if seamount_stratification_type == 'linear':
            densityCell = (
                seamount_density_coef_linear
                - seamount_density_gradient_linear
                * z_mid
                / seamount_density_depth_linear
            )

        elif seamount_stratification_type == 'exponential':
            densityCell = (
                seamount_density_coef_exp
                - seamount_density_gradient_exp
                * np.exp(z_mid / seamount_density_depth_exp)
            )

        # Back-solve linear EOS for temperature, with S=S_ref
        # T = T_ref - (rho - rho_ref)/alpha
        temperature = (
            eos_linear_tref
            - (densityCell - eos_linear_rhoref) / eos_linear_alpha
        )

        ds['temperature'] = temperature
        ds['salinity'] = constant_salinity * xr.ones_like(temperature)
        ds['normalVelocity'] = (
            (
                'Time',
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([1, ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )
        ds['fCell'] = coriolis_parameter * xr.ones_like(temperature)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds_mesh.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds_mesh.xVertex)

        # this was in internal wave but not overflow. Is it needed?
        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        # finalize and write file
        self.write_model_dataset(ds, 'init.nc')
        # May not be needed.


# from internal wave:write_netcdf(ds, 'initial_state.nc')
