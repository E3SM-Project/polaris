from polaris.ocean.model import OceanModelStep
from polaris.resolution import resolution_to_string

# The pressure-gradient schemes a variant can be run with, mapping the config
# spelling to Omega's PressureGradType.  There is no "centered limit" of the
# finite-volume scheme: the two are separate implementations and no setting
# reduces one to the other, so this is a choice between them rather than a
# parameter of one.
SCHEMES = {
    'centered': 'Centered',
    'finite_volume': 'FiniteVolume',
}

# Which field in init.nc is the Polaris counterpart of each scheme's output.
# omega_vs_polaris compares Omega against the matching one; comparing against
# the wrong one would measure the difference between two schemes and call it
# an implementation disagreement.
SCHEME_HPGA = {
    'centered': 'HPGA',
    'finite_volume': 'HPGAFiniteVolume',
}


class Forward(OceanModelStep):
    """
    This step performs a forward run for a single time step, writing out
    the normal-velocity tendency (which is just the pressure gradient
    acceleration) along with other diagnostics.

    Attributes
    ----------
    horiz_res : float
        The horizontal resolution in km

    scheme : str
        The pressure-gradient scheme, a key of :py:data:`SCHEMES`
    """

    def __init__(
        self, component, horiz_res, init, indir, scheme, subdir_suffix=None
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        horiz_res : float
            The horizontal resolution in km

        init : polaris.tasks.ocean.horiz_press_grad.init.Init
            The init step for this resolution

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        scheme : str
            The pressure-gradient scheme to run, a key of :py:data:`SCHEMES`

        subdir_suffix : str, optional
            A suffix used in place of the horizontal resolution in the step
            name, for sweeps that repeat a horizontal resolution
        """
        if scheme not in SCHEMES:
            raise ValueError(
                f'Unknown pressure-gradient scheme {scheme!r}; expected one '
                f'of {sorted(SCHEMES)}.'
            )
        self.horiz_res = horiz_res
        self.scheme = scheme
        if subdir_suffix is None:
            suffix = resolution_to_string(horiz_res)
        else:
            suffix = subdir_suffix
        super().__init__(
            component=component,
            name=f'forward_{suffix}_{scheme}',
            indir=indir,
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
        )

        self.add_horiz_mesh_input_file(
            work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc'
        )
        self.add_init_input_file(work_dir_target=f'{init.path}/init.nc')

        validate_vars = ['NormalVelocityTend']
        self.add_output_file('output.nc', validate_vars=validate_vars)

    def setup(self):
        """
        Fill in config options in the forward.yaml file based on config options
        """
        super().setup()

        quadrature_points = self.config.getint(
            'horiz_press_grad', 'quadrature_points'
        )
        self.add_yaml_file(
            'polaris.tasks.ocean.horiz_press_grad',
            'forward.yaml',
            template_replacements=dict(
                pressure_grad_type=SCHEMES[self.scheme],
                quadrature_points=quadrature_points,
            ),
        )
