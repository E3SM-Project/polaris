from polaris.ocean.convergence.analysis import ConvergenceAnalysis


class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the external gravity wave test case
    """

    def __init__(
        self,
        component,
        subdir,
        dependencies,
        refinement='both',
        ref_solution_factor=None,
    ):
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

        refinement : str, optional
            Whether to refine in space, time or both space and time
        """
        convergence_vars = [
            {'name': 'layerThickness', 'title': 'layerThickness', 'zidx': 0},
            {'name': 'normalVelocity', 'title': 'normalVelocity', 'zidx': 0},
        ]
        super().__init__(
            component=component,
            subdir=subdir,
            dependencies=dependencies,
            convergence_vars=convergence_vars,
            refinement=refinement,
        )

        base_mesh = dependencies['mesh'][ref_solution_factor]
        init = dependencies['init'][ref_solution_factor]
        forward = dependencies['forward'][ref_solution_factor]
        self.add_input_file(
            filename=f'mesh_r{ref_solution_factor:02g}.nc',
            work_dir_target=f'{base_mesh.path}/base_mesh.nc',
        )
        self.add_input_file(
            filename=f'init_r{ref_solution_factor:02g}.nc',
            work_dir_target=f'{init.path}/initial_state.nc',
        )
        self.add_input_file(
            filename=f'output_r{ref_solution_factor:02g}.nc',
            work_dir_target=f'{forward.path}/output.nc',
        )

        self.ref_solution_factor = ref_solution_factor

    def exact_solution(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        refinement_factor : float
            The factor by which to scale space, time or both

        field_name : str
            The name of the variable of which we evaluate convergence
            For the default method, we use the same convergence rate for all
            fields

        time : float
            The time at which to evaluate the exact solution in seconds.
            For the default method, we always use the initial state.

        zidx : int, optional
            The z-index for the vertical level at which to evaluate the exact
            solution

        Returns
        -------
        solution : xarray.DataArray
            The exact solution with dimension nCells
        """

        if field_name != 'layerThickness' and field_name != 'normalVelocity':
            print(
                f'Variable {field_name} not available as a reference '
                'solution for the external gravity wave test case'
            )

        field_mpas = super().get_output_field(
            refinement_factor=self.ref_solution_factor,
            field_name=field_name,
            time=time,
            zidx=zidx,
        )
        return field_mpas
