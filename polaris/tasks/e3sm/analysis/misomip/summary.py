import os

from polaris.analysis.manifest import FRAGMENT_FILENAME, read_fragment
from polaris.analysis.page import PageStep
from polaris.analysis.publish import PLOTS_DIRNAME, published_basename

#: The link to the captions file in the step's work directory
CAPTIONS_FILENAME = 'captions.txt'

#: The subdirectory the product steps' fragments are linked into
FRAGMENTS_DIRNAME = 'fragments'

#: What separates the cells of a table's row in a captions file
CELL_SEPARATOR = ' ; '


class SummaryPage(PageStep):
    """
    A step that makes a summary page of a run beside its galleries, from a
    captions file someone writes for the run: notes, tables and chosen
    plots, each with a title and a caption

    Each line of the captions file is one of these, with blank lines
    ignored:

    ``NOTE|heading|text``
        A paragraph, under a new heading, or under the one before if the
        heading is ``-``.  The text may be empty, for a heading alone.

    ``TABLE|caption|cell ; cell ; ...``
        A table under the heading before, with a caption and a row of
        column headings

    ``ROW|cell ; cell ; ...``
        A row of the table before

    ``LINK|text|href``
        A link under the heading before, or at the top of the page before
        any heading, with ``href`` relative to the page

    ``plot|title|caption``
        A plot the task publishes, under its own heading.  The plot is
        named as it is in the ``plots`` directory of the published tree.

    Attributes
    ----------
    captions : str
        The captions file

    fragment_filenames : list of str
        The product steps' manifest fragments, as local paths within this
        step's work directory
    """

    def __init__(self, component, subdir, product_steps, captions):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        product_steps : list of polaris.analysis.product_step.ProductStep
            The steps whose plots the page may show

        captions : str
            The captions file
        """
        super().__init__(
            component=component,
            name='summary',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
            page_name='summary',
            page_title='Summary',
        )
        self.captions = os.path.abspath(os.path.expanduser(captions))
        self.add_input_file(filename=CAPTIONS_FILENAME, target=self.captions)
        self.fragment_filenames: list = []
        for step in product_steps:
            if not getattr(step, 'makes_products', False):
                continue
            name = step.subdir.replace('/', '_')
            self.add_dependency(step, name=name)
            filename = os.path.join(FRAGMENTS_DIRNAME, f'{name}.json')
            self.add_input_file(
                filename=filename,
                work_dir_target=f'{step.path}/{FRAGMENT_FILENAME}',
            )
            self.fragment_filenames.append(filename)

    def run(self):
        """
        Write the page from the captions file
        """
        plots = get_published_plots(
            [self.work_path(name) for name in self.fragment_filenames]
        )
        lines = read_captions(self.work_path(CAPTIONS_FILENAME))
        add_captions(self.page, lines, plots)
        self.write_page()


def get_published_plots(fragment_filenames):
    """
    Get the plots that the fragments describe, by the names they are
    published under

    Parameters
    ----------
    fragment_filenames : list of str
        The manifest fragments of the steps that made the plots

    Returns
    -------
    plots : dict of str to str
        Each plot's link relative to a page beside the galleries, by its
        published name
    """
    plots = dict()
    for fragment_filename in fragment_filenames:
        step_path = os.path.dirname(os.path.realpath(fragment_filename))
        for product in read_fragment(fragment_filename).products:
            if not os.path.exists(os.path.join(step_path, product.plot)):
                # the publish step reports a plot that was never made
                continue
            name = published_basename(product, product.plot)
            plots[name] = f'../{PLOTS_DIRNAME}/{name}'
    return plots


def read_captions(filename):
    """
    Read a captions file

    Parameters
    ----------
    filename : str
        The captions file

    Returns
    -------
    lines : list of tuple
        Each line that is not blank, as its number and its fields: the
        kind and two more for most lines, the kind and one more for a row
    """
    lines = []
    with open(filename) as captions:
        for number, line in enumerate(captions, start=1):
            if not line.strip():
                continue
            kind, _, rest = line.rstrip('\n').partition('|')
            kind = kind.strip()
            if kind == 'ROW':
                fields = [rest.strip()]
            else:
                fields = [part.strip() for part in rest.split('|', 1)]
                if len(fields) != 2:
                    raise ValueError(
                        f'Line {number} of {filename} has too few fields: '
                        f'{line.strip()}'
                    )
            lines.append((number, kind, *fields))
    return lines


def add_captions(page, lines, plots):
    """
    Add sections to a page from the lines of a captions file

    Parameters
    ----------
    page : polaris.analysis.page.Page
        The page

    lines : list of tuple
        The lines, as :py:func:`read_captions` returns them

    plots : dict of str to str
        The plots the page may show, as
        :py:func:`get_published_plots` returns them
    """
    section = None
    for number, kind, *fields in lines:
        if kind == 'NOTE':
            heading, text = fields
            if heading != '-' or section is None:
                section = page.add_section(None if heading == '-' else heading)
            if text:
                section['paragraphs'].append(text)
        elif kind == 'TABLE':
            caption, columns = fields
            if section is None or section['table'] is not None:
                raise ValueError(
                    f'Line {number}: a table goes under a NOTE of its own.'
                )
            section['table'] = {
                'caption': caption,
                'columns': [
                    column.strip() for column in columns.split(CELL_SEPARATOR)
                ],
                'rows': [],
            }
        elif kind == 'ROW':
            table = None if section is None else section['table']
            if table is None:
                raise ValueError(f'Line {number}: a ROW follows a TABLE.')
            cells = fields[0].split(CELL_SEPARATOR)
            if len(cells) != len(table['columns']):
                raise ValueError(
                    f'Line {number}: the row has {len(cells)} cells but '
                    f'the table has {len(table["columns"])} columns.'
                )
            table['rows'].append(
                [{'value': cell.strip(), 'href': None} for cell in cells]
            )
        elif kind == 'LINK':
            text, href = fields
            if section is None:
                section = page.add_section(None)
            section['links'].append({'text': text, 'href': href})
        else:
            if kind not in plots:
                raise ValueError(
                    f'Line {number}: {kind} is not a plot the task '
                    f'publishes.  The plots are:\n  '
                    + '\n  '.join(sorted(plots))
                )
            title, caption = fields
            section = page.add_section(
                title, text=caption, figures=[(plots[kind], title)]
            )
            # notes, tables and links go under a NOTE, not a plot
            section = None
