import os
import time

import numpy as np

from polaris.ocean.convergence import get_timestep_for_task
from polaris.ocean.model import get_time_interval_string
from polaris.ocean.tasks.cosine_bell.forward import Forward


class RestartStep(Forward):
    """
    A forward model step in the restart test case
    """

    def dynamic_model_config(self, at_setup):
        """
        Add model config options, namelist, streams and yaml files using config
        options or template replacements that need to be set both during step
        setup and at runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)

        do_restart = self.do_restart

        dt, _ = get_timestep_for_task(
            self.config, self.refinement_factor, refinement=self.refinement
        )
        dt = np.ceil(dt)

        if not do_restart:
            # 2 time steps without a restart
            start_time = 0.0
            run_duration = 2.0 * dt
            output_interval = 2.0 * dt
        else:
            # 1 time step from the restart at 1 time step
            start_time = dt
            run_duration = dt
            output_interval = dt

        # to keep the time formatting from getting too complicated, we'll
        # assume 2 time steps is never more than a day
        start_time_str = time.strftime(
            '0001-01-01_%H:%M:%S', time.gmtime(start_time)
        )

        run_duration_str = get_time_interval_string(seconds=run_duration)

        output_interval_str = get_time_interval_string(seconds=output_interval)

        # For Omega, we want the output interval as a number of seconds
        output_freq = int(output_interval)

        if do_restart:
            restart_time_str = start_time_str
            init_freq_units = 'never'
        else:
            # Effectively never
            restart_time_str = '99999-12-31_00:00:00'
            init_freq_units = 'OnStartup'

        package = 'polaris.ocean.tasks.cosine_bell.restart'
        replacements = dict(
            do_restart=do_restart,
            not_restart=not do_restart,
            start_time=start_time_str,
            run_duration=run_duration_str,
            output_interval=output_interval_str,
            restart_time=restart_time_str,
            init_freq_units=init_freq_units,
            output_freq=f'{output_freq}',
        )

        self.add_yaml_file(
            package=package,
            yaml='forward.yaml',
            template_replacements=replacements,
        )

        restart_dir = os.path.abspath(
            os.path.join(self.work_dir, '..', 'restarts')
        )
        os.makedirs(restart_dir, exist_ok=True)
