import xarray as xr

from polaris.tasks.ocean.single_column.init import Init


class FrazilInit(Init):
    """
    A step for creating the mesh and initial condition for single-column
    frazil test cases

    Attributes
    ----------
    case : str
        The initial condition/forcing case, either ``'melting'`` or
        ``'freezing'``
    """

    def __init__(
        self, component, subdir, case, name='init', forcing_vars=None
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
            The initial condition/forcing case, either ``'melting'`` or
            ``'freezing'``

        name : str, optional
            the name of the step

        forcing_vars : list of str, optional
            the surface forcing fields to apply, see
            ``polaris.tasks.ocean.single_column.init.Init``
        """
        if case not in ('melting', 'freezing'):
            raise ValueError(
                f"case must be 'melting' or 'freezing', got {case!r}"
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

    def _compute_temperature_salinity(self, config, ds, x_cell):
        """
        Compute the melting or freezing initial temperature and salinity
        profiles.  Salinity increases linearly with depth in both cases.  In
        the melting case, temperature is a constant value above a
        transition depth and a different constant value below it.  In the
        freezing case, temperature is uniform (and close to the local
        freezing point once frazil is enabled).
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
            temperature_vert = xr.where(
                z_mid > -transition_depth,
                temperature_upper,
                temperature_lower,
            )
        else:
            temperature_freezing = section.getfloat('temperature_freezing')
            temperature_vert = temperature_freezing * xr.ones_like(z_mid)

        temperature, _ = xr.broadcast(temperature_vert, x_cell)
        temperature = temperature.transpose('nCells', 'nVertLevels')
        temperature = temperature.expand_dims(dim='Time', axis=0)

        return temperature, salinity
