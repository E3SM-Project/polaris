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

    provides_forcing : bool
        Whether this source also supplies the surface forcing file.  A forward
        step only turns the surface forcing on when it has a file to read, so
        sources without one leave the models' (off) defaults alone.
    """

    min_res: float
    approx_cell_count: Optional[int]
    graph_target: Optional[str] = None
    provides_forcing: bool = False

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


class StepInitialCondition(InitialCondition):
    """
    An initial condition provided by an upstream ``realistic_global/init``
    step, whose work directory holds the mesh, vertical coordinate (Omega),
    initial state, and graph files.

    Attributes
    ----------
    init_step : polaris.Step
        The ``initial_state`` step whose outputs are consumed.

    forcing_step : polaris.Step or None
        The ``forcing`` step whose model-specific forcing file is consumed, or
        ``None`` when the forward run gets no surface forcing.
    """

    def __init__(
        self,
        init_step: 'Step',
        min_res: float,
        approx_cell_count: Optional[int],
        forcing_step: Optional['Step'] = None,
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

        forcing_step : polaris.Step, optional
            The ``forcing`` step (from the same
            :py:func:`~polaris.tasks.ocean.realistic_global.init.steps.get_realistic_init_steps`
            call) that writes the model-specific surface forcing file.  When it
            is not given, the forward run is unforced.
        """
        self.init_step = init_step
        self.min_res = min_res
        self.approx_cell_count = approx_cell_count
        self.graph_target = f'{init_step.path}/culled_graph.info'
        self.forcing_step = forcing_step
        self.provides_forcing = forcing_step is not None

    def add_input_files(self, step: 'OceanModelStep') -> None:
        """
        Link the mesh, vertical coordinate, initial state and (when there is a
        forcing step) the surface forcing from the init steps' work
        directories.  The vertical-coordinate entry is dropped for MPAS-Ocean
        by the shared placeholder mechanism, and the graph is linked (and
        partitioned) by ``OceanModelStep`` from ``graph_target``.
        """
        path = self.init_step.path
        step.add_horiz_mesh_input_file(work_dir_target=f'{path}/mesh.nc')
        step.add_vert_coord_input_file(work_dir_target=f'{path}/vert_coord.nc')
        step.add_init_input_file(work_dir_target=f'{path}/init.nc')
        if self.forcing_step is not None:
            forcing_filename = step.get_forcing_filename()
            step.add_forcing_input_file(
                work_dir_target=(
                    f'{self.forcing_step.path}/{forcing_filename}'
                )
            )


class DatabaseInitialCondition(InitialCondition):
    """
    An initial condition staged in the Polaris input-file database and
    referenced by a constructed filename.

    The graph partition file for MPAS-Ocean is built from the mesh by the base
    ``OceanModelStep`` (``graph_target`` is ``None``).  This source is
    implemented and unit-tested but is not yet wired into a registered task;
    the exact database layout and graph handling are finalized when the
    corresponding files are staged.

    Attributes
    ----------
    mesh_name : str
        The mesh name embedded in the database filename.

    mesh_id : int or str
        The mesh id embedded in the database filename.

    eos_type : str or None
        The equation of state embedded in the database filename; when ``None``
        it is read from ``[ocean] eos_type``.

    database : str
        The database subdirectory (the configured model is appended).
    """

    def __init__(
        self,
        mesh_name: str,
        mesh_id,
        min_res: float,
        approx_cell_count: Optional[int],
        eos_type: Optional[str] = None,
        database: str = 'realistic_global',
    ) -> None:
        self.mesh_name = mesh_name
        self.mesh_id = mesh_id
        self.min_res = min_res
        self.approx_cell_count = approx_cell_count
        self.eos_type = eos_type
        self.database = database

    def add_input_files(self, step: 'OceanModelStep') -> None:
        """
        Add the database initial-condition file (and, for Omega, the same file
        as the horizontal mesh, matching the current single-file convention).
        """
        config = step.config
        model = config.get('ocean', 'model')
        eos_type = self.eos_type
        if eos_type is None:
            eos_type = config.get('ocean', 'eos_type')
        # normalize e.g. 'teos-10' -> 'teos10'
        eos_type = eos_type.replace('-', '')
        filename = f'ocean.{self.mesh_name}.{self.mesh_id}.{eos_type}.nc'
        database = f'{self.database}/{model}'
        step.add_init_input_file(target=filename, database=database)
        if model == 'omega':
            step.add_horiz_mesh_input_file(target=filename, database=database)
