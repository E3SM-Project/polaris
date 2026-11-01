import os

from polaris import Step
from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.analysis.publish import publish
from polaris.analysis.site import generate_site
from polaris.provenance import get_summary

#: The subdirectory the fragments are linked into, one per step
FRAGMENTS_DIRNAME = 'fragments'


class PublishStep(Step):
    """
    A step that publishes what product steps made and generates the gallery
    over it

    This is the only step that knows how results are presented.  It reads
    each step's manifest fragment, copies the products into the staging
    tree, renders a thumbnail for each plot, writes the merged manifest, and
    generates the site.  Working from the fragments rather than from the
    directory structure is what lets the work be re-chunked later without
    disturbing output paths, links, or the gallery.

    The step never looks for its inputs.  Each fragment is a declared input,
    linked into ``fragments/`` from the step that wrote it, so Polaris checks
    before this step runs that every one of them is there and names the ones
    that are not.  Each of those steps is also declared as a dependency,
    which is what reaches anything knowable only after a step has run and
    what names a step that never ran at all.  Nothing reorders steps, so the
    task has to list this one last.

    Every step that makes products writes a fragment, even when it made
    nothing: an empty product list is what a step with nothing to publish
    writes, and it is what lets the fragment be declared rather than looked
    for.

    The step reads its options from one config section, which holds
    ``output_path``, ``simulation_name``, ``copy_netcdf``,
    ``thumbnail_size``, ``thumbnail_scale``, ``thumbnail_format`` and
    ``thumbnail_quality``.

    Attributes
    ----------
    section : str
        The config section the step's options are in

    fragment_filenames : list of str
        The fragments, as local paths within this step's work directory, in
        the order the steps that wrote them are listed
    """

    def __init__(self, component, subdir, product_steps, section):
        """
        Create the publish step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        product_steps : list of polaris.analysis.product_step.ProductStep
            The steps whose products are published.  Each that sets
            ``makes_products`` becomes a dependency, and the rest are left
            out.

        section : str
            The config section the step's options are in
        """
        super().__init__(
            component=component,
            name='publish',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.section = section
        self.fragment_filenames: list = []
        for step in product_steps:
            if getattr(step, 'makes_products', False):
                self._add_product_dependency(step)

    def run(self):
        """
        Publish every product the fragments describe and generate the gallery
        """
        section = self.config[self.section]
        output_path = self.output_path()

        published, _ = publish(
            fragment_filenames=[
                self.work_path(filename)
                for filename in self.fragment_filenames
            ],
            output_path=output_path,
            logger=self.logger,
            thumbnail_size=tuple(
                self.config.getlist(self.section, 'thumbnail_size', dtype=int)
            ),
            thumbnail_scale=section.getfloat('thumbnail_scale'),
            thumbnail_format=section.get('thumbnail_format'),
            thumbnail_quality=section.getint('thumbnail_quality'),
            copy_data=section.getboolean('copy_netcdf'),
        )

        generate_site(
            published=published,
            output_path=output_path,
            simulation_name=section.get('simulation_name'),
            provenance=get_summary(config=self.config),
        )
        self.logger.info(f'published to {output_path}')

    def output_path(self):
        """
        Get the root of the staging tree results are published into

        Returns
        -------
        output_path : str
            The ``output_path`` config option, or ``analysis_output`` in the
            base work directory if it is not set
        """
        output_path = self.config.get(self.section, 'output_path')
        if not output_path:
            output_path = os.path.join(self.base_work_dir, 'analysis_output')
        return output_path

    def _add_product_dependency(self, step):
        """
        Declare one step's fragment as an input and the step as a dependency,
        naming both for its work directory so that two keys of one product
        do not collide

        A task that rebuilds its steps whenever the config is read asks a
        step whose work directory did not change a second time for the
        pickle it already owes.  ``add_output_file()`` keeps only the first
        of those, so the pickle is listed once however often the step is
        rebuilt.
        """
        name = step.subdir.replace('/', '_')
        self.add_dependency(step, name=name)

        filename = os.path.join(FRAGMENTS_DIRNAME, f'{name}.json')
        self.add_input_file(
            filename=filename,
            work_dir_target=f'{step.path}/{FRAGMENT_FILENAME}',
        )
        self.fragment_filenames.append(filename)
