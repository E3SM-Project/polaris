import cmocean  # noqa: F401

from polaris.ocean.model import OceanIOStep
from polaris.ocean.model.time import get_days_since_start
from polaris.viz import plot_global_mpas_field


class Viz(OceanIOStep):
    """
    A step for plotting fields from the realistic global output

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """

    def __init__(
        self,
        component,
        indir,
        forward,
        name='viz',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory in the test case's work directory for the step

        base_mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step

        forward : polaris.Step
            The init step
        """
        super().__init__(component=component, name=name, indir=indir)
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{forward.path}/mesh.nc',
        )
        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{forward.path}/init.nc',
        )
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{forward.path}/output.nc'
        )
        self.forward = forward
        if component.state_vars is None:
            component._read_variables_yaml()
        self.variables_to_plot = [
            'kineticEnergyCell' if var == 'normalVelocity' else var
            for var in component.state_vars
        ]

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        variables_to_plot = self.variables_to_plot

        ds_init = self.open_model_dataset(
            'init.nc',
            config,
            decode_times=False,
            mesh_filename='mesh.nc',
        )
        ds_init = ds_init.isel(Time=0, nVertLevels=0)

        ds_out = self.open_model_dataset(
            'output.nc',
            config,
            decode_times=False,
            mesh_filename='mesh.nc',
        )

        time = get_days_since_start(ds_out)
        ds_final = ds_out.isel(Time=-1, nVertLevels=0)
        t_days = int(round(time[-1]))

        for var in variables_to_plot:
            print(f'Plotting {var}')
            colormap_section = f'realistic_global_viz_{var}'
            if var not in ds_init.keys():
                self.logger.info(f'{var} not found in init.nc')
            else:
                plot_global_mpas_field(
                    mesh_filename='mesh.nc',
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
                    mesh_filename='mesh.nc',
                    da=ds_final[var],
                    out_filename=f'{var}_{t_days}days.png',
                    config=config,
                    colormap_section=colormap_section,
                    title=f'{var} after {t_days} days',
                    plot_land=True,
                    central_longitude=180.0,
                )
