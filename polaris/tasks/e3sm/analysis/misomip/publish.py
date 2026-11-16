import os

from polaris.analysis.publish_step import PublishStep
from polaris.analysis.site import INDEX_FILENAME

#: The suffix of the name of a run's health page, after the kind of run
HEALTH_SUFFIX = '_run_health'

#: The labels of the kinds of run in the bar of links
KIND_LABELS = {'e3sm': 'E3SM', 'standalone': 'standalone'}


class MisomipPublish(PublishStep):
    """
    The step that publishes one MISOMIP analysis task's products, under
    ``<output_path>/<relative_path>``

    Attributes
    ----------
    relative_path : str
        Where the task's gallery goes within the output path, such as
        ``misomip-o4km-li1km/ocean0``

    missing : str
        The error when the task has nothing to publish, which names the
        config options it needs

    title : str or None
        The heading of every page, the run's name, such as ``Ocean3``, or
        ``None`` for the framework's default
    """

    def __init__(
        self,
        component,
        subdir,
        product_steps,
        relative_path,
        missing,
        title=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        product_steps : list of polaris.analysis.product_step.ProductStep
            The steps whose products are published

        relative_path : str
            Where the task's gallery goes within the output path

        missing : str
            The error when the task has nothing to publish

        title : str, optional
            The heading of every page, the run's name
        """
        super().__init__(
            component=component,
            subdir=subdir,
            product_steps=product_steps,
            section='misomip_analysis',
        )
        self.relative_path = relative_path
        self.missing = missing
        self.title = title

    def setup(self):
        """
        Make it an error to set up a task with nothing to publish
        """
        super().setup()
        if not self.fragment_filenames:
            raise ValueError(self.missing)

    def output_path(self):
        """
        Get the directory this task's gallery is published into

        Returns
        -------
        output_path : str
            The task's directory under ``[misomip_analysis] output_path``
        """
        return os.path.join(super().output_path(), self.relative_path)

    def site_title(self):
        """
        Get the heading of every page, the run's name

        Returns
        -------
        title : str or None
            The run's name, or ``None`` for the framework's default
        """
        return self.title

    def site_links(self, pages):
        """
        Get the bar of links on every page: the summary, the gallery, the
        run health and the provenance, and the page of all runs if
        ``[misomip_analysis] all_runs_href`` gives it

        Parameters
        ----------
        pages : list of dict
            The pages published beside the galleries

        Returns
        -------
        links : list of tuple
            The links, each ``(text, href)``
        """
        all_runs = self.config.get(
            'misomip_analysis', 'all_runs_href', fallback=''
        ).strip()
        return get_site_links(pages, all_runs)

    def site_home(self, pages):
        """
        Get the site's home, the summary if there is one

        Parameters
        ----------
        pages : list of dict
            The pages published beside the galleries

        Returns
        -------
        home : str or None
            ``summary`` or ``None``
        """
        names = [page['name'] for page in pages]
        return 'summary' if 'summary' in names else None


def get_site_links(pages, all_runs=''):
    """
    Get the bar of links on every page of a MISOMIP analysis, in a fixed
    order, with the same labels for every run

    Parameters
    ----------
    pages : list of dict
        The pages published beside the galleries, each with its ``name``,
        ``title`` and ``href``

    all_runs : str, optional
        The page of all runs, relative to the root of the staging tree or a
        full URL, or empty for none

    Returns
    -------
    links : list of tuple
        The links, each ``(text, href)``
    """
    hrefs = {page['name']: page['href'] for page in pages}
    links = []
    if 'summary' in hrefs:
        links.append(('Summary', hrefs.pop('summary')))
    links.append(('Gallery', INDEX_FILENAME))
    health = [name for name in hrefs if name.endswith(HEALTH_SUFFIX)]
    for name in health:
        text = 'Run health'
        if len(health) > 1:
            kind = name[: -len(HEALTH_SUFFIX)]
            text = f'{text} ({KIND_LABELS.get(kind, kind)})'
        links.append((text, hrefs.pop(name)))
    if 'provenance' in hrefs:
        links.append(('Provenance', hrefs.pop('provenance')))
    titles = {page['name']: page['title'] for page in pages}
    links.extend((titles[name], href) for name, href in hrefs.items())
    if all_runs:
        links.append(('All runs', all_runs))
    return links
