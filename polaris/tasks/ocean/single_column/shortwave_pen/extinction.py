import xarray as xr

from polaris.ocean.model import OceanIOStep


class Extinction(OceanIOStep):
    """
    A helper step that creates the ``shortwave_extinction_coeffs.nc`` forcing
    file consumed by Omega's ``ShortwaveExtinctionIn`` input stream.  The
    file contains uniform, per-cell red- and blue-band extinction
    coefficients (``ExtinctionCoeffRedCell`` and ``ExtinctionCoeffBlueCell``)
    used by the penetrating-shortwave-radiation tendency term.

    Attributes
    ----------
    extinction_coeff_red : float
        The red-band extinction coefficient in 1/m

    extinction_coeff_blue : float
        The blue-band extinction coefficient in 1/m
    """

    def __init__(
        self,
        component,
        subdir,
        init,
        extinction_coeff_red,
        extinction_coeff_blue,
        name='extinction',
    ):
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

        extinction_coeff_red : float
            The red-band extinction coefficient in 1/m

        extinction_coeff_blue : float
            The blue-band extinction coefficient in 1/m

        name : str, optional
            The name of the step
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.extinction_coeff_red = extinction_coeff_red
        self.extinction_coeff_blue = extinction_coeff_blue
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_output_file(filename='shortwave_extinction_coeffs.nc')

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config

        ds_mesh = self.open_model_dataset('mesh.nc', config=config)

        ds = xr.Dataset()
        ds['ExtinctionCoeffRedCell'] = (
            self.extinction_coeff_red * xr.ones_like(ds_mesh.xCell)
        )
        ds['ExtinctionCoeffBlueCell'] = (
            self.extinction_coeff_blue * xr.ones_like(ds_mesh.xCell)
        )

        self.write_model_dataset(ds, 'shortwave_extinction_coeffs.nc', config)
