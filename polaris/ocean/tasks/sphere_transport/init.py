import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.ocean.tasks.sphere_transport.resources.flow_types import (
    flow_divergent,
    flow_nondivergent,
    flow_rotation,
)
from polaris.ocean.tasks.sphere_transport.resources.tracer_distributions import (  # noqa: E501
    correlation_fn,
    cosine_bells,
    slotted_cylinders,
    xyztrig,
)
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):
    """
    A step for an initial condition for for the cosine bell test case
    """
    def __init__(self, component, name, subdir, base_mesh, case_name):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        base_mesh : polaris.Step
            The base mesh step

        case_name: str
            The name of the test case
        """
        super().__init__(component=component, name=name, subdir=subdir)

        self.case_name = case_name
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc')

        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{base_mesh.path}/graph.info')

        self.add_output_file(filename='initial_state.nc')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        case_name = self.case_name

        section = config['sphere_transport']
        temperature = section.getfloat('temperature')
        salinity = section.getfloat('salinity')
        vel_pd = section.getfloat('vel_pd')

        section = config['vertical_grid']
        bottom_depth = section.getfloat('bottom_depth')

        ds_mesh = xr.open_dataset('mesh.nc')
        angleEdge = ds_mesh.angleEdge
        latCell = ds_mesh.latCell
        latEdge = ds_mesh.latEdge
        lonCell = ds_mesh.lonCell
        lonEdge = ds_mesh.lonEdge
        sphere_radius = ds_mesh.sphere_radius

        ds = ds_mesh.copy()

        ds['bottomDepth'] = bottom_depth * xr.ones_like(latCell)
        ds['ssh'] = xr.zeros_like(latCell)

        init_vertical_coord(config, ds)

        temperature_array = temperature * xr.ones_like(latCell)
        temperature_array, _ = xr.broadcast(temperature_array, ds.refZMid)
        ds['temperature'] = temperature_array.expand_dims(dim='Time', axis=0)
        ds['salinity'] = salinity * xr.ones_like(ds.temperature)

        # tracer1
        tracer1 = xyztrig(lonCell, latCell, sphere_radius)

        # tracer2
        section = config['sphere_transport']
        radius = section.getfloat('cosine_bells_radius')
        background_value = section.getfloat('cosine_bells_background')
        amplitude = section.getfloat('cosine_bells_amplitude')
        tracer2 = cosine_bells(lonCell, latCell, radius, background_value,
                               amplitude, sphere_radius)

        # tracer3
        if case_name == 'correlated_tracers_2d':
            coeff = config.getlist(case_name, 'correlation_coefficients',
                                   dtype=float)
            tracer3 = correlation_fn(tracer2, coeff[0], coeff[1], coeff[2])
        else:
            section = config['sphere_transport']
            radius = section.getfloat('slotted_cylinders_radius')
            background_value = section.getfloat('slotted_cylinders_background')
            amplitude = section.getfloat('slotted_cylinders_amplitude')
            tracer3 = slotted_cylinders(lonCell, latCell, radius,
                                        background_value, amplitude,
                                        sphere_radius)
        _, tracer1_array = np.meshgrid(ds.refZMid.values, tracer1)
        _, tracer2_array = np.meshgrid(ds.refZMid.values, tracer2)
        _, tracer3_array = np.meshgrid(ds.refZMid.values, tracer3)

        ds['tracer1'] = (('nCells', 'nVertLevels',), tracer1_array)
        ds['tracer1'] = ds.tracer1.expand_dims(dim='Time', axis=0)
        ds['tracer2'] = (('nCells', 'nVertLevels',), tracer2_array)
        ds['tracer2'] = ds.tracer2.expand_dims(dim='Time', axis=0)
        ds['tracer3'] = (('nCells', 'nVertLevels',), tracer3_array)
        ds['tracer3'] = ds.tracer3.expand_dims(dim='Time', axis=0)

        # Initialize velocity
        seconds_per_day = 86400.
        if case_name == 'rotation_2d':
            rotation_vector = config.getlist(case_name, 'rotation_vector',
                                             dtype=float)
            vector = np.array(rotation_vector)
            u, v = flow_rotation(lonEdge, latEdge, vector,
                                 vel_pd * seconds_per_day, sphere_radius)
        elif case_name == 'divergent_2d':
            section = config[case_name]
            vel_amp = section.getfloat('vel_amp')
            u, v = flow_divergent(0., lonEdge, latEdge,
                                  vel_amp, vel_pd * seconds_per_day)
        elif (case_name == 'nondivergent_2d' or
              case_name == 'correlated_tracers_2d'):
            section = config[case_name]
            vel_amp = section.getfloat('vel_amp')
            u, v = flow_nondivergent(0., lonEdge, latEdge,
                                     vel_amp, vel_pd * seconds_per_day)
        else:
            raise ValueError(f'Unexpected test case name {case_name}')

        normalVelocity = sphere_radius * (u * np.cos(angleEdge) +
                                          v * np.sin(angleEdge))
        normalVelocity, _ = xr.broadcast(normalVelocity, ds.refZMid)
        ds['normalVelocity'] = normalVelocity.expand_dims(dim='Time', axis=0)

        ds['fCell'] = xr.zeros_like(ds_mesh.xCell)
        ds['fEdge'] = xr.zeros_like(ds_mesh.xEdge)
        ds['fVertex'] = xr.zeros_like(ds_mesh.xVertex)

        write_netcdf(ds, 'initial_state.nc')
