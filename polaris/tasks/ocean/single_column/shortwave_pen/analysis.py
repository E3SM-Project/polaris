from polaris.constants import get_constant
from polaris.ocean.eos import compute_density
from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.single_column.shortwave_pen.jerlov import (
    JERLOV_WATER_TYPES,
)


class Analysis(OceanIOStep):
    """
    A step that checks how the column potential energy of the ``jerlov`` runs
    of the ``shortwave_pen`` task varies with water clarity.

    Every run is driven by the same incident surface shortwave flux, so they
    all add the same energy to the column; the conservation of that energy is
    checked by the property checks on the forward steps themselves.  What
    differs is where the heat ends up.  Clearer water lets the flux penetrate
    further, lowering density deeper in the column, which raises the column
    potential energy more than depositing the same heat near the surface.
    The check therefore requires the potential energy gain to decrease as the
    water grows more turbid.

    Attributes
    ----------
    water_types : list of int
        The Jerlov water types being compared, in increasing order of
        turbidity
    """

    def __init__(self, component, indir, init, water_types):
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

        water_types : list of int
            The Jerlov water types to compare
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.water_types = sorted(water_types)
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{init.path}/init.nc',
        )
        for water_type in self.water_types:
            self.add_input_file(
                filename=f'output_jerlov_type{water_type}.nc',
                target=f'../forward_jerlov_type{water_type}/output.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger
        gravity = get_constant('standard_acceleration_of_gravity')

        ds_init = self.open_model_dataset('init.nc', config=config)
        pe0 = _potential_energy(ds_init, config, gravity, time_index=0)

        changes = dict()
        for water_type in self.water_types:
            ds = self.open_model_dataset(
                f'output_jerlov_type{water_type}.nc', config=config
            )
            pe = _potential_energy(ds, config, gravity, time_index=-1)
            changes[water_type] = pe - pe0

        summary = '\n'.join(
            f'  type {water_type} ({JERLOV_WATER_TYPES[water_type]}): '
            f'{changes[water_type]:.6e} J/m^2'
            for water_type in self.water_types
        )
        logger.info(f'Column potential energy change over the run:\n{summary}')

        if len(self.water_types) < 2:
            logger.info(
                'Fewer than two water types were run, so the potential '
                'energy comparison is skipped'
            )
            return

        for clearer, murkier in zip(
            self.water_types[:-1], self.water_types[1:], strict=False
        ):
            if changes[clearer] <= changes[murkier]:
                raise ValueError(
                    f'Expected Jerlov water type {clearer} '
                    f'({JERLOV_WATER_TYPES[clearer]}), which is clearer and '
                    f'so deposits heat deeper, to increase the column '
                    f'potential energy more than water type {murkier} '
                    f'({JERLOV_WATER_TYPES[murkier]}) '
                    f'({changes[clearer]:.6e} <= {changes[murkier]:.6e}).'
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
