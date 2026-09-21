import numpy as np

from polaris.constants import get_constant
from polaris.ocean.eos import compute_density
from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.single_column.thermo.analysis import CP0_SW


class Analysis(OceanIOStep):
    """
    A step that compares the ``forward_constant`` (all shortwave heating
    absorbed in the surface layer) and ``forward_pen`` (Omega's
    penetrating-shortwave-radiation scheme) runs of the ``shortwave_pen``
    task.

    Two quantities are checked:

    * the column-integrated heating (the mass-weighted temperature change
      summed over the water column) should be identical between the two
      runs, since both are driven by the same incident surface flux and the
      extinction coefficients used to build the penetrating-shortwave
      forcing are large enough that a negligible amount of shortwave flux
      escapes through the bottom of the column
    * the column potential energy is expected to increase more for the
      penetrating-shortwave run, since heat deposited at depth lowers
      density deeper in the water column, producing a larger increase in
      column potential energy than concentrating all heating at the
      surface
    """

    def __init__(self, component, indir, init, constant_step, pen_step):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        init : polaris.Step
            The initial-condition step providing the mesh

        constant_step : polaris.Step
            The forward step with all shortwave heating absorbed at the
            surface

        pen_step : polaris.Step
            The forward step with penetrating shortwave radiation enabled
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{init.path}/init.nc',
        )
        self.add_input_file(
            filename='output_constant.nc',
            work_dir_target=f'{constant_step.path}/output.nc',
        )
        self.add_input_file(
            filename='output_pen.nc',
            work_dir_target=f'{pen_step.path}/output.nc',
        )

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger
        tol = config.getfloat(
            'single_column_shortwave_pen', 'heating_error_tolerance'
        )
        rho_sw = get_constant('seawater_density_reference')
        gravity = get_constant('standard_acceleration_of_gravity')

        ds_mesh = self.open_model_dataset('mesh.nc', config=config)
        area = ds_mesh['areaCell'].values.astype(float)

        ds_init = self.open_model_dataset('init.nc', config=config)
        ds_const = self.open_model_dataset('output_constant.nc', config=config)
        ds_pen = self.open_model_dataset('output_pen.nc', config=config)

        heat_const = _column_heating(ds_init, ds_const, area, rho_sw)
        heat_pen = _column_heating(ds_init, ds_pen, area, rho_sw)

        rel_err = abs(heat_const - heat_pen) / abs(heat_const)
        logger.info(
            'Column-integrated heating over the run:\n'
            f'  constant (surface-absorbed): {heat_const:.6e} J\n'
            f'  penetrating shortwave:       {heat_pen:.6e} J\n'
            f'  relative difference:         {rel_err:.3e} (tol {tol:g})'
        )
        if rel_err > tol:
            raise ValueError(
                'The column-integrated heating differs between the '
                'constant-absorption and penetrating-shortwave runs by '
                f'more than the tolerance ({rel_err:.3e} > {tol:g}).'
            )

        pe0 = _potential_energy(ds_init, config, gravity, time_index=0)
        pe_const = _potential_energy(ds_const, config, gravity, time_index=-1)
        pe_pen = _potential_energy(ds_pen, config, gravity, time_index=-1)
        dpe_const = pe_const - pe0
        dpe_pen = pe_pen - pe0
        logger.info(
            'Column potential energy change over the run:\n'
            f'  constant (surface-absorbed): {dpe_const:.6e} J/m^2\n'
            f'  penetrating shortwave:       {dpe_pen:.6e} J/m^2'
        )
        if dpe_pen <= dpe_const:
            raise ValueError(
                'Expected the penetrating-shortwave run, which deposits '
                'heat deeper in the water column, to increase the column '
                'potential energy more than the constant-absorption run, '
                'which concentrates the heating at the surface '
                f'(dPE_pen={dpe_pen:.6e} <= dPE_const={dpe_const:.6e}).'
            )


def _pick(ds, *names):
    """Return the first variable in ``names`` present in ``ds``."""
    for name in names:
        if name in ds:
            return ds[name]
    raise KeyError(
        f'None of {names} found in dataset (available: {list(ds.data_vars)})'
    )


def _at_time(da, time_index):
    """Select the given time index from ``da``, if it has a time dimension"""
    for time_dim in ('time', 'Time'):
        if time_dim in da.dims:
            return da.isel({time_dim: time_index})
    return da


def _column_heating(ds_init, ds_final, area, rho_sw):
    """
    The change in column-integrated heat content (J), summed over the
    domain, between the initial condition and the final snapshot of
    ``ds_final``
    """
    thickness0 = _at_time(
        _pick(ds_init, 'PseudoThickness', 'layerThickness'), 0
    )
    temperature0 = _at_time(_pick(ds_init, 'Temperature', 'temperature'), 0)
    thickness1 = _at_time(
        _pick(ds_final, 'PseudoThickness', 'layerThickness'), -1
    )
    temperature1 = _at_time(_pick(ds_final, 'Temperature', 'temperature'), -1)

    dims = thickness0.dims
    vert_dim = 'NVertLayers' if 'NVertLayers' in dims else 'nVertLevels'

    ht0 = (thickness0 * temperature0).sum(dim=vert_dim).values.astype(float)
    ht1 = (thickness1 * temperature1).sum(dim=vert_dim).values.astype(float)
    return float(np.sum(rho_sw * CP0_SW * area * (ht1 - ht0)))


def _potential_energy(ds, config, gravity, time_index):
    """
    The domain-averaged column potential energy (J/m^2),
    ``g * sum(rho * z_mid * thickness)``, at the given time index
    """
    thickness = _at_time(
        _pick(ds, 'PseudoThickness', 'layerThickness'), time_index
    )
    temperature = _at_time(_pick(ds, 'Temperature', 'temperature'), time_index)
    salinity = _at_time(_pick(ds, 'Salinity', 'salinity'), time_index)
    z_mid = _at_time(_pick(ds, 'zMid'), time_index)

    dims = thickness.dims
    vert_dim = 'NVertLayers' if 'NVertLayers' in dims else 'nVertLevels'

    density = compute_density(config, temperature, salinity)
    pe_per_cell = gravity * (density * z_mid * thickness).sum(dim=vert_dim)
    return float(pe_per_cell.mean().values)
