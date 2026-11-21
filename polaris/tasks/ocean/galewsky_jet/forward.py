from polaris.ocean.convergence.spherical import SphericalConvergenceForward
from polaris.ocean.model import get_time_interval_string


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs of the Galewsky jet

    Attributes
    ----------
    task_name : str
        The task (``steady_state``, ``adjustment`` or ``unstable``) whose
        config section gives the run duration, output interval and viscosity
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        mesh,
        init,
        refinement_factor,
        task_name,
    ):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        refinement_factor : float
            The factor by which to scale space and time

        task_name : str
            The task (``steady_state``, ``adjustment`` or ``unstable``) whose
            config section gives the run duration, output interval and
            viscosity
        """
        self.task_name = task_name
        package = 'polaris.tasks.ocean.galewsky_jet'
        validate_vars = ['layerThickness', 'normalVelocity']
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            mesh=mesh,
            init=init,
            package=package,
            yaml_filename='forward.yaml',
            output_filename='output.nc',
            validate_vars=validate_vars,
            update_eos=True,
            graph_target=f'{mesh.path}/graph.info',
            refinement_factor=refinement_factor,
            refinement='both',
        )

        # viscosity is a constant, not scaled with cell width.  Omega's
        # scaling is already off by default in OceanModelStep.
        self.add_model_config_options(
            options={'config_hmix_scaleWithMesh': False},
            config_model='mpas-ocean',
        )

    def dynamic_model_config(self, at_setup):
        """
        Set the run duration, output interval and viscosity from this task's
        config section, then the time step and other options as in other
        spherical convergence tests

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        section = self.config[f'galewsky_jet_{self.task_name}']
        s_per_hour = 3600.0
        run_duration = section.getfloat('run_duration') * s_per_hour
        output_interval = section.getfloat('output_interval') * s_per_hour
        viscosity = section.getfloat('viscosity')

        self.replacements = dict(
            run_duration=get_time_interval_string(seconds=run_duration),
            output_interval=get_time_interval_string(seconds=output_interval),
            output_freq=f'{int(output_interval)}',
            use_mom_del2=f'{viscosity > 0.0}',
            mom_del2=f'{viscosity}',
        )
        super().dynamic_model_config(at_setup=at_setup)
