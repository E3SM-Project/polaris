from polaris import Step
from polaris.analysis.manifest import FRAGMENT_FILENAME, Manifest


class ProductStep(Step):
    """
    A step that makes products for a published gallery

    Each product the step describes with :py:meth:`add_product` is written to
    a manifest fragment in the step's work directory, which a
    :py:class:`polaris.analysis.publish_step.PublishStep` reads.  A step that
    also derives from another kind of step lists this class first, as in
    ``class MyStep(ProductStep, OceanIOStep)``, so that both constructors
    run.

    Attributes
    ----------
    manifest : polaris.analysis.manifest.Manifest
        The products this step has described so far, written to
        ``manifest.json`` in the step's work directory as they are added.
        Steps add to it through :py:meth:`add_product` rather than directly.
    """

    #: Whether this step makes products for the published gallery, and so
    #: writes a manifest fragment describing them.  A step that only computes
    #: intermediate results for other steps to plot sets this to ``False``,
    #: which keeps the ``publish`` step from depending on it and from
    #: reporting the fragment it was never going to write.
    makes_products = True

    def __init__(self, *args, **kwargs):
        """
        Create the step

        Parameters
        ----------
        args, kwargs
            Arguments passed on to the constructor of the next step class
        """
        super().__init__(*args, **kwargs)
        # the step's work directory names whatever the product is keyed on,
        # so it is what tells two keys of one step apart in the merged
        # manifest
        self.manifest = Manifest(step_name=self.subdir)
        if self.makes_products:
            self.add_output_file(FRAGMENT_FILENAME)

    def runtime_setup(self):
        """
        Write the empty manifest fragment before the step runs

        The fragment is written here, and again by each
        :py:meth:`add_product` call, so that a step that makes products
        always leaves one behind: an empty product list until it has
        something to put in it.  Nothing is asked of the step author, because
        a rule that has to be remembered at the end of ``run()`` would be
        forgotten in exactly the step that made nothing --- which is the case
        that stops the ``publish`` step.

        Writing it again also clears out what a previous run of the step
        described, so a fragment never outlives the products it names.
        """
        super().runtime_setup()
        if self.makes_products:
            self._write_manifest()

    def add_product(self, plot, group, gallery, title, data=None, **facets):
        """
        Describe one product this step has just made, and update the fragment

        Parameters
        ----------
        plot : str
            The name of the plot file, relative to the step's work directory

        group : str
            The product group this belongs to, which becomes a gallery group

        gallery : str
            The gallery within that group

        title : str
            A one-line description, used as the caption

        data : str, optional
            The name of the netCDF file holding what was plotted

        facets
            Any other keys that identify the product

        Returns
        -------
        product : polaris.analysis.manifest.Product
            The product that was added
        """
        if not self.makes_products:
            raise ValueError(
                f'The step {self.name} sets makes_products = False, so it '
                f'writes no manifest fragment and cannot describe the '
                f'product plotted in "{plot}".'
            )
        product = self.manifest.add(
            plot=plot,
            group=group,
            gallery=gallery,
            title=title,
            data=data,
            **facets,
        )
        self._write_manifest()
        return product

    def _write_manifest(self):
        """Write the fragment describing what the step has made so far"""
        self.manifest.write(self.work_path())
