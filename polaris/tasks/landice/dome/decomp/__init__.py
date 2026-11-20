from polaris import Task
from polaris.tasks.landice.dome.forward import Forward
from polaris.tasks.landice.dome.validate import (
    EXACT_NORMS,
    FO_NORMS,
    Validate,
)


class Decomp(Task):
    """
    A dome task that makes sure MALI gives the same results on 1 and 4 tasks
    """

    def __init__(self, component, velocity_solver, indir, init):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.landice.Landice
            The landice component that this task belongs to

        velocity_solver : {'sia', 'FO'}
            MALI's velocity solver

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.landice.dome.init.Init
            The shared step that makes the mesh and initial condition
        """
        super().__init__(component=component, name='decomp', indir=indir)

        self.add_step(init, symlink='init')

        subdirs = list()
        for procs in [1, 4]:
            name = f'{procs}proc'
            self.add_step(
                Forward(
                    component=component,
                    init=init,
                    velocity_solver=velocity_solver,
                    name=name,
                    indir=self.subdir,
                    ntasks=procs,
                )
            )
            subdirs.append(name)

        if velocity_solver == 'FO':
            norms = FO_NORMS
        else:
            norms = EXACT_NORMS

        self.add_step(
            Validate(
                component=component,
                step_subdirs=subdirs,
                indir=self.subdir,
                norms=norms,
            )
        )
