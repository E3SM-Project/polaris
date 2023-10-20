import importlib.resources as imp_res

import matplotlib.pyplot as plt
import xarray as xr

from polaris import Step


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
            target='../forward/output/output.2000.nc')

    def run(self):
        """
        Run this step of the test case
        """
        style_filename = str(
            imp_res.files('polaris.viz') / 'polaris.mplstyle')
        plt.style.use(style_filename)
        ds = xr.open_dataset('output.2000.nc', decode_times=False)
        daysSinceStartOfSim = ds.daysSinceStartOfSim.values
        snowVolumeCell = ds.snowVolumeCell.values
        iceVolumeCell = ds.iceVolumeCell.values
        surfaceTemperatureCell = ds.surfaceTemperatureCell.values

        fig, axis = plt.subplots(figsize=(8, 8))

        axis.plot(daysSinceStartOfSim, surfaceTemperatureCell,
                  color='green', label='surfaceTemperature')
        axis.set_ylabel('Temperature (C)')
        axis.set_xlabel('Days')
        axis.set_xlim(0, daysSinceStartOfSim[-1])
        axis.set_ylim(None, 0)
        axis.set_title('MPAS_Seaice single cell')

        plt.legend()

        axis2 = axis.twinx()

        axis2.plot(daysSinceStartOfSim, iceVolumeCell,
                   color='red', label='iceVolume')
        axis2.plot(daysSinceStartOfSim, snowVolumeCell,
                   color='blue', label='snowVolume')
        axis2.set_ylabel('Thickness (m)')
        axis2.set_ylim(0, None)

        plt.legend()
        plt.tight_layout()
        plt.savefig('single_cell.pdf')
        plt.savefig('single_cell.png', dpi=300)
        plt.close()
