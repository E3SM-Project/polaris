"""
The initial state of the mixed-layer eddies tasks: the ice-free experiment
of Shrestha & Manucharyan (2022), a mixed layer carrying two opposing
sinusoidal salinity fronts over an Arctic profile, at rest on a doubly
periodic f-plane.

``itp77.csv`` is a profile from Ice-Tethered Profiler 77 (Krishfield et al.
2008; Toole et al. 2011) at 1 dbar spacing from 5 to 153 dbar, copied from
the Compass database file ``mixed_layer_restrat/itp77.csv``.  Its columns
are depth (m, negative), pressure (dbar), temperature (degC) and salinity
(g kg-1).
"""

import importlib.resources as imp_res

import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.ocean.viz.transect import compute_transect, plot_transect
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris.attrs import set_attrs
from polaris.coriolis import add_coriolis_to_dataset
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.eos import compute_specvol
from polaris.ocean.init_state import (
    add_density_from_specvol,
    add_quiescent_normal_velocity,
    layer_thickness_from_geom_interfaces,
)
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical.pstar_init import PStarInitStep
from polaris.ocean.vertical.ztilde import (
    geom_height_from_pseudo_height,
    pressure_from_z_tilde,
)
from polaris.viz import plot_horiz_field

# The number of times init_tracers() refines the geometric heights at which
# it evaluates the salinity profile.  The density varies by less than 1%,
# so geometric and pseudo-heights differ by well under a meter and this
# converges to round-off in a few passes.
GEOM_HEIGHT_ITER_COUNT = 3


def read_itp77_salinity():
    """
    Read the ITP77 salinity profile

    Returns
    -------
    z : numpy.ndarray
        Geometric heights (m, negative), increasing from the deepest

    salinity : numpy.ndarray
        Salinity (g kg-1) at ``z``
    """
    path = imp_res.files('polaris.tasks.ocean.mixed_layer_eddies').joinpath(
        'itp77.csv'
    )
    with path.open() as csv_file:
        data = np.loadtxt(csv_file, delimiter=',', skiprows=1)
    z = data[:, 0]
    salinity = data[:, 3]
    order = np.argsort(z)
    return z[order], salinity[order]


def compute_background_salinity(z, z_profile, salinity_profile, ml_depth):
    """
    Compute the background salinity: the profile below the base of the
    mixed layer and its value at the base above it

    Parameters
    ----------
    z : xarray.DataArray or numpy.ndarray
        Geometric heights (m, negative) at which to evaluate the profile

    z_profile : numpy.ndarray
        Geometric heights of the profile, increasing

    salinity_profile : numpy.ndarray
        Salinity of the profile at ``z_profile``

    ml_depth : float
        The depth of the base of the mixed layer, H_m (m, positive)

    Returns
    -------
    salinity : xarray.DataArray or numpy.ndarray
        The background salinity at ``z``
    """
    z_clipped = np.minimum(z, -ml_depth)
    salinity = np.interp(z_clipped, z_profile, salinity_profile)
    if isinstance(z, xr.DataArray):
        salinity = xr.DataArray(salinity, dims=z.dims, coords=z.coords)
    return salinity


def compute_density_anomaly(config, y, z, y_period):
    """
    Compute the density anomaly of the mixed layer and its fronts,
    Z_S(z) [Delta rho_y Y_S(y) - Delta rho_z], from Shrestha & Manucharyan
    (2022), their eq. 5

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with the ``mixed_layer_eddies`` section

    y : xarray.DataArray
        The y coordinate (m)

    z : xarray.DataArray
        Geometric heights (m, negative) relative to the sea surface

    y_period : float
        The periodic length of the domain in y (m), which is the wavelength
        of the fronts

    Returns
    -------
    density_anomaly : xarray.DataArray
        The density anomaly (kg m-3)
    """
    section = config['mixed_layer_eddies']
    ml_depth = section.getfloat('mixed_layer_depth')
    taper_width = section.getfloat('mixed_layer_taper_width')
    drho_y = section.getfloat('front_density_difference')
    drho_z = section.getfloat('mixed_layer_density_offset')

    z_shape = 0.5 * (1.0 + np.tanh((z + ml_depth) / taper_width))
    y_shape = np.sin(2.0 * np.pi * (y - 0.5 * y_period) / y_period)
    return z_shape * (drho_y * y_shape - drho_z)


