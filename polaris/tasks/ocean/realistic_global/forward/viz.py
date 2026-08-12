import cmocean  # noqa: F401

from polaris.ocean.model import OceanIOStep
from polaris.ocean.model.time import get_days_since_start
from polaris.viz import plot_global_mpas_field

_WIND_STRESS_VARS = ['windStressZonal', 'windStressMeridional']


class Viz(OceanIOStep):
    """
    A step for plotting global maps of a forward run's state, at the start and
    end of the run, along with the wind stress that forced it.

    Attributes
    ----------
    forward : polaris.Step
        The forward step whose output is plotted.

    variables_to_plot : list of str
        The state variables to plot, in MPAS-Ocean naming.
    """

    def __init__(
        self,
        component,
        indir,
        forward,
        name='viz',
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        indir : str
            The directory the step is in, to which ``name`` is appended.

        forward : polaris.Step
            The forward step whose output is plotted.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, indir=indir)
        self.forward = forward
        if component.state_vars is None:
            component._read_variables_yaml()
        self.variables_to_plot = [
            'kineticEnergyCell' if var == 'normalVelocity' else var
            for var in component.state_vars
        ]

    def setup(self):
        """
        Link the forward step's inputs and output.

        The staged filenames are config options rather than fixed names, and
        they differ between the models, so the entries are added here rather
        than in ``__init__()``, where the model is not yet known.  The wind
        stress is read from whichever file the forward run's initial condition
        says holds the forcing: a file of its own when the init workflow
        produced one, or the initial condition itself when the stress travels
        inside it.
        """
        forward = self.forward
        path = forward.path
        mesh_filename = self.get_horiz_mesh_filename()
        init_filename = self.get_init_filename()
        self.add_horiz_mesh_input_file(
            work_dir_target=f'{path}/{mesh_filename}'
        )
        self.add_init_input_file(work_dir_target=f'{path}/{init_filename}')
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{path}/output.nc'
        )

        self.forcing_filename = forward.init_condition.get_forcing_filename(
            forward
        )
        if self.forcing_filename != init_filename:
            self.add_input_file(
                filename=self.forcing_filename,
                work_dir_target=f'{path}/{self.forcing_filename}',
            )

    def run(self):
        """
        Plot the wind stress and the state at the start and end of the run.
        """
        config = self.config
        variables_to_plot = self.variables_to_plot
        mesh_filename = self.get_horiz_mesh_filename()
        init_filename = self.get_init_filename()

        ds_init = self.open_model_dataset(
            init_filename,
            config,
            decode_times=True,
            mesh_filename=mesh_filename,
        )
        ds_init = ds_init.isel(Time=0, nVertLevels=0)
        ds_out = self.open_model_dataset(
            'output.nc',
            config,
            decode_times=True,
            mesh_filename=mesh_filename,
        )

        time = get_days_since_start(ds_out)
        ds_final = ds_out.isel(Time=-1, nVertLevels=0)
        t_days = int(round(time[-1]))

        ds_forcing = self.open_model_dataset(
            self.forcing_filename,
            config,
            decode_times=True,
            mesh_filename=mesh_filename,
        )
        if 'Time' in ds_forcing.dims:
            # MPAS-Ocean gives the forcing a Time dimension and Omega does not
            ds_forcing = ds_forcing.isel(Time=0)

        for var in _WIND_STRESS_VARS:
            if var not in ds_forcing:
                self.logger.info(f'{var} not found in {self.forcing_filename}')
                continue
            plot_global_mpas_field(
                mesh_filename=mesh_filename,
                da=ds_forcing[var],
                out_filename=f'{var}.png',
                config=config,
                colormap_section='realistic_global_viz_windStress',
                title=var,
                plot_land=True,
                central_longitude=180.0,
            )

        for var in variables_to_plot:
            colormap_section = f'realistic_global_viz_{var}'
            if var not in ds_init.keys():
                self.logger.info(f'{var} not found in {init_filename}')
            else:
                plot_global_mpas_field(
                    mesh_filename=mesh_filename,
                    da=ds_init[var],
                    out_filename=f'{var}_init.png',
                    config=config,
                    colormap_section=colormap_section,
                    title=f'{var} at init',
                    plot_land=True,
                    central_longitude=180.0,
                )
            if var not in ds_final.keys():
                self.logger.info(f'{var} not found in output.nc')
            else:
                plot_global_mpas_field(
                    mesh_filename=mesh_filename,
                    da=ds_final[var],
                    out_filename=f'{var}_{t_days}days.png',
                    config=config,
                    colormap_section=colormap_section,
                    title=f'{var} after {t_days} days',
                    plot_land=True,
                    central_longitude=180.0,
                )
