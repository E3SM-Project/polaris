import os
import shutil

from polaris.tasks.ocean.realistic_global.forward import Forward

#: The package holding this task's yaml overrides
PACKAGE = 'polaris.tasks.ocean.realistic_global.restart'


class RestartStep(Forward):
    """
    One segment of the realistic global restart chain.

    The chain is two segments that between them cover the same period as the
    task's ``full_run``.  Both segments read and write restarts through a
    ``restarts`` directory shared by the whole task, following the restart
    chain in ``realistic_global/dynamic_adjustment``, and the continuing
    segment appends its history to the frames the first segment already
    wrote.

    Attributes
    ----------
    previous_step : polaris.Step or None
        The segment this one continues from, or ``None`` for the first
        segment of the chain.
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        mesh_name,
        mpaso_id,
        omega_id,
        ncells,
        replacements,
        previous_step=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        mesh_name : str
            The name of the mesh (e.g. ``QU.240km``)

        mpaso_id : int
            The ID of the MPAS-Ocean initial condition in the Polaris input
            database

        omega_id : int
            The ID of the Omega initial condition in the Polaris input
            database

        ncells : int
            The approximate number of cells in the mesh, used to constrain
            resources

        replacements : dict
            Template replacements for the forward yaml files

        previous_step : polaris.Step, optional
            The segment this one continues from.  When given, this step reads
            that segment's restart and appends to its history file.
        """
        super().__init__(
            component=component,
            package='polaris.tasks.ocean.realistic_global',
            name=name,
            subdir=subdir,
            mesh_name=mesh_name,
            mpaso_id=mpaso_id,
            omega_id=omega_id,
            ncells=ncells,
            replacements=replacements,
        )

        self.previous_step = previous_step

        if previous_step is not None:
            # under a name of its own, so that the copy made in
            # runtime_setup() writes to output.nc rather than through a
            # symlink into the previous segment's work directory
            self.add_input_file(
                filename='previous_output.nc',
                work_dir_target=f'{previous_step.path}/output.nc',
            )

    def setup(self):
        """
        Add this task's overrides on top of the shared realistic_global
        forward yaml, which ``Forward.setup()`` adds first
        """
        model = self.config.get('ocean', 'model')
        if model != 'omega':
            raise ValueError(
                f'The realistic_global restart task supports only Omega, not '
                f'{model!r}.  It is a regression test for the way Omega '
                f'writes its history time axis across a restart (Omega '
                f'#482), and MPAS-Ocean stamps its output with xtime rather '
                f'than an elapsed time measured from the clock start, so the '
                f'failure it looks for cannot arise there.'
            )

        super().setup()

        replacements = dict(
            self.replacements,
            restart_read_dir=self.restart_read_target(),
            restart_write_dir=self.restart_write_target(),
        )

        self.add_yaml_file(
            package=PACKAGE,
            yaml='forward.yaml',
            template_replacements=replacements,
        )

    def runtime_setup(self):
        """
        Make the shared restart directory, and seed the history file with the
        previous segment's frames when this segment continues from one
        """
        super().runtime_setup()

        os.makedirs(self.restart_write_dir(), exist_ok=True)

        if self.previous_step is None:
            return

        # Reproduce what a continuation run finds on disk: a history file
        # that already holds the earlier frames and has to be appended to.
        # This is copied rather than symlinked so that appending to it cannot
        # reach back into the previous segment's work directory.
        shutil.copy(
            os.path.join(self.work_dir, 'previous_output.nc'),
            os.path.join(self.work_dir, 'output.nc'),
        )

    def restart_write_dir(self):
        """
        The absolute path of the directory this segment writes its restart
        into
        """
        return os.path.normpath(
            os.path.join(self.work_dir, self.restart_write_target())
        )

    def restart_write_target(self):
        """
        The path, relative to the step's work directory, that this segment
        writes its restart into.  Each segment gets one of its own, so that
        a segment's own restart cannot replace the pointer it read from.
        """
        return f'../restarts/{self.name}'

    def restart_read_target(self):
        """
        The path, relative to the step's work directory, that this segment
        reads a restart from.  A segment that starts from an initial state
        never opens it, so it is pointed at its own directory.
        """
        if self.previous_step is None:
            return self.restart_write_target()
        return f'../restarts/{self.previous_step.name}'
