import os

from polaris.tasks.ocean.isomip_plus.forward import Forward

#: The interval between the monthly records of MALI's data-mode geometry
MONTHLY_INTERVAL = '0000-01-00_00:00:00'


class MisomipForward(Forward):
    """
    A step for running MPAS-Ocean alone from the initial condition E3SM
    reads, with the same physics, wetting and drying, outflow and land-ice
    geometry

    Attributes
    ----------
    data_mode : bool
        Whether the land-ice geometry varies in time, as MALI's data mode
        replays it in monthly records
    """

    def __init__(
        self, component, subdir, resolution, init, ssh_adjust, data_mode
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step, which must end in ``forward``

        resolution : float
            The horizontal resolution (km) of the mesh

        init : polaris.Step
            The step that produced the mesh, graph file and forcing

        ssh_adjust : polaris.Step
            The last SSH-adjustment step, which produced the initial
            condition

        data_mode : bool
            Whether the land-ice geometry varies in time
        """
        indir, name = os.path.split(subdir)
        if name != 'forward':
            raise ValueError(f'The subdirectory {subdir} must end in forward')
        super().__init__(
            component=component,
            indir=indir,
            resolution=resolution,
            init=init,
            ssh_adjust=ssh_adjust,
            thin_film=True,
        )
        self.data_mode = data_mode

    def get_forcing_interval(self, at_setup):
        """
        Get the interval between the land-ice forcing records: a month in
        data mode

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step

        Returns
        -------
        interval : str
            The interval between records
        """
        return MONTHLY_INTERVAL if self.data_mode else 'none'

    def dynamic_model_config(self, at_setup):
        """
        Add the options of the ISOMIP+ forward run with a thin film, and turn
        off the time-varying land-ice forcing if the geometry is fixed

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)
        if not self.data_mode:
            self.add_yaml_file(
                'polaris.tasks.ocean.misomip', 'static_land_ice.yaml'
            )
