import json
import os
import shutil

from polaris import Step

#: The file in a page step's work directory that describes its page
PAGE_FILENAME = 'page.json'


class Page:
    """
    A page published beside the galleries, such as a run's provenance,
    described as sections of text, labeled values, tables and files, so
    that the publish step renders it in the gallery's style

    Attributes
    ----------
    name : str
        The page's directory within the staging tree, which is also its
        name in links

    title : str
        The page's heading and the text of the link to it in the footer of
        every gallery page

    sections : list of dict
        The sections, in order, as :py:meth:`add_section` makes them

    files : dict
        The name each file is published under within the page's directory,
        keyed by its path relative to the step's work directory
    """

    def __init__(self, name, title):
        """
        Create an empty page

        Parameters
        ----------
        name : str
            The page's directory within the staging tree

        title : str
            The page's heading and the text of the link to it
        """
        self.name = name
        self.title = title
        self.sections: list = []
        self.files: dict = {}

    def add_section(
        self, title, text=None, entries=None, table=None, code=None
    ):
        """
        Add a section to the page

        Parameters
        ----------
        title : str
            The section's heading

        text : str, optional
            A paragraph under the heading

        entries : list of tuple, optional
            Labeled values, each ``(label, value)`` or
            ``(label, value, href)``, where ``href`` is the value's link,
            relative to the page

        table : dict, optional
            A table, with ``columns``, a list of headings, and ``rows``, a
            list of rows of values, each value a string or a
            ``(value, href)`` pair

        code : str, optional
            Text shown as it is, such as the commands that set up a case

        Returns
        -------
        section : dict
            The section that was added
        """
        section = {'title': title, 'text': text, 'code': code}
        section['entries'] = [_entry(entry) for entry in entries or []]
        if table is not None:
            section['table'] = {
                'columns': list(table['columns']),
                'rows': [
                    [_cell(value) for value in row] for row in table['rows']
                ],
            }
        else:
            section['table'] = None
        self.sections.append(section)
        return section

    def add_file(self, filename, published_name=None):
        """
        Publish a file with the page, in the page's directory

        Parameters
        ----------
        filename : str
            The file's path relative to the step's work directory

        published_name : str, optional
            The name it is published under, by default its base name

        Returns
        -------
        href : str
            The file's link, relative to the page
        """
        if published_name is None:
            published_name = os.path.basename(filename)
        if published_name in self.files.values():
            raise ValueError(
                f'The page {self.name} already publishes a file named '
                f'{published_name}.'
            )
        self.files[filename] = published_name
        return published_name

    def write(self, work_dir):
        """
        Write the page's description in a step's work directory

        Parameters
        ----------
        work_dir : str
            The step's work directory

        Returns
        -------
        filename : str
            The description that was written
        """
        filename = os.path.join(work_dir, PAGE_FILENAME)
        with open(filename, 'w') as out:
            json.dump(self.to_dict(), out, indent=2)
            out.write('\n')
        return filename

    def to_dict(self):
        """
        Get the page's description

        Returns
        -------
        page : dict
            The page's ``name``, ``title``, ``sections`` and ``files``
        """
        return {
            'name': self.name,
            'title': self.title,
            'sections': self.sections,
            'files': self.files,
        }


class PageStep(Step):
    """
    A step that makes a page published beside the galleries

    The step fills in :py:attr:`page` as it runs and calls
    :py:meth:`write_page` at the end, and a
    :py:class:`polaris.analysis.publish_step.PublishStep` that lists it
    among its product steps publishes the page and links to it from the
    footer of every page.  A step that also derives from another kind of
    step lists this class first, as with
    :py:class:`polaris.analysis.product_step.ProductStep`.

    Attributes
    ----------
    page : polaris.analysis.page.Page
        The page the step makes
    """

    #: Whether this step makes a page, which is what the publish step looks
    #: for
    makes_page = True

    def __init__(self, *args, page_name, page_title, **kwargs):
        """
        Create the step

        Parameters
        ----------
        args, kwargs
            Arguments passed on to the constructor of the next step class

        page_name : str
            The page's directory within the staging tree

        page_title : str
            The page's heading and the text of the link to it
        """
        super().__init__(*args, **kwargs)
        self.page = Page(name=page_name, title=page_title)
        self.add_output_file(PAGE_FILENAME)

    def write_page(self):
        """Write the page's description in the step's work directory"""
        self.page.write(self.work_path())


def read_page(filename):
    """
    Read a page's description

    Parameters
    ----------
    filename : str
        The description, as :py:meth:`Page.write` wrote it

    Returns
    -------
    page : dict
        The page's ``name``, ``title``, ``sections`` and ``files``
    """
    with open(filename) as data:
        return json.load(data)


def publish_pages(page_filenames, output_path):
    """
    Copy each page's files into its directory in the staging tree

    Parameters
    ----------
    page_filenames : list of str
        The pages' descriptions, each in the work directory of the step
        that wrote it or linked to it

    output_path : str
        The root of the staging tree

    Returns
    -------
    pages : list of dict
        The pages' descriptions, each with ``href``, the page's link
        relative to the root of the staging tree, for
        :py:func:`polaris.analysis.site.generate_site` to render
    """
    pages = []
    names: set = set()
    for page_filename in page_filenames:
        page = read_page(page_filename)
        if page['name'] in names:
            raise ValueError(
                f'Two steps make a page named {page["name"]}, which would '
                f'be published in the same directory.'
            )
        names.add(page['name'])
        step_path = os.path.dirname(os.path.realpath(page_filename))
        page_path = os.path.join(output_path, page['name'])
        # files an earlier version of the page published, and no longer
        # does, would otherwise stay with nothing linking to them
        if os.path.isdir(page_path):
            shutil.rmtree(page_path)
        os.makedirs(page_path)
        for filename, published_name in page['files'].items():
            shutil.copyfile(
                os.path.join(step_path, filename),
                os.path.join(page_path, published_name),
            )
        page['href'] = f'{page["name"]}/index.html'
        pages.append(page)
    return pages


def _entry(entry):
    """A labeled value, with its link or ``None``"""
    if len(entry) == 2:
        label, value = entry
        href = None
    else:
        label, value, href = entry
    return {'label': label, 'value': str(value), 'href': href}


def _cell(value):
    """A table's value, with its link or ``None``"""
    if isinstance(value, (tuple, list)):
        text, href = value
        return {'value': str(text), 'href': href}
    return {'value': str(value), 'href': None}
