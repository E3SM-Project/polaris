import xarray as xr

from polaris.ocean.model import OceanIOStep


class Extinction(OceanIOStep):
    """
    A helper step that creates the ``shortwave_extinction_coeffs.nc`` forcing
    file consumed by Omega's ``ShortwaveExtinctionIn`` input stream.  The
    file contains uniform, per-cell red- and blue-band extinction
    coefficients (``ExtinctionCoeffRedCell`` and ``ExtinctionCoeffBlueCell``)
    used by the penetrating-shortwave-radiation tendency term.
    """

    def __init__(self, component, subdir, init, name='extinction'):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step will go into

        init : polaris.Step
            The initial-condition step providing the mesh
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_output_file(filename='shortwave_extinction_coeffs.nc')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        section = config['single_column_shortwave_pen']
        extinction_coeff_red = section.getfloat('extinction_coeff_red')
        extinction_coeff_blue = section.getfloat('extinction_coeff_blue')

        ds_mesh = self.open_model_dataset('mesh.nc', config=config)

        ds = xr.Dataset()
        ds['ExtinctionCoeffRedCell'] = extinction_coeff_red * xr.ones_like(
            ds_mesh.xCell
        )
        ds['ExtinctionCoeffBlueCell'] = extinction_coeff_blue * xr.ones_like(
            ds_mesh.xCell
        )

        self.write_model_dataset(ds, 'shortwave_extinction_coeffs.nc', config)
