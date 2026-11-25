import dataclasses

from polaris.mpas.time import get_time_interval_string
from polaris.tasks.ocean.realistic_global.forward.forward import Forward
from polaris.tasks.ocean.realistic_global.forward.stage import ForwardStage

PACKAGE = 'polaris.tasks.ocean.realistic_global.ssh_adjustment'


class SshForward(Forward):
    """
    A single short step from rest of a realistic global ocean with ice-shelf
    cavities, whose depth-mean acceleration the SSH adjustment that follows
    cancels.

    The step is a ``realistic_global`` forward run, with the
    ``[realistic_global_forward]`` options and so the time integrator of the
    forward runs.  Its time step, run duration and output interval are all
    ``[ssh_adjustment] solve_dt_per_km`` times the mesh's minimum
    resolution, and its output holds the state at the start of the step as
    well as at its end.  The land-ice pressure is applied, but the land-ice
    fluxes are off.
    """

    def __init__(self, component, init_condition, subdir, name):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        init_condition : StepInitialCondition
            The source of the model input files, whose initial state is the
            initial condition or the previous SSH adjustment's output.

        subdir : str
            The subdirectory for the step.

        name : str
            The name of the step.
        """
        super().__init__(
            component=component,
            init_condition=init_condition,
            name=name,
            subdir=subdir,
        )

    def get_stage(self) -> ForwardStage:
        """
        The ``[realistic_global_forward]`` stage, shortened to a single step
        from rest with output before and after it and no land-ice fluxes.

        The stage is built from the config each time it is needed, rather
        than at setup, so that the options of a user's config take effect.

        Returns
        -------
        ForwardStage
            The run settings for this step.
        """
        config = self.config
        section = config['ssh_adjustment']
        method = section.get('method')
        if method != 'solve':
            raise ValueError(
                f'Realistic global SSH adjustment only supports '
                f'"method = solve", not {method!r}.'
            )
        seconds = section.getfloat('solve_dt_per_km') * (
            self.init_condition.min_res
        )
        dt = get_time_interval_string(seconds=seconds)
        stage = ForwardStage.from_config(config, name=self.name)
        return dataclasses.replace(
            stage,
            run_duration=dt,
            output_interval=dt,
            restart_interval=dt,
            stats_interval=dt,
            dt=dt,
            rk4_dt=dt,
            land_ice_flux_mode='off',
            output_density=True,
            do_restart=False,
            restart_in=None,
            restart_out=None,
        )

    def dynamic_model_config(self, at_setup):
        """
        Add the output that SSH adjustment reads to the forward run's model
        config.

        Parameters
        ----------
        at_setup : bool
            Whether this is being run during setup of the step, as opposed to
            at run time.
        """
        super().dynamic_model_config(at_setup=at_setup)
        self.add_yaml_file(PACKAGE, 'ssh_forward.yaml')
