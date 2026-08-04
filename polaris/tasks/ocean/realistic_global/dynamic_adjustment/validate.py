from polaris import Step
from polaris.tasks.ocean.realistic_global.dynamic_adjustment.schedule import (
    SECTION,
)


class Validate(Step):
    """
    A step that checks a completed dynamic-adjustment sequence for obvious
    failures: a per-stage maximum-temperature threshold (numerical blow-up) and
    a "settling" heuristic that the maximum cell kinetic energy is not
    increasing over the last several stages.

    Both checks read each stage's ``output.nc``, which carries the tracers and
    ``kineticEnergyCell`` for either ocean model, through
    ``open_model_dataset`` so that Omega's variable names are mapped to the
    MPAS-Ocean ones the checks are written in.  The baseline comparison of the
    final stage is handled separately by that forward step's ``validate_vars``.

    One caveat the threshold cannot express: Omega's temperature is
    conservative temperature where MPAS-Ocean's is potential temperature, so
    ``temperature_max`` is not literally the same quantity in the two models.
    Against a blow-up threshold the difference is immaterial.

    Attributes
    ----------
    stage_names : list of str
        The stage subdirectory names whose ``output.nc`` files are checked, in
        schedule order.
    """

    def __init__(self, component, stage_names, indir):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        stage_names : list of str
            The stage subdirectory names, in schedule order.

        indir : str
            The directory the step is in, to which ``validate`` is appended.
        """
        super().__init__(component=component, name='validate', indir=indir)
        self.stage_names = list(stage_names)
        for stage_name in self.stage_names:
            self.add_input_file(
                filename=f'output_{stage_name}.nc',
                target=f'../{stage_name}/output.nc',
            )

    def run(self):
        """
        Check the temperature threshold and kinetic-energy flattening.
        """
        super().run()
        config = self.config
        logger = self.logger

        temperature_max = config.getfloat(SECTION, 'temperature_max')
        ke_num = config.getint(SECTION, 'ke_check_num_stages')
        ke_tol = config.getfloat(SECTION, 'ke_check_rel_tolerance')

        max_ke = []
        for stage_name in self.stage_names:
            ds = self.component.open_model_dataset(
                f'output_{stage_name}.nc', config
            )
            with ds:
                _check_temperature_max(ds, temperature_max, stage_name, logger)
                max_ke.append(_final_max_ke(ds))

        _check_ke_flattening(self.stage_names, max_ke, ke_num, ke_tol, logger)


def _check_temperature_max(ds, temperature_max, stage_name, logger):
    """Raise if the final-time maximum temperature exceeds the threshold."""
    if 'temperature' not in ds:
        return
    value = float(ds['temperature'].isel(Time=-1).max())
    if value > temperature_max:
        raise ValueError(
            f'Stage {stage_name!r}: maximum temperature {value:.2f} exceeds '
            f'the allowed {temperature_max:.2f}.'
        )
    logger.info(
        f'Stage {stage_name!r}: max temperature {value:.2f} <= '
        f'{temperature_max:.2f}.'
    )


def _final_max_ke(ds):
    """The maximum cell kinetic energy at the final output time."""
    return float(ds['kineticEnergyCell'].isel(Time=-1).max())


def _check_ke_flattening(stage_names, max_ke, ke_num, ke_tol, logger):
    """
    Raise if the maximum cell kinetic energy increases by more than ``ke_tol``
    (a fraction) between any two of the last ``ke_num`` stages.  Skipped when
    there are fewer than ``ke_num`` stages (e.g. the coarse default schedule),
    since a single damped-to-undamped transition is not a meaningful trend.
    """
    if len(stage_names) < ke_num:
        logger.info(
            f'Fewer than {ke_num} stages; skipping the kinetic-energy '
            f'flattening check.'
        )
        return
    tail_names = stage_names[-ke_num:]
    tail_ke = max_ke[-ke_num:]
    for index in range(1, len(tail_ke)):
        previous = tail_ke[index - 1]
        current = tail_ke[index]
        if previous > 0.0 and current > previous * (1.0 + ke_tol):
            raise ValueError(
                f'Stage {tail_names[index]!r}: maximum cell kinetic energy '
                f'{current:.3e} increased by more than {ke_tol:.1%} over the '
                f'previous stage ({previous:.3e}); the adjustment is not '
                f'settling.'
            )
    logger.info(
        f'Maximum cell kinetic energy is flattening over the last {ke_num} '
        f'stages ({tail_ke[0]:.3e} -> {tail_ke[-1]:.3e}).'
    )
