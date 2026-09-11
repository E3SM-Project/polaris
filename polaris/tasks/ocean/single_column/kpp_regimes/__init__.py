from polaris import Task
from polaris.tasks.ocean.single_column.forward import Forward
from polaris.tasks.ocean.single_column.kpp_regimes.analysis import Analysis
from polaris.tasks.ocean.single_column.kpp_regimes.viz import KPPViz


class KPPRegimes(Task):
    """
    Single-column tests exercising KPP boundary-layer regimes not covered
    by the KPPMix unit tests or the generic ``vmix`` task: free convection,
    combined wind+convection forcing, a stable/restratifying case, the
    ``MatchTechnique`` comparison, Langmuir enhancement, and sea-ice OBL
    suppression.
    """

    def __init__(self, component, config, init, indir, name):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            The shared config for this regime (already includes the
            appropriate forcing/stratification cfg files)

        init : polaris.tasks.ocean.single_column.init.Init
            The shared init step for this regime

        indir : str
            The subdirectory the task belongs to

        name : str
            The regime name, one of the registered ``kpp_*`` task names
        """
        super().__init__(component=component, name=name, indir=indir)
        config_filename = 'kpp_regimes.cfg'
        self.set_shared_config(config, link=config_filename)
        self.config.add_from_package(
            'polaris.tasks.ocean.single_column.kpp_regimes', config_filename
        )
        self.config.add_from_package('polaris.ocean.eos', 'linear.cfg')
        self.add_step(init, symlink='init')

        validate_vars = [
            'temperature',
            'salinity',
            'layerThickness',
            'normalVelocity',
        ]

        common_kwargs = dict(
            component=component,
            init=init,
            indir=f'{indir}/{name}',
            ntasks=1,
            min_tasks=1,
            openmp_threads=1,
            validate_vars=validate_vars,
            task_name=name,
            task_package='polaris.tasks.ocean.single_column.kpp_regimes',
            enable_vadv=False,
            enable_hadv=False,
            # PVTendencyEnable (Omega) carries both relative vorticity and
            # Coriolis in one term; disabling horizontal advection must not
            # silently disable Coriolis for regimes whose physics depends on
            # it (e.g. wind-driven cases). Keep it governed by each task's
            # [coriolis] config instead, matching MPAS-Ocean, which has no
            # equivalent option and always applies Coriolis per its config.
            disable_coriolis=False,
            run_duration_steps=(
                36 if name == 'kpp_strong_convection_cooling' else None
            ),
            # kpp_combined includes evaporation (matching Van Roekel et al.
            # 2018 CEW), which carries an SST-dependent enthalpy flux the
            # generic energy-conservation checker can't represent, same as
            # kpp_non_local_flux_suppression
            check_properties=(
                ['mass conservation', 'salt conservation']
                if name in ('kpp_non_local_flux_suppression', 'kpp_combined')
                else None
            ),
            # Default to disabled for every task; kpp_langmuir overrides
            # these per-step below so MPAS-Ocean's on/off comparison
            # actually differs (previously both steps shared this value).
            mpas_langmuir_mixing_opt='NONE',
            mpas_use_theory_wave=False,
            minimum_obl_under_sea_ice=(
                30.0 if name == 'kpp_sea_ice' else None
            ),
        )

        if name == 'kpp_langmuir':
            langmuir_on_kwargs = dict(
                common_kwargs,
                use_langmuir_circulation=True,
                mpas_langmuir_mixing_opt='LWF16',
                mpas_use_theory_wave=True,
            )
            langmuir_off_kwargs = dict(
                common_kwargs,
                use_langmuir_circulation=False,
                mpas_langmuir_mixing_opt='NONE',
                mpas_use_theory_wave=False,
            )
            self.add_step(Forward(**langmuir_on_kwargs))
            self.add_step(Forward(**langmuir_off_kwargs))
            comparisons = {
                'langmuir': '../forward_no_vadv_no_hadv_langmuir',
                'no_langmuir': '../forward_no_vadv_no_hadv_no_langmuir',
            }
        else:
            self.add_step(Forward(**common_kwargs))
            self.add_step(
                Forward(**common_kwargs, match_technique='MatchBoth')
            )
            comparisons = {
                'standard': '../forward_no_vadv_no_hadv',
                'matchboth': '../forward_no_vadv_no_hadv_matchboth',
            }

        self.add_step(
            KPPViz(
                component=component,
                indir=f'{indir}/{name}',
                comparisons=comparisons,
                regime=name,
            )
        )

        self.add_step(
            Analysis(
                component=component,
                indir=f'{indir}/{name}',
                regime=name,
                comparisons=comparisons,
            )
        )