class Init(PStarInitStep, OceanIOStep):
    """
    A step for creating a mesh and initial condition for mixed-layer eddies
    tasks on the p-star vertical coordinate

    Attributes
    ----------
    resolution : float
        The horizontal resolution in km
    """

    def __init__(
        self, component, resolution, name='init', subdir=None, indir=None
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The horizontal resolution in km

        name : str, optional
            The name of the step

        subdir : str, optional
            The subdirectory for the step.  If neither this nor ``indir``
            are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(
            component=component, name=name, subdir=subdir, indir=indir
        )
        self.resolution = resolution
        self._geom_z_bot: xr.DataArray | None = None
        self._noise: xr.DataArray | None = None
        self._z_profile: np.ndarray | None = None
        self._salinity_profile: np.ndarray | None = None

    def setup(self):
        """
        Add the mesh, vertical coordinate and initial state as outputs
        """
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
        section = config['mixed_layer_eddies']

        ds_mesh = self._build_mesh()

        bottom_depth = section.getfloat('bottom_depth')
        geom_z_bot = -bottom_depth * xr.ones_like(ds_mesh.xCell)
        set_attrs(geom_z_bot, long_name='seafloor geometric height', units='m')
        self._geom_z_bot = geom_z_bot
        self._z_profile, self._salinity_profile = read_itp77_salinity()
        self._noise = self._make_noise(ds_mesh)

        ds = self.run_pstar_init(ds_mesh=ds_mesh, geom_z_bot=geom_z_bot)

        ds = layer_thickness_from_geom_interfaces(ds)
        ds = add_quiescent_normal_velocity(ds, ds_mesh)
        ds = add_density_from_specvol(ds)

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(ds, 'init.nc', config)

        self._plot_initial_state(ds_mesh, ds)

    def init_tracers(
        self, ds: xr.Dataset
    ) -> tuple[xr.DataArray, xr.DataArray]:
        """
        Initialize conservative temperature and absolute salinity at the
        current p-star layer midpoints.  The salinity profile is defined in
        geometric depth below the sea surface, so it is evaluated at the
        geometric heights that the profile itself implies for this
        coordinate.
        """
        config = self.config
        temperature = config.getfloat('mixed_layer_eddies', 'temperature')

        ct = temperature * xr.ones_like(ds.ZTildeMid)
        ct = ct.transpose('Time', 'nCells', 'nVertLevels')
        set_attrs(ct, long_name='conservative temperature', units='degC')

        pressure = pressure_from_z_tilde(ds.ZTildeMid)
        z_mid = ds.ZTildeMid
        for _ in range(GEOM_HEIGHT_ITER_COUNT):
            sa = self._compute_salinity(ds, z_mid)
            spec_vol = compute_specvol(
                config=config,
                temperature=ct,
                salinity=sa,
                pressure=pressure,
            )
            assert isinstance(spec_vol, xr.DataArray)
            assert self._geom_z_bot is not None
            geom_z_inter, geom_z_mid = geom_height_from_pseudo_height(
                geom_z_bot=self._geom_z_bot,
                h_tilde=ds.PseudoThickness.fillna(0.0),
                spec_vol=spec_vol,
                min_level_cell=ds.minLevelCell - 1,
                max_level_cell=ds.maxLevelCell - 1,
            )
            # heights relative to the top of the column, where the base
            # class anchors the sea surface
            z_mid = geom_z_mid - geom_z_inter.isel(nVertLevelsP1=0)

        sa = self._compute_salinity(ds, z_mid)
        sa = sa.transpose('Time', 'nCells', 'nVertLevels')
        set_attrs(sa, long_name='absolute salinity', units='g kg-1')

        return ct, sa

    def _build_mesh(self):
        """
        Build the doubly periodic planar hex mesh and add the Coriolis
        parameter, writing ``base_mesh.nc``, ``culled_mesh.nc`` and
        ``culled_graph.info``
        """
        config = self.config
        logger = self.logger
        section = config['mixed_layer_eddies']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')

        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        dc = 1e3 * self.resolution
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
        return ds_mesh

    def _make_noise(self, ds_mesh):
        """
        Make the uniform salinity noise that seeds the instability, the same
        in every outer iteration of the p-star initialization
        """
        section = self.config['mixed_layer_eddies']
        amplitude = section.getfloat('salinity_noise_amplitude')
        seed = section.getint('noise_seed')
        nlevels = self.config.getint('vertical_grid', 'vert_levels')
        rng = np.random.default_rng(seed)
        noise = rng.uniform(
            -amplitude, amplitude, size=(1, ds_mesh.sizes['nCells'], nlevels)
        )
        return xr.DataArray(noise, dims=('Time', 'nCells', 'nVertLevels'))

    def _compute_salinity(self, ds, z_mid):
        """
        Compute the salinity at geometric heights ``z_mid`` relative to the
        sea surface: the background profile plus the fronts, converted to
        salinity with the linear equation of state, plus the noise
        """
        config = self.config
        ml_depth = config.getfloat('mixed_layer_eddies', 'mixed_layer_depth')
        # with eos_linear_alpha = 0, drho/dS converts density to salinity
        drho_ds = config.getfloat('ocean', 'eos_linear_beta')
        y_period = float(ds.attrs['y_period'])

        assert self._z_profile is not None
        assert self._salinity_profile is not None
        background = compute_background_salinity(
            z_mid, self._z_profile, self._salinity_profile, ml_depth
        )
        anomaly = compute_density_anomaly(config, ds.yCell, z_mid, y_period)
        return background + anomaly / drho_ds + self._noise

    def _plot_initial_state(self, ds_mesh, ds):
        """
        Plot a cross-front section of salinity and density and the surface
        salinity
        """
        x_mid = float(ds_mesh.xCell.median())
        y_min = float(ds_mesh.yVertex.min())
        y_max = float(ds_mesh.yVertex.max())
        y = xr.DataArray(data=np.linspace(y_min, y_max, 2), dims=('nPoints',))
        x = x_mid * xr.ones_like(y)

        ds_transect = compute_transect(
            x=x,
            y=y,
            ds_horiz_mesh=ds_mesh,
            layer_thickness=ds.layerThickness.isel(Time=0),
            bottom_depth=ds.bottomDepth,
            min_level_cell=ds.minLevelCell - 1,
            max_level_cell=ds.maxLevelCell - 1,
            spherical=False,
        )

        fields = [
            ('salinity', 'cmo.haline', r'g kg$^{-1}$'),
            ('Density', 'cmo.dense', r'kg m$^{-3}$'),
        ]
        for field_name, cmap, units in fields:
            field = ds[field_name].isel(Time=0)
            plot_transect(
                ds_transect=ds_transect,
                mpas_field=field,
                title=f'{field_name} at x={1e-3 * x_mid:.1f} km',
                out_filename=f'initial_{field_name}_section.png',
                vmin=float(field.min()),
                vmax=float(field.max()),
                cmap=cmap,
                colorbar_label=units,
                color_start_and_end=True,
            )

        surface_salinity = ds.salinity.isel(Time=0, nVertLevels=0)
        plot_horiz_field(
            ds_mesh,
            surface_salinity,
            'initial_surface_salinity.png',
            vmin=float(surface_salinity.min()),
            vmax=float(surface_salinity.max()),
            cmap='cmo.haline',
            transect_x=x,
            transect_y=y,
        )
