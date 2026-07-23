import xarray as xr

from polaris.ocean.eos import convert_tracers_to_mpas_ocean
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical.pstar_init import PStarInitStep
from polaris.ocean.vertical.pstar_state import (
    add_density_from_specvol,
    add_quiescent_normal_velocity,
    layer_thickness_from_geom_interfaces,
)
from polaris.tasks.ocean.overflow.mesh import (
    build_overflow_mesh,
    compute_bottom_depth,
    compute_initial_temperature,
)


class PStarInit(PStarInitStep, OceanIOStep):
    """
    A step for creating a mesh and initial condition for overflow test
    cases on the p-star vertical coordinate.

    The overflow tracer profile is interpreted as conservative
    temperature (CT) and absolute salinity (SA).  Omega receives CT and
    SA directly; for MPAS-Ocean they are converted to potential
    temperature and practical salinity at a nominal lon/lat location.
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

        # Form a continental shelf-like bathymetry
        bottom_depth = compute_bottom_depth(config, ds_mesh.xCell)
        geom_z_bot = -bottom_depth
        geom_z_bot.attrs['long_name'] = 'seafloor geometric height'
        geom_z_bot.attrs['units'] = 'm'

        # Iterate the p-star coordinate to convergence with zero surface
        # pressure
        ds = self.run_pstar_init(ds_mesh=ds_mesh, geom_z_bot=geom_z_bot)

        ds = layer_thickness_from_geom_interfaces(ds)
        ds = add_quiescent_normal_velocity(ds, ds_mesh)
        ds = add_density_from_specvol(ds)

        if config.get('ocean', 'model') == 'mpas-ocean':
            section = config['overflow']
            nominal_lon = section.getfloat('nominal_lon')
            nominal_lat = section.getfloat('nominal_lat')
            ds = convert_tracers_to_mpas_ocean(
                ds, lon=nominal_lon, lat=nominal_lat
            )

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(ds, 'init.nc', config)

    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Initialize conservative temperature and absolute salinity at the
        current p-star layer midpoints: the overflow profile of constant
        temperature except for a block of cold water on the shelf, and
        constant salinity.
        """
        config = self.config

        temp_cell = compute_initial_temperature(config, ds.xCell)
        # the profile does not vary with depth, so broadcasting over the
        # p-star layer midpoints is trivial
        ct = (temp_cell * xr.ones_like(ds.ZTildeMid)).transpose(
            'Time', 'nCells', 'nVertLevels'
        )
        ct.attrs['long_name'] = 'conservative temperature'
        ct.attrs['units'] = 'degC'

        salinity = config.getfloat('overflow', 'salinity')
        sa = salinity * xr.ones_like(ct)
        sa.attrs['long_name'] = 'absolute salinity'
        sa.attrs['units'] = 'g kg-1'

        return ct, sa
