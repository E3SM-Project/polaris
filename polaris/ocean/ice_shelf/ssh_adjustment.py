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
    def __init__(self, component, init, forward, indir=None,
                 name='ssh_adjust'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        init : polaris.Step
            the step that produced the initial condition

        forward: polaris.Step
            the step that produced the state which will be adjusted

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        name : str, optional
            the name of this step
        """
        super().__init__(component=component, name=name,
                         indir=f'{indir}/ssh_adjustment')

        self.add_input_file(filename='final.nc',
                            work_dir_target=f'{forward.path}/output.nc')
        self.add_input_file(filename='init.nc',
                            work_dir_target=f'{forward.path}/init.nc')
        self.add_input_file(filename='mesh.nc',
                            work_dir_target=f'{init.path}/culled_mesh.nc')
        self.add_output_file(filename='output.nc')

    # no setup() is needed

    def run(self):
        """
        Adjust the sea surface height or land-ice pressure to be dynamically
        consistent with one another.
        """
        logger = self.logger
        config = self.config
        adjust_variable = config.get('ssh_adjustment', 'adjust_variable')
        mask_variable = config.get('ssh_adjustment', 'mask_variable')
        mesh_filename = 'mesh.nc'
        init_filename = 'init.nc'
        final_filename = 'final.nc'
        out_filename = 'output.nc'
        ds_mesh = xr.open_dataset(mesh_filename)
        ds_init = xr.open_dataset(init_filename)
        ds_final = xr.open_dataset(final_filename)
        ds_out = ds_init.copy()

        if adjust_variable not in ['ssh', 'landIcePressure']:
            raise ValueError(f"Unknown variable to modify: {adjust_variable}")
        if mask_variable not in ds_init.keys():
            raise ValueError(f"Mask variable {mask_variable} is not contained "
                             f"in {init_filename}")

        logger.info("   * Updating SSH or land-ice pressure")

        # keep the data set with Time for output
        # and generate these time slices
        ds_init = ds_init.isel(Time=0)
        ds_final = ds_final.isel(Time=-1)

        on_a_sphere = ds_out.attrs['on_a_sphere'].lower() == 'yes'

        if 'minLevelCell' in ds_final:
            minLevelCell = ds_final.minLevelCell - 1
        else:
            minLevelCell = ds_mesh.minLevelCell - 1

        init_ssh = ds_init.ssh
        final_ssh = ds_final.ssh
        top_density = ds_final.density.isel(nVertLevels=minLevelCell)

        mask = ds_init[mask_variable]
        delta_ssh = mask * (final_ssh - init_ssh)

        # then, modify the SSH or land-ice pressure
        if adjust_variable == 'ssh':
            final_ssh = final_ssh.expand_dims(dim='Time', axis=0)
            ds_out['ssh'] = final_ssh
            # also update the landIceDraft variable, which will be used to
            # compensate for the SSH due to land-ice pressure when
            # computing sea-surface tilt
            ds_out['landIceDraft'] = final_ssh
            # we also need to stretch layerThickness to be compatible with
            # the new SSH
            stretch = ((final_ssh + ds_mesh.bottomDepth) /
                       (init_ssh + ds_mesh.bottomDepth))
            ds_out['layerThickness'] = ds_out.layerThickness * stretch
            land_ice_pressure = ds_out.landIcePressure.values
        else:
            # Moving the SSH up or down by deltaSSH would change the
            # land-ice pressure by density(SSH)*g*deltaSSH. If deltaSSH is
            # positive (moving up), it means the land-ice pressure is too
            # small and if deltaSSH is negative (moving down), it means
            # land-ice pressure is too large, the sign of the second term
            # makes sense.
            gravity = constants['SHR_CONST_G']
            delta_land_ice_pressure = top_density * gravity * delta_ssh

            land_ice_pressure = np.maximum(
                0.0, ds_final.landIcePressure + delta_land_ice_pressure)

            ds_out['landIcePressure'] = \
                land_ice_pressure.expand_dims(dim='Time', axis=0)

            final_ssh = init_ssh

        write_netcdf(ds_out, out_filename)

        # Write the largest change in SSH and its lon/lat to a file
        with open('maxDeltaSSH.log', 'w') as log_file:

            mask = land_ice_pressure > 0.
            i_cell = np.abs(delta_ssh.where(mask)).argmax().values

            ds_cell = ds_final.isel(nCells=i_cell)
            ds_mesh = ds_mesh.isel(nCells=i_cell)
            delta_ssh_max = delta_ssh.isel(nCells=i_cell).values

            if on_a_sphere:
                coords = (f'lon/lat: '
                          f'{np.rad2deg(ds_cell.lonCell.values):f} '
                          f'{np.rad2deg(ds_cell.latCell.values):f}')
            else:
                coords = (f'x/y: {1e-3 * ds_mesh.xCell.values:f} '
                          f'{1e-3 * ds_mesh.yCell.values:f}')
            string = (f'deltaSSHMax: '
                      f'{delta_ssh_max:g}, {coords}')
            logger.info(f'     {string}')
            log_file.write(f'{string}\n')
            string = (f'ssh: {final_ssh.isel(nCells=i_cell).values:g}, '
                      f'land_ice_pressure: '
                      f'{land_ice_pressure.isel(nCells=i_cell).values:g}')
            logger.info(f'     {string}')
            log_file.write(f'{string}\n')

        logger.info("   - Complete\n")
