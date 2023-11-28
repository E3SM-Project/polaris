import numpy as np
import xarray as xr
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf

from polaris import Step


class SshAdjustment(Step):
    """
    A step for iteratively adjusting the pressure from the weight of the ice
    shelf to match the sea-surface height as part of ice-shelf 2D test cases
    """
    def __init__(self, component, resolution, forward, indir=None,
                 name='ssh_adjust', tidal_forcing=False):
        """
        Create the step

        Parameters
        ----------
        resolution : float
            The resolution of the test case in m

        coord_type: str
            The coordinate type (e.g., 'z-star', 'single_layer', etc.)

        iteration : int, optional
            the iteration number

        tidal_forcing : bool, optional
        """
        self.resolution = resolution

        super().__init__(component=component, name=name, indir=indir)

        self.add_input_file(filename='init.nc',
                            target=f'{forward.path}/output.nc')
        self.add_input_file(filename='init_ssh.nc',
                            target=f'{forward.path}/output_ssh.nc')
        self.add_output_file(filename='output.nc')

    # no setup() is needed

    def run(self):
        """
        Adjust the sea surface height or land-ice pressure to be dynamically
        consistent with one another.

        """
        logger = self.logger
        # TODO get from config
        # config = self.config
        adjust_variable = 'landIcePressure'
        in_filename = self.inputs[0]
        ssh_filename = self.inputs[1]
        out_filename = self.outputs[0]

        if adjust_variable not in ['ssh', 'landIcePressure']:
            raise ValueError(f"Unknown variable to modify: {adjust_variable}")

        logger.info("   * Updating SSH or land-ice pressure")

        with xr.open_dataset(in_filename) as ds:

            # keep the data set with Time for output
            ds_out = ds

            ds = ds.isel(Time=0)

            on_a_sphere = ds.attrs['on_a_sphere'].lower() == 'yes'

            initSSH = ds.ssh
            if 'minLevelCell' in ds:
                minLevelCell = ds.minLevelCell - 1
            else:
                minLevelCell = xr.zeros_like(ds.maxLevelCell)

            with xr.open_dataset(ssh_filename) as ds_ssh:
                # get the last time entry
                ds_ssh = ds_ssh.isel(Time=ds_ssh.sizes['Time'] - 1)
                finalSSH = ds_ssh.ssh
                topDensity = ds_ssh.density.isel(nVertLevels=minLevelCell)

            mask = np.logical_and(ds.maxLevelCell > 0,
                                  ds.modifyLandIcePressureMask == 1)

            deltaSSH = mask * (finalSSH - initSSH)

            # then, modify the SSH or land-ice pressure
            if adjust_variable == 'ssh':
                ssh = finalSSH.expand_dims(dim='Time', axis=0)
                ds_out['ssh'] = ssh
                # also update the landIceDraft variable, which will be used to
                # compensate for the SSH due to land-ice pressure when
                # computing sea-surface tilt
                ds_out['landIceDraft'] = ssh
                # we also need to stretch layerThickness to be compatible with
                # the new SSH
                stretch = ((finalSSH + ds.bottomDepth) /
                           (initSSH + ds.bottomDepth))
                ds_out['layerThickness'] = ds_out.layerThickness * stretch
                landIcePressure = ds.landIcePressure.values
            else:
                # Moving the SSH up or down by deltaSSH would change the
                # land-ice pressure by density(SSH)*g*deltaSSH. If deltaSSH is
                # positive (moving up), it means the land-ice pressure is too
                # small and if deltaSSH is negative (moving down), it means
                # land-ice pressure is too large, the sign of the second term
                # makes sense.
                gravity = constants['SHR_CONST_G']
                deltaLandIcePressure = topDensity * gravity * deltaSSH

                landIcePressure = np.maximum(
                    0.0, ds.landIcePressure + deltaLandIcePressure)

                ds_out['landIcePressure'] = \
                    landIcePressure.expand_dims(dim='Time', axis=0)

                finalSSH = initSSH

            write_netcdf(ds_out, out_filename)

            # Write the largest change in SSH and its lon/lat to a file
            with open('maxDeltaSSH.log', 'w') as log_file:

                mask = landIcePressure > 0.
                i_cell = np.abs(deltaSSH.where(mask)).argmax().values

                ds_cell = ds.isel(nCells=i_cell)
                deltaSSHMax = deltaSSH.isel(nCells=i_cell).values

                if on_a_sphere:
                    coords = (f'lon/lat: '
                              f'{np.rad2deg(ds_cell.lonCell.values):f} '
                              f'{np.rad2deg(ds_cell.latCell.values):f}')
                else:
                    coords = (f'x/y: {1e-3 * ds_cell.xCell.values:f} '
                              f'{1e-3 * ds_cell.yCell.values:f}')
                string = (f'deltaSSHMax: '
                          f'{deltaSSHMax:g}, {coords}')
                logger.info(f'     {string}')
                log_file.write(f'{string}\n')
                string = (f'ssh: {finalSSH.isel(nCells=i_cell).values:g}, '
                          f'landIcePressure: '
                          f'{landIcePressure.isel(nCells=i_cell).values:g}')
                logger.info(f'     {string}')
                log_file.write(f'{string}\n')

        logger.info("   - Complete\n")
