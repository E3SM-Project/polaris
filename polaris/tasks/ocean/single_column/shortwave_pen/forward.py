from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.shortwave_pen.jerlov import (
    omega_jerlov_equivalent,
)


class ShortwavePenForward(Forward):
    """
    A forward step for the ``shortwave_pen`` task that distributes the
    incident shortwave flux through the water column, either with MPAS-Ocean's
    two-band Jerlov scheme or with Omega's three-band penetrating-shortwave-
    radiation tendency term.

    With ``scheme='jerlov'`` the two models are configured to absorb the flux
    identically, so their profiles can be compared directly.  With
    ``scheme='manizza'``, which Omega alone supports, the red and blue bands
    are given distinct extinction coefficients to show what the third band
    changes.

    Attributes
    ----------
    water_type : int
        The Jerlov water type, between 1 (I) and 5 (III)

    scheme : {'jerlov', 'manizza'}
        Whether the red and blue bands share the Jerlov visible extinction
        coefficient or take distinct Manizza coefficients
    """

    def __init__(
        self,
        component,
        init,
        extinction,
        name,
        indir,
        water_type,
        scheme,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
        validate_vars=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        init : polaris.Step
            The initial-condition step

        extinction : polaris.Step
            The step that creates the extinction-coefficient forcing file

        name : str
            The name of the step

        indir : str
            The directory the step is in

        water_type : int
            The Jerlov water type, between 1 (I) and 5 (III)

        scheme : {'jerlov', 'manizza'}
            The shortwave absorption scheme to configure

        ntasks : int, optional
            The number of tasks the step would ideally use

        min_tasks : int, optional
            The number of tasks the step requires

        openmp_threads : int, optional
            The number of OpenMP threads the step will use

        validate_vars : list, optional
            A list of variable names to compare with a baseline
        """
        if scheme not in ('jerlov', 'manizza'):
            raise ValueError(
                f'Unknown shortwave absorption scheme "{scheme}"; expected '
                f'"jerlov" or "manizza"'
            )
        super().__init__(
            component=component,
            init=init,
            name=name,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            validate_vars=validate_vars,
            task_name='shortwave_pen',
        )
        self.water_type = water_type
        self.scheme = scheme
        self.extinction_path = extinction.path

    def setup(self):
        """
        Add the extinction-coefficient forcing file, which only Omega reads
        """
        super().setup()
        if self.config.get('ocean', 'model') == 'omega':
            self.add_input_file(
                filename='shortwave_extinction_coeffs.nc',
                work_dir_target=(
                    f'{self.extinction_path}/shortwave_extinction_coeffs.nc'
                ),
            )

    def dynamic_model_config(self, at_setup):
        """
        Set the model config options that control shortwave absorption
        """
        super().dynamic_model_config(at_setup=at_setup)

        config = self.config
        model = config.get('ocean', 'model')
        section = config['single_column_shortwave_pen']

        if model == 'omega':
            if self.scheme == 'jerlov':
                options, _ = omega_jerlov_equivalent(self.water_type)
            else:
                options = {
                    'NearIrFraction': section.getfloat('near_ir_fraction'),
                    'NearIrCoeff': section.getfloat('near_ir_coeff'),
                    'RedFraction': section.getfloat('red_fraction'),
                    'BlueFraction': section.getfloat('blue_fraction'),
                }
            self.add_model_config_options(
                options=options, config_model='Omega'
            )
        elif model == 'mpas-ocean':
            if self.scheme != 'jerlov':
                raise ValueError(
                    'MPAS-Ocean only supports the two-band Jerlov scheme; '
                    f'the "{self.scheme}" scheme requires Omega.'
                )
            self.add_model_config_options(
                options={
                    'config_sw_absorption_type': 'jerlov',
                    'config_jerlov_water_type': self.water_type,
                    # deposits the flux below the 200 m cutoff in the bottom
                    # layer, as Omega does, so the column conserves energy
                    'config_enable_shortwave_energy_fixer': True,
                },
                config_model='mpas-ocean',
            )
        else:
            raise ValueError(f'Unknown ocean model {model}')

        # radiative forcing only: isolate the effect of the shortwave
        # absorption profile from convective/shear-driven mixing
        self.add_model_config_options(
            options={
                'config_use_cvmix_convection': False,
                'config_use_cvmix_shear': False,
            },
            config_model='ocean',
        )
