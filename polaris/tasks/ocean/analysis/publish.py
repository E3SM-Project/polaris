import os

from polaris import Step
from polaris.analysis import generate_site, publish
from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.provenance import get_summary

#: The pickle a dependency leaves behind, which is what makes a step that
#: did not run report itself by name rather than as an empty gallery
DEPENDENCY_PICKLE = 'step_after_run.pickle'


class Publish(Step):
    """
    A step that publishes what the analysis steps made and generates the
    gallery over it

    This is the only step that knows how results are presented.  It reads
    each step's manifest fragment, symlinks the products into the staging
    tree, renders a thumbnail for each plot, writes the merged manifest, and
    generates the site.  Working from the fragments rather than from the
    directory structure is what lets the work be re-chunked later without
    disturbing output paths, links, or the gallery.

    The step never looks for its inputs.  It declares every step that makes
    products as a dependency, so Polaris checks that each of them ran before
    this step is allowed to, and names the ones that did not.  Nothing
    reorders steps, so the suite has to list this one last.

    A fragment itself is optional.  A step that ran but made no products
    writes none, and that is reported rather than treated as a failure,
    which is what a developer iterating on a single plot wants.
    """

    def __init__(self, component, subdir, product_steps):
        """
        Create the publish step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        product_steps : list of polaris.Step
            The steps that make products, each of which becomes a dependency
        """
        super().__init__(
            component=component,
            name='publish',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        for step in product_steps:
            self._add_product_dependency(step)

    def run(self):
        """
        Publish every product the fragments describe and generate the gallery
        """
        config = self.config
        output_path = self.output_path()
        fragments = [
            os.path.join(self.base_work_dir, step.path, FRAGMENT_FILENAME)
            for step in self.dependencies.values()
        ]

        published, _ = publish(
            fragment_filenames=fragments,
            output_path=output_path,
            logger=self.logger,
            thumbnail_size=tuple(
                config.getlist('ocean_analysis', 'thumbnail_size', dtype=int)
            ),
            thumbnail_format=config.get('ocean_analysis', 'thumbnail_format'),
            thumbnail_quality=config.getint(
                'ocean_analysis', 'thumbnail_quality'
            ),
        )

        generate_site(
            published=published,
            output_path=output_path,
            simulation_name=config.get('ocean_analysis', 'simulation_name'),
            provenance=get_summary(config=config),
        )
        self.logger.info(f'published to {output_path}')

    def output_path(self):
        """
        Get the root of the staging tree results are published into

        Returns
        -------
        output_path : str
            The ``[ocean_analysis] output_path`` config option, or
            ``analysis_output`` in the base work directory if it is not set
        """
        output_path = self.config.get('ocean_analysis', 'output_path')
        if not output_path:
            output_path = os.path.join(self.base_work_dir, 'analysis_output')
        return output_path

    def _add_product_dependency(self, step):
        """
        Depend on one step that makes products, naming it for its work
        directory so that two ranges of one product do not collide

        The task rebuilds its steps whenever the config is read, so a step
        whose work directory did not change is asked a second time for the
        pickle it already owes.  The duplicate is dropped rather than left
        for Polaris to check twice.
        """
        already_a_dependency = DEPENDENCY_PICKLE in step.outputs
        name = step.subdir.replace('/', '_')
        self.add_dependency(step, name=name)
        if already_a_dependency:
            step.outputs.remove(DEPENDENCY_PICKLE)
