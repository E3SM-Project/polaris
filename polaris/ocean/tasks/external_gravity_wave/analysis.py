import xarray as xr

from polaris.mpas import time_index_from_xtime
from polaris.ocean.convergence import ConvergenceAnalysis
from polaris.ocean.model import get_time_interval_string


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the cosine bell test case
    """
    def __init__(self, component, resolution, subdir, dependencies, dts):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            Mesh resolution

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        convergence_vars = [{'name': 'normalVelocity',
                             'title': 'normal velocity',
                             'zidx': 0},
                            {'name': 'layerThickness',
                             'title': 'layer thickness',
                             'zidx': 0}]
        resolutions = [resolution]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars, dts=dts)

    def get_output_field(self, mesh_name, field_name,
                         time, dt, zidx=None):
        """
        Get the model output field at the given time and z index

        Parameters
        ----------
        mesh_name : str
            The mesh name which is the prefix for the output file

        field_name : str
            The name of the variable of which we evaluate convergence

        time : float
            The time at which to evaluate the exact solution in seconds

        dt: float, optional
            Extracts the numerical solution that has been computed
            with dt

        zidx : int, optional
            The z-index for the vertical level to take the field from

        Returns
        -------
        field_mpas : xarray.DataArray
            model output field
        """
        time_str = get_time_interval_string(seconds=dt)
        ds_out = xr.open_dataset(f'dt{time_str}s_output.nc')

        tidx = time_index_from_xtime(ds_out.xtime.values, time)
        ds_out = ds_out.isel(Time=tidx)

        field_mpas = ds_out[field_name]
        if zidx is not None:
            field_mpas = field_mpas.isel(nVertLevels=zidx)
        return field_mpas
