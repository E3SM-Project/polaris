import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.landice.mismip_plus.geometry import (
    ACCUMULATION_RATE,
    CALVING_X,
    FRICTION_COEFFICIENT,
    FRICTION_EXPONENT,
    ICE_DENSITY,
    MALI_SECONDS_PER_YEAR,
    SECONDS_PER_YEAR,
    bed_topography,
)

# the thickness in m of the slab the spin-up starts from by default
SLAB_THICKNESS = 100.0


class Init(Step):
    """
    A step for adding the MISMIP+ initial condition and forcing to the MALI
    mesh
    """

    def __init__(self, component, mesh_step, subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        mesh_step : polaris.tasks.mesh.planar.mismip_plus.MismipPlusMesh
            The shared step that makes the mesh

        subdir : str
            The subdirectory for the step
        """
        super().__init__(component=component, name='init', subdir=subdir)
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{mesh_step.path}/mali_mesh.nc',
        )
        self.add_output_file(filename='landice_grid.nc')

    def run(self):
        """
        Run this step
        """
        ds = xr.open_dataset('mesh.nc').load()
        _add_mismip_plus_fields(ds)
        write_netcdf(ds, 'landice_grid.nc')


def _add_mismip_plus_fields(ds):
    """
    Add the bed, the slab, the forcing and the boundary conditions of MISMIP+
    to a MALI mesh
    """
    x_cell = ds.xCell
    y_cell = ds.yCell

    ds['bedTopography'][0, :] = bed_topography(x_cell, y_cell).values
    ds['thickness'][0, :] = xr.where(
        x_cell < CALVING_X, SLAB_THICKNESS, 0.0
    ).values

    # MALI takes the accumulation in kg m^-2 s^-1
    ds['sfcMassBal'][0, :] = ACCUMULATION_RATE * ICE_DENSITY / SECONDS_PER_YEAR

    # MALI removes ice wherever the calving mask is 1
    ds['calvingMask'] = (
        ('Time', 'nCells'),
        np.expand_dims((x_cell > CALVING_X).values.astype(np.int32), axis=0),
    )

    # the walls at y = 0 and the domain's width are the rows of cells with
    # the smallest and largest y.  Albany prescribes only the y-component of
    # velocity (zero) there, which makes them free-slip walls.
    dc = float(ds.dcEdge.values[0])
    dy = 0.5 * np.sqrt(3.0) * dc
    y = y_cell.values
    wall = np.isclose(y, y.min(), atol=0.05 * dy, rtol=0.0) | np.isclose(
        y, y.max(), atol=0.05 * dy, rtol=0.0
    )
    ds['dirichletVelocityMask'][0, :, :] = 0
    ds['dirichletVelocityMask'][0, wall, :] = 1

    # MALI's Weertman law is basal stress = muFriction * N * |u|^m, with
    # the effective pressure N in Pa and u in m per MALI's year
    ds['muFriction'][0, :] = FRICTION_COEFFICIENT / (
        MALI_SECONDS_PER_YEAR**FRICTION_EXPONENT
    )
    ds['effectivePressure'][0, :] = 1.0
