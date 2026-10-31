import os
import shutil
from glob import glob

from polaris.e3sm.init.inputdata import ASSEMBLED_FILES
from polaris.io import symlink
from polaris.step import Step

#: A script symlinked into the step's work directory for copying the staged
#: tree into an inputdata directory.  It is deliberately not run by the step:
#: writing into a shared inputdata directory is a decision a person makes.
SYNC_SCRIPT = 'sync_to_inputdata.sh'


class AssembleStep(Step):
    """
    A base step for materializing a staged tree of E3SM input files.

    Product steps write only their own outputs, and a subclass of this step
    links them into :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES` at
    their E3SM-facing paths, so what is in the tree is described in one place
    rather than in every step.

    A subclass declares the products it stages as input files in its
    constructor.  Its ``run()`` calls this class's ``run()``, which rebuilds
    the tree from empty and stages the README, and then calls :py:meth:`stage`
    and :py:meth:`stage_partitions`.  Staging happens at run time because the
    staged paths carry names, such as the creation date, that come from config
    options a person may change after setup.
    """

    def __init__(
        self,
        component,
        name,
        subdir,
        readme_package,
        readme_filename='README',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        name : str
            The name of the step.

        subdir : str
            The subdirectory for the step.

        readme_package : str
            The package the README staged at the top of the tree comes from.
            What a tree does and does not hold is particular to the workflow
            that stages it, so each supplies its own.

        readme_filename : str, optional
            The README's filename in ``readme_package``.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.add_input_file(
            filename='README', target=readme_filename, package=readme_package
        )
        # not staged: a helper the person doing the copy runs by hand
        self.add_input_file(filename=SYNC_SCRIPT, package=__package__)

    def run(self):
        """
        Rebuild the staged tree from empty and stage the README.

        The tree is deleted first so that it describes this assembly and not
        the union of every assembly ever run here.  Staging only ever adds
        links, so without this a changed creation date, mesh name or product
        set leaves the previous names behind -- still resolving, and now
        pointing at newer content.  Rebuilding is a few hundred symlinks,
        which is cheap next to being unable to trust what is in the tree.
        """
        super().run()
        if os.path.exists(ASSEMBLED_FILES):
            shutil.rmtree(ASSEMBLED_FILES)
        self.stage('README', 'README')

    def stage(self, source, staged_path):
        """
        Link one product into the assembled tree at its E3SM-facing path.

        Parameters
        ----------
        source : str
            The product, relative to the step's work directory.

        staged_path : str
            The path to link it to, relative to
            :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.
        """
        destination = os.path.join(ASSEMBLED_FILES, staged_path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        symlink(os.path.abspath(source), destination)

    def stage_partitions(self, step, basename, path_func):
        """
        Link every partition the given step produced.

        Found by listing rather than by recomputing the core list, so that the
        staged tree describes what was actually built.

        Parameters
        ----------
        step : polaris.Step
            The step that wrote the partitions.

        basename : str
            The stem of the partition files, ``<basename>.part.<ncores>``.

        path_func : callable
            Takes a core count and returns the path to stage that partition
            at, relative to
            :py:data:`~polaris.e3sm.init.inputdata.ASSEMBLED_FILES`.

        Raises
        ------
        FileNotFoundError
            If the step produced no partitions.
        """
        step_dir = self.step_dir(step)
        found = sorted(glob(os.path.join(step_dir, f'{basename}.part.*')))
        if not found:
            raise FileNotFoundError(
                f'{step.name} produced no partition files in {step_dir}.'
            )
        for source in found:
            ncores = int(os.path.basename(source).rsplit('.', 1)[-1])
            self.stage(source, path_func(ncores))

    def step_dir(self, step):
        """
        The work directory of another step, found from this one's.

        Parameters
        ----------
        step : polaris.Step
            The other step.

        Returns
        -------
        str
            The other step's work directory.
        """
        relative = os.path.relpath(step.path, self.path)
        return os.path.normpath(os.path.join(self.work_dir, relative))
