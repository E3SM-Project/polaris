import numpy as np
import xarray as xr

from polaris.constants import get_constant
from polaris.ocean.eos import compute_ct_freezing
from polaris.tasks.ocean.single_column.init import Init


class FrazilInit(Init):
    """
    A step for creating the mesh and initial condition for single-column
    frazil test cases

    Attributes
    ----------
    case : str
        The initial condition/forcing case, one of ``'melting'``,
        ``'freezing'`` or ``'melt_short'``

    at_freezing : bool
        For the ``'freezing'`` case, whether to initialize temperature at the
        local EOS freezing point rather than at ``temperature_freezing``
    """

    def __init__(
        self,
        component,
        subdir,
        case,
        name='init',
        forcing_vars=None,
        at_freezing=False,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step will go into

        case : str
            The initial condition/forcing case, one of ``'melting'``,
            ``'freezing'`` or ``'melt_short'``

        name : str, optional
            the name of the step

        forcing_vars : list of str, optional
            the surface forcing fields to apply, see
            ``polaris.tasks.ocean.single_column.init.Init``

        at_freezing : bool, optional
            For the ``'freezing'`` case, initialize temperature at the local
            EOS freezing point rather than at ``temperature_freezing``
        """
        if case not in ('melting', 'freezing', 'melt_short'):
            raise ValueError(
                "case must be 'melting', 'freezing' or 'melt_short', got "
                f'{case!r}'
            )
        if forcing_vars is None:
            forcing_vars = ['latent_heat_flux'] if case == 'freezing' else []
        super().__init__(
            component=component,
            subdir=subdir,
            name=name,
            forcing_vars=forcing_vars,
        )
        self.case = case
        self.at_freezing = at_freezing

    def _compute_temperature_salinity(self, config, ds, x_cell):
        """
        Compute the melting or freezing initial temperature and salinity
        profiles.  Salinity increases linearly with depth in both cases.  In
        the melting case, temperature is a constant value above a
        transition depth and a different constant value below it.  In the
        freezing case, temperature is uniform (and close to the local
        freezing point once frazil is enabled), or exactly at the local
        freezing point if ``at_freezing`` is set.  In the ``melt_short``
        case, temperature is constant above the transition depth and a fixed
        amount below the local freezing point beneath it.
        """
        section = config['single_column_frazil']
        salinity_surface = section.getfloat('salinity_surface')
        dsdz = section.getfloat('dsdz')

        z_mid = ds.refZMid

        # depth increases downward from the surface (z_mid <= 0)
        depth = -z_mid
        salinity_vert = salinity_surface + dsdz * depth
        salinity, _ = xr.broadcast(salinity_vert, x_cell)
        salinity = salinity.transpose('nCells', 'nVertLevels')
        salinity = salinity.expand_dims(dim='Time', axis=0)

        if self.case == 'melting':
            temperature_upper = section.getfloat('temperature_upper_melting')
            temperature_lower = section.getfloat('temperature_lower_melting')
            transition_depth = section.getfloat('transition_depth_melting')
            transition_width = section.getfloat('transition_width_melting')
            depth = -z_mid
            transition = (depth - transition_depth) / transition_width
            smooth = 0.5 * (1.0 + np.tanh(transition))
            temperature_vert = (
                temperature_upper
                + (temperature_lower - temperature_upper) * smooth
            )
        elif self.case == 'melt_short':
            temperature_top = section.getfloat('temperature_top_melt_short')
            supercooling = section.getfloat('supercooling_melt_short')
            transition_depth = section.getfloat('transition_depth_melt_short')
            ct_freezing = compute_ct_freezing(
                config,
                salinity.isel(Time=0, nCells=0),
                pressure=self._compute_pressure(z_mid),
            )
            temperature_vert = xr.where(
                depth < transition_depth,
                temperature_top,
                ct_freezing - supercooling,
            )
        elif self.at_freezing:
            temperature_vert = compute_ct_freezing(
                config,
                salinity.isel(Time=0, nCells=0),
                pressure=self._compute_pressure(z_mid),
            )
        else:
            temperature_freezing = section.getfloat('temperature_freezing')
            temperature_vert = temperature_freezing * xr.ones_like(z_mid)

        temperature, _ = xr.broadcast(temperature_vert, x_cell)
        temperature = temperature.transpose('nCells', 'nVertLevels')
        temperature = temperature.expand_dims(dim='Time', axis=0)

        self._report_below_freezing_fraction(
            config=config,
            temperature=temperature,
            salinity=salinity,
            z_mid=z_mid,
            layer_thickness=ds.layerThickness,
        )

        return temperature, salinity

    @staticmethod
    def _compute_pressure(z_mid):
        """Hydrostatic pressure; the init has ssh = 0, so z_mid is exact."""
        return (
            -z_mid
            * get_constant('seawater_density_reference')
            * get_constant('standard_acceleration_of_gravity')
        )

    def _report_below_freezing_fraction(
        self, config, temperature, salinity, z_mid, layer_thickness
    ):
        """Report the water-column fraction below the EOS freezing point."""
        freezing_temperature = compute_ct_freezing(
            config,
            salinity.isel(Time=0, nCells=0),
            pressure=self._compute_pressure(z_mid),
        )
        below_freezing = (
            temperature.isel(Time=0, nCells=0) < freezing_temperature
        )
        below_freezing_thickness = (
            layer_thickness.isel(Time=0, nCells=0) * below_freezing
        ).sum()
        fraction = (
            below_freezing_thickness
            / layer_thickness.isel(Time=0, nCells=0).sum()
        )
        self.logger.info(
            'Initial water column below the EOS freezing point: '
            f'{100.0 * float(fraction):.1f}%',
        )
