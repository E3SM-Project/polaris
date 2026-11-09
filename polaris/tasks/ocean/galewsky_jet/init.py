import xarray as xr
from mpas_tools.io import open_dataset

from polaris.coriolis import add_coriolis_to_dataset
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical import init_vertical_coord
from polaris.tasks.ocean.galewsky_jet.initial_state import (
    balanced_height,
    get_jet_params,
    height_perturbation,
    normal_velocity_from_streamfunction,
    streamfunction,
)


class Init(OceanIOStep):
    """
    A step for the initial condition of the Galewsky jet: the balanced jet,
    optionally with the height perturbation that triggers its instability

    Attributes
    ----------
    perturbed : bool
        Whether to add the height perturbation
    """

    def __init__(self, component, name, subdir, base_mesh, perturbed):
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

        perturbed : bool
            Whether to add the height perturbation
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.perturbed = perturbed

        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc',
        )

        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{base_mesh.path}/graph.info',
        )

        # needed to write the horizontal mesh for Omega on a sphere
        self.add_input_file(
            filename='reconstruction_weights.nc',
            work_dir_target=f'{base_mesh.path}/reconstruction_weights.nc',
        )

    def setup(self):
        """
        Add the output files for the ocean model's input
        """
        super().setup()
        self.add_output_files_for_ocean_model_input(
            horiz_mesh_filename='culled_mesh.nc',
            vert_coord_filename='vert_coord.nc',
            init_filename='init.nc',
        )

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        params = get_jet_params(config)
        jet = dict(
            u_max=params['u_max'], phi0=params['phi0'], phi1=params['phi1']
        )

        section = config['galewsky_jet']
        temperature = section.getfloat('temperature')
        salinity = section.getfloat('salinity')
        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds_mesh = open_dataset(self.work_path('mesh.nc'))
        lat_cell = ds_mesh.latCell.drop_attrs()

        h = balanced_height(lat_cell.values, h_mean=params['h_mean'], **jet)
        if self.perturbed:
            h = h + height_perturbation(
                ds_mesh.lonCell.values,
                lat_cell.values,
                h_hat=params['h_hat'],
                alpha=params['alpha'],
                beta=params['beta'],
                phi2=params['phi2'],
            )

        psi = streamfunction(ds_mesh.latVertex.values, **jet)
        normal_velocity = xr.DataArray(
            normal_velocity_from_streamfunction(ds_mesh, psi),
            dims=('nEdges',),
        )

        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        self.write_horiz_mesh_dataset(
            ds_mesh, self.work_path('culled_mesh.nc'), config
        )

        ds = ds_mesh.copy()
        ds['bottomDepth'] = bottom_depth * xr.ones_like(lat_cell)
        ds['ssh'] = xr.DataArray(h, dims=('nCells',)) - ds.bottomDepth

        init_vertical_coord(config, ds)
        temperature_array = temperature * xr.ones_like(lat_cell)
        temperature_array, _ = xr.broadcast(temperature_array, ds.refZMid)
        salinity_array = salinity * xr.ones_like(temperature_array)
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refZMid)

        ds['temperature'] = temperature_array.expand_dims(dim='Time', axis=0)
        ds['salinity'] = salinity_array.expand_dims(dim='Time', axis=0)
        ds['normalVelocity'] = normal_velocity.expand_dims(dim='Time', axis=0)
        # temperature and salinity must be set before this call:
        # write_vert_coord_dataset converts restingThickness to
        # RefPseudoThickness via pseudothickness_from_ds, which requires T/S
        self.write_vert_coord_dataset(
            ds, self.work_path('vert_coord.nc'), config
        )

        self.write_initial_state_dataset(ds, self.work_path('init.nc'), config)
