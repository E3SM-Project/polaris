import numpy as np
import xarray as xr
from mpas_tools.io import open_dataset, write_netcdf
from mpas_tools.logging import LoggingContext
from mpas_tools.mesh.conversion import cull
from mpas_tools.mesh.creation.sort_mesh import sort_mesh
from mpas_tools.mesh.cull import cull_dataset

from polaris.constants import get_constant
from polaris.coriolis import add_coriolis_to_dataset
from polaris.model_step import make_graph_file
from polaris.ocean.ice_shelf import (
    compute_freezing_temperature,
    compute_land_ice_draft_from_pressure,
)
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.isomip_plus.mesh.xy import add_isomip_plus_xy

# the profiles used for the initial condition and for restoring in each
# experiment
PROFILES = {
    'ocean0': {'init': 'warm', 'restoring': 'warm'},
    'ocean1': {'init': 'cold', 'restoring': 'warm'},
    'ocean2': {'init': 'warm', 'restoring': 'cold'},
    'inception': {'init': 'warm', 'restoring': 'warm'},
    'wetting': {'init': 'warm', 'restoring': 'warm'},
    'drying': {'init': 'warm', 'restoring': 'warm'},
}


class Init(OceanIOStep):
    """
    A step for creating the mesh, initial condition and forcing for an
    ISOMIP+ task

    Attributes
    ----------
    experiment : str
        The ISOMIP+ experiment

    thin_film : bool
        Whether a thin film is present under grounded ice, as it is for
        experiments with time-varying geometry
    """

    def __init__(
        self, component, indir, culled_mesh, topo, experiment, thin_film
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` will be appended

        culled_mesh : polaris.Step
            The shared step that culled the mesh to the ISOMIP+ domain

        topo : polaris.Step
            The shared step that produced the task's topography on the culled
            mesh

        experiment : str
            The ISOMIP+ experiment

        thin_film : bool
            Whether a thin film is present under grounded ice, as it is for
            experiments with time-varying geometry
        """
        super().__init__(component=component, name='init', indir=indir)
        if experiment not in PROFILES:
            raise ValueError(f'Unexpected experiment {experiment}')
        self.experiment = experiment
        self.thin_film = thin_film

        self.add_input_file(
            filename='culled_mesh.nc',
            work_dir_target=f'{culled_mesh.path}/culled_mesh.nc',
        )
        self.add_input_file(
            filename='topography.nc',
            work_dir_target=f'{topo.path}/topography_remapped.nc',
        )
        self.add_output_file(filename='forcing.nc')
        if thin_film:
            self.add_output_file(filename='land_ice_forcing.nc')

    def setup(self):
        """
        Add the files the ocean model will read as outputs
        """
        super().setup()
        self.add_output_files_for_ocean_model_input(
            graph_filename='culled_graph.info'
        )

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        ds_mesh, ds_topo = self._cull_mesh()

        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        mesh_filename = self.get_horiz_mesh_filename()
        self.write_horiz_mesh_dataset(ds_mesh, mesh_filename, config)
        make_graph_file(
            mesh_filename=mesh_filename, graph_filename='culled_graph.info'
        )

        if 'Time' in ds_topo.dims:
            ds_topo_init = ds_topo.isel(Time=0)
        else:
            ds_topo_init = ds_topo

        ds = self._compute_geometry(ds_mesh, ds_topo_init)
        init_vertical_coord(config, ds)
        self._compute_state(ds)

        self.write_vert_coord_dataset(
            ds, self.get_vert_coord_filename(), config
        )
        self.write_initial_state_dataset(ds, self.get_init_filename(), config)

        self._write_forcing(ds)
        if self.thin_film:
            self._write_land_ice_forcing(ds_topo)

    def _cull_mesh(self):
        """
        Remove cells that never hold ocean from the mesh and topography.
        With a thin film, all cells are kept.
        """
        logger = self.logger
        ds_base = open_dataset('culled_mesh.nc')
        ds_topo = open_dataset('topography.nc')

        if self.thin_film:
            logger.info(
                f'Keeping all {ds_base.sizes["nCells"]} cells, with a thin '
                f'film under grounded ice'
            )
            return ds_base, ds_topo

        min_ocean_fraction = self.config.getfloat(
            'isomip_plus', 'min_ocean_fraction'
        )
        ocean_fraction = (
            ds_topo.landIceFloatingFraction + ds_topo.openOceanFraction
        )
        # NaN fractions compare as False, so cells without data are removed
        keep = ocean_fraction >= min_ocean_fraction
        logger.info(
            f'Keeping {int(keep.sum())} of {ds_base.sizes["nCells"]} cells '
            f'that hold ocean'
        )

        ds_mask = xr.Dataset()
        ds_mask['regionCellMasks'] = xr.where(keep, 0, 1).expand_dims(
            dim='nRegions', axis=1
        )

        with LoggingContext(name=__name__, logger=logger) as logger:
            ds_mesh = cull(ds_base, dsMask=ds_mask, logger=logger, dir='.')

        # sort the cell, edge and vertex indices for better performances
        ds_mesh = sort_mesh(ds_mesh)
        add_isomip_plus_xy(ds_mesh)

        ds_topo = cull_dataset(
            ds=ds_topo, ds_base_mesh=ds_base, ds_culled_mesh=ds_mesh
        )
        return ds_mesh, ds_topo

    def _compute_geometry(self, ds_mesh, ds_topo):
        """
        Compute the land-ice masks and fractions, pressure, SSH and bottom
        depth
        """
        config = self.config
        logger = self.logger
        section = config['isomip_plus']
        mask_variable = config.get('ssh_adjustment', 'mask_variable')

        ds = ds_mesh.copy()

        land_ice_fraction, floating_fraction, land_ice_mask = (
            self._mask_land_ice_fractions(ds_topo)
        )
        floating_mask = np.logical_and(land_ice_mask, floating_fraction > 0.0)

        ds['landIceMask'] = land_ice_mask.astype(int)
        ds['landIceFloatingMask'] = floating_mask.astype(int)
        ds['landIceFraction'] = land_ice_fraction
        ds['landIceFloatingFraction'] = floating_fraction
        ds['landIceGroundedFraction'] = ds_topo.landIceGroundedFraction
        ds['landIcePressure'] = ds_topo.landIcePressure

        min_ssh_adjust_fraction = section.getfloat(
            'min_ssh_adjust_land_ice_fraction'
        )
        ssh_adjust_mask = ds_topo.landIceFraction > min_ssh_adjust_fraction
        ds[mask_variable] = ssh_adjust_mask.astype(int)

        bottom_depth = -ds_topo.bedrockTopography
        # the initial SSH is where ice with the prescribed pressure would
        # float, limited by the bed
        draft = self._draft_from_pressure(ds_topo.landIcePressure)
        if self.thin_film:
            min_column_thickness = section.getfloat(
                'min_column_thickness_thin_film'
            )
            # grounded ice is heavier than the water it would displace, so
            # the draft computed from its pressure is below the bed
            thin_film_mask = draft <= -bottom_depth
            ds['thinFilmMask'] = thin_film_mask.astype(int)
            logger.info(
                f'{int(thin_film_mask.sum())} cells have a thin film under '
                f'grounded ice'
            )
        else:
            min_column_thickness = section.getfloat('min_column_thickness')
        ssh = np.maximum(draft, -bottom_depth)
        ds['landIceDraft'] = ssh

        # deepen the bottom where needed to keep a minimum column thickness
        min_depth = -ssh + min_column_thickness
        too_thin = bottom_depth < min_depth
        ds['bottomDepth'] = xr.where(too_thin, min_depth, bottom_depth)
        logger.info(
            f'Adjusted bottomDepth for {int(too_thin.sum())} cells to '
            f'achieve a minimum column thickness of {min_column_thickness} m'
        )

        # init_vertical_coord() adds the Time dimension to ssh
        ds['ssh'] = ssh

        for var in [
            'landIceMask',
            'landIceFloatingMask',
            'landIceFraction',
            'landIceFloatingFraction',
            'landIceGroundedFraction',
            'landIcePressure',
            'landIceDraft',
        ]:
            ds[var] = ds[var].expand_dims(dim='Time', axis=0)

        return ds

    def _mask_land_ice_fractions(self, ds_topo):
        """
        Get the land-ice fractions, set to zero outside of the land-ice mask,
        and the mask itself
        """
        min_land_ice_fraction = self.config.getfloat(
            'isomip_plus', 'min_land_ice_fraction'
        )
        land_ice_fraction = ds_topo.landIceFraction
        land_ice_mask = land_ice_fraction > min_land_ice_fraction
        land_ice_fraction = land_ice_fraction.where(land_ice_mask, 0.0)
        floating_fraction = ds_topo.landIceFloatingFraction.where(
            land_ice_mask, 0.0
        )
        return land_ice_fraction, floating_fraction, land_ice_mask

    def _draft_from_pressure(self, land_ice_pressure):
        """
        Get the draft of floating ice with the given land-ice pressure
        """
        ocean_density = self.config.getfloat('isomip_plus', 'ocean_density')
        return compute_land_ice_draft_from_pressure(
            land_ice_pressure=land_ice_pressure,
            modify_mask=land_ice_pressure > 0.0,
            ref_density=ocean_density,
        )

    def _compute_state(self, ds):
        """
        Compute the initial temperature, salinity and velocity
        """
        profile = PROFILES[self.experiment]['init']
        temperature, salinity = self._get_profiles(ds, profile)

        if self.thin_film:
            # thin-film cells hold fresh water at the freezing point
            thin_film_mask = ds.thinFilmMask == 1
            salinity = xr.where(thin_film_mask, 0.0, salinity)
            freezing_temp = compute_freezing_temperature(
                config=self.config,
                salinity=salinity,
                pressure=ds.landIcePressure,
            )
            temperature = xr.where(thin_film_mask, freezing_temp, temperature)
            temperature = temperature.transpose(
                'Time', 'nCells', 'nVertLevels'
            )
            salinity = salinity.transpose('Time', 'nCells', 'nVertLevels')

        ds['temperature'] = temperature
        ds['salinity'] = salinity

        normal_velocity = xr.zeros_like(ds.xEdge)
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        ds['normalVelocity'] = normal_velocity.expand_dims(dim='Time', axis=0)

    def _get_profiles(self, ds, profile):
        """
        Get the temperature and salinity for the given profile, linear in
        depth between the sea surface and the deepest ocean floor
        """
        config = self.config
        section = config['isomip_plus']
        top_temp = section.getfloat(f'{profile}_top_temp')
        bot_temp = section.getfloat(f'{profile}_bot_temp')
        top_sal = section.getfloat(f'{profile}_top_sal')
        bot_sal = section.getfloat(f'{profile}_bot_sal')

        max_bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')
        frac = -ds.zMid / max_bottom_depth

        temperature = (1.0 - frac) * top_temp + frac * bot_temp
        salinity = (1.0 - frac) * top_sal + frac * bot_sal
        return temperature, salinity

    def _write_forcing(self, ds):
        """
        Write the restoring and evaporation forcing
        """
        config = self.config
        section = config['isomip_plus_forcing']
        restore_rate = section.getfloat('restore_rate')
        restore_evap_rate = section.getfloat('restore_evap_rate')
        restore_xmin = section.getfloat('restore_xmin')
        restore_xmax = section.getfloat('restore_xmax')

        ref_density = get_constant('seawater_density_reference')
        heat_capacity = get_constant(
            'seawater_specific_heat_capacity_reference'
        )
        s_per_day = get_constant('day_to_s')

        profile = PROFILES[self.experiment]['restoring']
        temperature, salinity = self._get_profiles(ds, profile)

        ds_forcing = xr.Dataset()
        ds_forcing['temperatureInteriorRestoringValue'] = temperature
        ds_forcing['salinityInteriorRestoringValue'] = salinity

        x_cell = ds.xIsomipCell
        x_frac = np.maximum(
            (x_cell - restore_xmin) / (restore_xmax - restore_xmin), 0.0
        )
        x_frac = x_frac.broadcast_like(temperature)

        # convert from 1/days to 1/s
        rate = x_frac * restore_rate / s_per_day
        ds_forcing['temperatureInteriorRestoringRate'] = rate
        ds_forcing['salinityInteriorRestoringRate'] = rate

        # "evaporation" in the restoring region offsets the melt water,
        # removing salt and heat at the surface restoring values
        mask = np.logical_and(x_cell >= restore_xmin, x_cell <= restore_xmax)
        mask = mask.expand_dims(dim='Time', axis=0)
        # convert m/yr to m/s, negative for evaporation
        evap_rate = -restore_evap_rate / (s_per_day * 365.0)
        top_temp = config.getfloat('isomip_plus', f'{profile}_top_temp')
        top_sal = config.getfloat('isomip_plus', f'{profile}_top_sal')
        ds_forcing['evaporationFlux'] = mask * ref_density * evap_rate
        # PSU m/s to kg m^-2 s^-1
        ds_forcing['seaIceSalinityFlux'] = mask * evap_rate * top_sal
        # C m/s to W m^-2
        ds_forcing['seaIceHeatFlux'] = (
            mask * evap_rate * top_temp * ref_density * heat_capacity
        )

        write_netcdf(ds_forcing, 'forcing.nc')

    def _write_land_ice_forcing(self, ds_topo):
        """
        Write the time-varying land-ice forcing from all records of the
        topography
        """
        land_ice_fraction, floating_fraction, _ = (
            self._mask_land_ice_fractions(ds_topo)
        )
        # MPAS-Ocean computes the draft from the pressure, so the draft is
        # not part of the forcing
        ds_out = xr.Dataset()
        ds_out['xtime'] = ds_topo.xtime
        ds_out['landIcePressureForcing'] = ds_topo.landIcePressure
        ds_out.landIcePressureForcing.attrs['units'] = 'Pa'
        ds_out.landIcePressureForcing.attrs['long_name'] = (
            'Pressure from the weight of land ice at the ice-ocean interface'
        )
        ds_out['landIceFractionForcing'] = land_ice_fraction
        ds_out.landIceFractionForcing.attrs['long_name'] = (
            'The fraction of each cell covered by land ice'
        )
        ds_out['landIceFloatingFractionForcing'] = floating_fraction
        ds_out.landIceFloatingFractionForcing.attrs['long_name'] = (
            'The fraction of each cell covered by floating land ice'
        )
        write_netcdf(ds_out, 'land_ice_forcing.nc', char_dim_name='StrLen')
