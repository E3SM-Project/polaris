import cmocean  # noqa: F401
import xarray as xr

from polaris.ocean.convergence.analysis import ConvergenceAnalysis
from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.galewsky_jet.diagnostics import relative_vorticity
from polaris.tasks.ocean.galewsky_jet.initial_state import (
    balanced_height,
    get_jet_params,
    normal_velocity_from_streamfunction,
    streamfunction,
)
from polaris.viz import plot_global_mpas_field


class SteadyStateAnalysis(ConvergenceAnalysis):
    """
    A step for analyzing how far the unperturbed jet drifts from its initial
    state at each resolution

    Attributes
    ----------
    mesh_type : {'icos', 'qu'}
        The type of mesh, which selects the convergence thresholds
    """

    def __init__(self, component, subdir, dependencies, mesh_type):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step

        mesh_type : {'icos', 'qu'}
            The type of mesh, which selects the convergence thresholds
        """
        self.mesh_type = mesh_type
        convergence_vars = [
            {'name': 'h', 'title': 'layer thickness', 'zidx': None},
            {'name': 'normalVelocity', 'title': 'normal velocity', 'zidx': 0},
        ]
        super().__init__(
            component=component,
            subdir=subdir,
            dependencies=dependencies,
            convergence_vars=convergence_vars,
            refinement='both',
        )

    def exact_solution(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the exact solution, the balanced initial state

        Parameters
        ----------
        refinement_factor : float
            The factor by which to scale space and time

        field_name : str
            The name of the variable, ``h`` or ``normalVelocity``

        time : float
            The time in seconds, unused because the solution is steady

        zidx : int, optional
            The z-index, unused because there is a single layer

        Returns
        -------
        solution : xarray.DataArray
            The exact solution on cells or edges
        """
        ds_mesh = self.open_model_dataset(
            self.work_path(f'mesh_r{refinement_factor:02g}.nc'), self.config
        )
        params = get_jet_params(self.config)
        jet = dict(
            u_max=params['u_max'], phi0=params['phi0'], phi1=params['phi1']
        )
        if field_name == 'h':
            h = balanced_height(
                ds_mesh.latCell.values, h_mean=params['h_mean'], **jet
            )
            return xr.DataArray(h, dims=('nCells',))
        elif field_name == 'normalVelocity':
            psi = streamfunction(ds_mesh.latVertex.values, **jet)
            normal_velocity = normal_velocity_from_streamfunction(ds_mesh, psi)
            return xr.DataArray(normal_velocity, dims=('nEdges',))
        raise ValueError(
            f'No exact solution for {field_name} in the steady_state task'
        )

    def get_output_field(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the model output field at the given time

        Parameters
        ----------
        refinement_factor : float
            The factor by which to scale space and time

        field_name : str
            The name of the variable, ``h`` or ``normalVelocity``

        time : float
            The time at which to evaluate the field in seconds

        zidx : int, optional
            The z-index for the vertical level to take the field from

        Returns
        -------
        field : xarray.DataArray
            The model output field
        """
        if field_name == 'normalVelocity':
            return super().get_output_field(
                refinement_factor=refinement_factor,
                field_name=field_name,
                time=time,
                zidx=zidx,
            )

        ds_init = self.open_model_dataset(
            self.work_path(f'init_r{refinement_factor:02g}.nc'), self.config
        )
        ds_vert_coord = self.open_vert_coord_dataset(
            ds_init,
            vert_coord_filename=self.work_path(
                f'vert_coord_r{refinement_factor:02g}.nc'
            ),
        )
        ssh = super().get_output_field(
            refinement_factor=refinement_factor,
            field_name='ssh',
            time=time,
            zidx=None,
        )
        return ssh + ds_vert_coord.bottomDepth

    def convergence_parameters(self, field_name=None):
        """
        Get convergence parameters

        Parameters
        ----------
        field_name : str
            The name of the variable, ``h`` or ``normalVelocity``

        Returns
        -------
        conv_thresh : float
            The minimum convergence rate

        error_type : {'l2', 'inf'}
            The error norm to compute
        """
        config = self.config
        conv_thresh = config.getfloat(
            'galewsky_jet_steady_state',
            f'convergence_thresh_{self.mesh_type}_{field_name}',
        )
        error_type = config.get('convergence', 'error_type')
        return conv_thresh, error_type


class SteadyStateViz(OceanIOStep):
    """
    A step for plotting the relative vorticity of the unperturbed jet at the
    end of the run, and its change from the initial state

    Attributes
    ----------
    mesh_name : str
        The name of the mesh
    """

    def __init__(self, component, name, subdir, init, forward, mesh_name):
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

        init : polaris.Step
            The init step

        forward : polaris.Step
            The forward step

        mesh_name : str
            The name of the mesh
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=f'{init.path}/culled_mesh.nc',
        )
        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/init.nc',
        )
        self.add_input_file(
            filename='output.nc', work_dir_target=f'{forward.path}/output.nc'
        )
        self.mesh_name = mesh_name
        for filename in ['final_vorticity.png', 'diff_vorticity.png']:
            self.add_output_file(filename)

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        mesh_name = self.mesh_name
        run_days = (
            config.getfloat('galewsky_jet_steady_state', 'run_duration') / 24.0
        )

        ds_mesh = self.open_model_dataset(self.work_path('mesh.nc'), config)
        ds_init = self.open_model_dataset(
            self.work_path('initial_state.nc'), config
        )
        ds_out = self.open_model_dataset(
            self.work_path('output.nc'), config, decode_times=False
        )

        normal_velocity = ds_init.normalVelocity.isel(
            Time=0, nVertLevels=0
        ).values
        vort_init = relative_vorticity(ds_mesh, normal_velocity)

        normal_velocity = ds_out.normalVelocity.isel(
            Time=-1, nVertLevels=0
        ).values
        vort_final = relative_vorticity(ds_mesh, normal_velocity)

        plots = dict(
            final_vorticity=(
                vort_final,
                'galewsky_jet_viz_vort',
                f'{mesh_name} relative vorticity after {run_days:g} days',
            ),
            diff_vorticity=(
                vort_final - vort_init,
                'galewsky_jet_viz_diff_vort',
                f'{mesh_name} vorticity change after {run_days:g} days',
            ),
        )
        for prefix, (values, colormap_section, title) in plots.items():
            plot_global_mpas_field(
                mesh_ds=ds_mesh,
                da=xr.DataArray(values, dims=('nVertices',)),
                out_filename=self.work_path(f'{prefix}.png'),
                config=config,
                colormap_section=colormap_section,
                colorbar_label=config.get(colormap_section, 'label'),
                title=title,
                plot_land=False,
            )
