from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from polaris import Step
    from polaris.ocean.model import OceanModelStep


class InitialCondition(ABC):
    """
    An abstraction for where a forward step's model inputs come from.

    A concrete subclass knows how to add the horizontal-mesh, vertical-
    coordinate, and initial-state input files to a forward step and, where
    relevant, which graph partition file the step should use.  The forward step
    holds one of these and defers all questions of provenance to it, so a new
    source can be added without changing the step or the run-settings logic.

    Attributes
    ----------
    min_res : float
        The mesh minimum resolution in km, used to scale per-km time steps.

    approx_cell_count : int or None
        The approximate number of cells in the mesh, used to size resources
        during setup before the mesh file exists.  ``None`` when it cannot be
        estimated for the mesh.

    graph_target : str or None
        The graph partition file for the step to use (a work-directory-relative
        path), or ``None`` when no existing graph file is provided.

    provides_forcing_file : bool
        Whether the model reads its surface forcing from a file this source
        stages.  Every realistic_global forward run is wind-forced, so this is
        true for every source that is wired into a task; it exists so that a
        future source which forces the run some other way can say so.
    """

    min_res: float
    approx_cell_count: Optional[int]
    graph_target: Optional[str] = None
    provides_forcing_file: bool = False

    @abstractmethod
    def add_input_files(self, step: 'OceanModelStep') -> None:
        """
        Add the model input files this source provides to ``step``.

        Called from the forward step's ``setup()`` (so ``step.config`` and the
        configured model are available).

        Parameters
        ----------
        step : polaris.ocean.model.OceanModelStep
            The forward step to add input files to.
        """

    def get_forcing_filename(self, step: 'OceanModelStep') -> str:
        """
        The local filename the model's forcing streams should read.

        A source that stages a forcing file of its own uses the configured
        forcing filename, which is the default here.  A source whose wind
        stress travels inside another file overrides this to name that file
        instead, so that the forcing streams are pointed at it without the
        forward step needing to know which case it is in.

        Parameters
        ----------
        step : polaris.ocean.model.OceanModelStep
            The forward step, which knows the configured staged filenames.

        Returns
        -------
        str
            The local filename holding the surface forcing.
        """
        return step.get_forcing_filename()


class StepInitialCondition(InitialCondition):
    """
    An initial condition provided by an upstream ``realistic_global/init``
    step, whose work directory holds the mesh, vertical coordinate (Omega),
    initial state, and graph files.

    Attributes
    ----------
    init_step : polaris.Step
        The ``initial_state`` step whose outputs are consumed.

    forcing_step : polaris.Step
        The ``forcing`` step whose model-specific forcing file is consumed.
    """

    def __init__(
        self,
        init_step: 'Step',
        min_res: float,
        approx_cell_count: Optional[int],
        forcing_step: 'Step',
    ) -> None:
        """
        Create the source.

        Parameters
        ----------
        init_step : polaris.Step
            The ``initial_state`` step (from
            :py:func:`~polaris.tasks.ocean.realistic_global.init.steps.get_realistic_init_steps`)
            whose outputs the forward step consumes.

        min_res : float
            The mesh minimum resolution in km (from the mesh definition).

        approx_cell_count : int or None
            The approximate number of cells in the mesh (from the mesh
            definition), used to size resources during setup before the mesh
            file exists.

        forcing_step : polaris.Step
            The ``forcing`` step (from the same
            :py:func:`~polaris.tasks.ocean.realistic_global.init.steps.get_realistic_init_steps`
            call) that writes the model-specific surface forcing file.
            Required, because every realistic_global forward run is
            wind-forced.
        """
        self.init_step = init_step
        self.min_res = min_res
        self.approx_cell_count = approx_cell_count
        self.graph_target = f'{init_step.path}/culled_graph.info'
        self.forcing_step = forcing_step
        self.provides_forcing_file = True

    def add_input_files(self, step: 'OceanModelStep') -> None:
        """
        Link the mesh, vertical coordinate, initial state and surface forcing
        from the init steps' work directories.  The vertical-coordinate entry
        is dropped for MPAS-Ocean by the shared placeholder mechanism, and the
        graph is linked (and partitioned) by ``OceanModelStep`` from
        ``graph_target``.

        The initial state is linked only when the run actually reads it.  A
        stage that continues from a restart does not: MPAS-Ocean reads the
        ``restart`` stream and never touches ``input`` when
        ``config_do_restart`` is set (``mpas_ocn_forward_mode.F``), and Omega's
        ``InitialState`` is switched off with ``FreqUnits: never``.  The mesh,
        in contrast, is read either way.  Linking a file a stage never opens
        only makes the work directory misleading about where its state came
        from.
        """
        path = self.init_step.path
        step.add_horiz_mesh_input_file(work_dir_target=f'{path}/mesh.nc')
        step.add_vert_coord_input_file(work_dir_target=f'{path}/vert_coord.nc')
        if _reads_initial_state(step):
            step.add_init_input_file(work_dir_target=f'{path}/init.nc')
        forcing_filename = step.get_forcing_filename()
        step.add_forcing_input_file(
            work_dir_target=f'{self.forcing_step.path}/{forcing_filename}'
        )


