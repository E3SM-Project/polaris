from matplotlib.figure import Figure
from mpas_tools.io import open_dataset

from polaris import Step
from polaris.viz import mplstyle_context


class Viz(Step):
    """
    A step for plotting the results of a single column test
    """

    def __init__(self, component, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which the name of the step will
            be appended
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.add_input_file(
            filename='output.2000.nc',
            target='../forward/output/output.2000.nc',
        )

    def run(self):
        """
        Run this step of the test case
        """
        ds = open_dataset(self.work_path('output.2000.nc'), decode_times=False)
        daysSinceStartOfSim = ds.daysSinceStartOfSim.values
        snowVolumeCell = ds.snowVolumeCell.values
        iceVolumeCell = ds.iceVolumeCell.values
        surfaceTemperatureCell = ds.surfaceTemperatureCell.values

        with mplstyle_context():
            fig = Figure(figsize=(8, 8))
            axis = fig.add_subplot(111)

            axis.plot(
                daysSinceStartOfSim,
                surfaceTemperatureCell,
                color='green',
                label='surfaceTemperature',
            )
            axis.set_ylabel('Temperature (C)')
            axis.set_xlabel('Days')
            axis.set_xlim(0, daysSinceStartOfSim[-1])
            axis.set_ylim(None, 0)
            axis.set_title('MPAS_Seaice single cell')

            axis.legend()

            axis2 = axis.twinx()

            axis2.plot(
                daysSinceStartOfSim,
                iceVolumeCell,
                color='red',
                label='iceVolume',
            )
            axis2.plot(
                daysSinceStartOfSim,
                snowVolumeCell,
                color='blue',
                label='snowVolume',
            )
            axis2.set_ylabel('Thickness (m)')
            axis2.set_ylim(0, None)

            axis2.legend()
            fig.tight_layout()
            fig.savefig(self.work_path('single_cell.pdf'))
            fig.savefig(self.work_path('single_cell.png'), dpi=300)
