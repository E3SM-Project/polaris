from polaris.landice.model import MaliModelStep


class Forward(MaliModelStep):
    """
    A step for running MALI on the dome mesh
    """

    def __init__(
        self,
        component,
        init,
        velocity_solver,
        name='forward',
        indir=None,
        ntasks=4,
        min_tasks=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        init : polaris.tasks.landice.dome.init.Init
            The shared step that makes the mesh and initial condition

        velocity_solver : {'sia', 'FO'}
            MALI's velocity solver

        name : str, optional
            The name of the step

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

        ntasks : int, optional
            The number of tasks to run on

        min_tasks : int, optional
            The minimum number of tasks to run on, ``ntasks`` by default
        """
        if min_tasks is None:
            min_tasks = ntasks
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=1,
            velocity_solver=velocity_solver,
            albany_input_package='polaris.tasks.landice.dome',
        )

        self.add_input_file(
            filename='landice_grid.nc',
            work_dir_target=f'{init.path}/landice_grid.nc',
        )
        self.add_input_file(
            filename='graph.info', work_dir_target=f'{init.path}/graph.info'
        )

        self.add_namelist_file(
            'polaris.tasks.landice.dome', 'namelist.landice'
        )
        self.add_streams_file('polaris.tasks.landice.dome', 'streams.landice')

        self.add_output_file(
            filename='output.nc', validate_vars=['thickness', 'normalVelocity']
        )