class DatabaseInitialCondition(InitialCondition):
    """
    An initial condition staged in the Polaris input-file database, under
    ``{database}/{model}/{mesh_name}``.

    A single database file supplies everything the model reads: the mesh, the
    initial state, the vertical coordinate for Omega, and the wind stress.  The
    two models are given different files, produced by
    ``utils/omega/convert_mpaso_ic_to_omega.py`` from the same MPAS-Ocean
    source, and named accordingly:

    - MPAS-Ocean: ``ocean.{mesh_name}.{mpaso_id}.zerovel.nc``, a zero-initial-
      velocity file, plus a prebuilt ``graph.info.{mpaso_id}``.
    - Omega: ``ocean.{mesh_name}.{mpaso_id}.{eos_type}.{omega_id}.nc``.  Omega
      partitions internally, so it needs no graph file.

    The asymmetry in those names -- ``zerovel`` on one side, an equation of
    state and a second id on the other -- is not a design, it is what is on the
    server.  Renaming means re-staging every file, so it waits until the
    ``realistic_global/init`` workflow can produce database initial conditions
    itself.

    The run is wind-forced like any other realistic_global forward run, but the
    wind stress travels inside the initial-condition file rather than in a
    forcing file of its own, so :py:meth:`get_forcing_filename` points the
    forcing streams at the initial condition.

    Attributes
    ----------
    mesh_name : str
        The mesh name embedded in the database path and filenames.

    mpaso_id : int or str
        The id of the MPAS-Ocean initial condition the files derive from.

    omega_id : int or str or None
        The id of the Omega conversion; required to run Omega.

    eos_type : str or None
        The equation of state embedded in the Omega filename; when ``None`` it
        is read from ``[ocean] eos_type``.

    database : str
        The top-level database subdirectory.
    """

    def __init__(
        self,
        mesh_name: str,
        mpaso_id,
        min_res: float,
        approx_cell_count: Optional[int],
        omega_id=None,
        eos_type: Optional[str] = None,
        database: str = 'realistic_global',
    ) -> None:
        """
        Create the source.

        Parameters
        ----------
        mesh_name : str
            The mesh name embedded in the database path and filenames.

        mpaso_id : int or str
            The id of the MPAS-Ocean initial condition.

        min_res : float
            The mesh minimum resolution in km.

        approx_cell_count : int or None
            The approximate number of cells in the mesh, used to size resources
            during setup before the mesh file is downloaded.

        omega_id : int or str, optional
            The id of the Omega conversion.  Required only to run Omega.

        eos_type : str, optional
            The equation of state embedded in the Omega filename; read from
            ``[ocean] eos_type`` when not given.

        database : str, optional
            The top-level database subdirectory.
        """
        self.mesh_name = mesh_name
        self.mpaso_id = mpaso_id
        self.omega_id = omega_id
        self.min_res = min_res
        self.approx_cell_count = approx_cell_count
        self.eos_type = eos_type
        self.database = database
        # the wind stress is in the initial-condition file
        self.provides_forcing_file = True
        # graph.info comes from the database rather than an upstream work
        # directory, and is added in add_input_files() once the model is known
        self.graph_target = None

    def add_input_files(self, step: 'OceanModelStep') -> None:
        """
        Add the database files the configured model reads.

        The same file is registered under several local names because it holds
        several things: for Omega it is the mesh, the vertical coordinate and
        the initial state at once, and for MPAS-Ocean the mesh and the initial
        state.  ``graph.info`` is added here rather than by ``OceanModelStep``
        because it too comes from the database.
        """
        model = step.config.get('ocean', 'model')
        database = f'{self.database}/{model}/{self.mesh_name}'
        filename = self._filename(step, model)
        step.add_init_input_file(target=filename, database=database)
        step.add_horiz_mesh_input_file(target=filename, database=database)
        if model == 'omega':
            step.add_vert_coord_input_file(target=filename, database=database)
        else:
            step.add_input_file(
                filename='graph.info',
                target=f'graph.info.{self.mpaso_id}',
                database=database,
            )

    def get_forcing_filename(self, step: 'OceanModelStep') -> str:
        """
        The initial-condition file, which is where the wind stress lives.
        """
        return step.get_init_filename()

    def _filename(self, step: 'OceanModelStep', model: str) -> str:
        """The database filename for ``model``."""
        if model != 'omega':
            return f'ocean.{self.mesh_name}.{self.mpaso_id}.zerovel.nc'
        if self.omega_id is None:
            raise ValueError(
                f'No omega_id was given for mesh {self.mesh_name!r}, so the '
                f'Omega initial condition in the {self.database} database '
                f'cannot be named.  Set omega_id to run this task with Omega.'
            )
        eos_type = self.eos_type
        if eos_type is None:
            eos_type = step.config.get('ocean', 'eos_type')
        # normalize e.g. 'teos-10' -> 'teos10'
        eos_type = eos_type.replace('-', '')
        return (
            f'ocean.{self.mesh_name}.{self.mpaso_id}.{eos_type}.'
            f'{self.omega_id}.nc'
        )


def _reads_initial_state(step: 'OceanModelStep') -> bool:
    """
    Whether ``step`` reads an initial state, as opposed to a restart.

    A forward step carries the ``ForwardStage`` it runs; a step that has no
    stage is a plain forward run and always starts from the initial state.
    """
    stage = getattr(step, 'stage', None)
    return stage is None or not stage.do_restart
