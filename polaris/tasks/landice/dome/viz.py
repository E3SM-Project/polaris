import cmocean  # noqa: F401
from mpas_tools.io import open_dataset

from polaris import Step
from polaris.viz import plot_horiz_field

# MALI's dome tasks use a 365-day year
SECONDS_PER_YEAR = 365.0 * 24.0 * 3600.0


class Viz(Step):
    """
    A step for plotting the ice thickness and surface speed at the end of a
    dome run
    """

    def __init__(self, component, init, indir, forward_subdir='forward'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        init : polaris.tasks.landice.dome.init.Init
            The shared step that makes the mesh and initial condition

        indir : str
            the directory the step is in, to which ``name`` will be appended

        forward_subdir : str, optional
            The subdirectory of the step with the output to plot
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/landice_grid.nc'
        )
        self.add_input_file(
            filename='output.nc', target=f'../{forward_subdir}/output.nc'
        )
        for filename in ['thickness.png', 'surface_speed.png']:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step of the task
        """
        section = self.config['dome_viz']
        ds_mesh = open_dataset('mesh.nc')
        ds = open_dataset('output.nc')

        t_index = ds.sizes['Time'] - 1
        years = float(ds.daysSinceStart.isel(Time=t_index).values) / 365.0

        plot_horiz_field(
            ds_mesh=ds_mesh,
            field=ds.thickness,
            out_file_name='thickness.png',
            t_index=t_index,
            title=f'Ice thickness after {years:g} years',
            cmap=section.get('thickness_cmap'),
            cmap_title='m',
        )

        speed = SECONDS_PER_YEAR * ds.surfaceSpeed
        plot_horiz_field(
            ds_mesh=ds_mesh,
            field=speed,
            out_file_name='surface_speed.png',
            t_index=t_index,
            title=f'Surface speed after {years:g} years',
            cmap=section.get('speed_cmap'),
            cmap_title='m yr$^{-1}$',
        )
