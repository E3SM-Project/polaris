import os
from datetime import datetime

from jinja2 import Environment, PackageLoader, select_autoescape

from polaris.analysis.manifest import range_key
from polaris.provenance import get_summary

#: The landing page at the root of the staging tree
INDEX_FILENAME = 'index.html'

#: The subdirectory of the staging tree holding the gallery pages
GALLERIES_DIRNAME = 'galleries'


def generate_site(published, output_path, simulation_name, provenance=None):
    """
    Generate the static site over the products that have been published

    The site is a landing page of gallery groups, plus one page of thumbnails
    per gallery.  It is rendered from the merged manifest alone, so that a
    facet added later, a richer presentation, or a different visual design
    costs nothing anywhere else: no step, no manifest fragment already
    written, and no published path has to change.

    The pages have their CSS inlined and no JavaScript, so a page costs one
    request and its images, and works the same from a local filesystem and
    from a web portal.

    Parameters
    ----------
    published : list of dict
        The merged manifest, as :py:func:`~polaris.analysis.publish.publish`
        returned it

    output_path : str
        The root of the staging tree, where the pages are written

    simulation_name : str
        The name of the simulation that was analyzed, shown on every page

    provenance : dict, optional
        Labels and values recording what produced the results, shown in the
        footer of every page.  By default, the provenance of the Polaris that
        is running, from :py:func:`polaris.provenance.get_summary`.

    Returns
    -------
    filenames : list of str
        The pages that were written, the landing page first
    """
    if provenance is None:
        provenance = get_summary()
    provenance = dict(provenance)
    provenance['generated'] = datetime.now().isoformat(timespec='seconds')

    groups = _build_groups(published)
    environment = Environment(
        loader=PackageLoader('polaris.analysis', 'templates'),
        autoescape=select_autoescape(default_for_string=True, default=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    shared = {
        'title': f'Analysis of {simulation_name}',
        'provenance': list(provenance.items()),
    }

    filenames = [
        _render(
            environment=environment,
            template_name='index.template',
            filename=os.path.join(output_path, INDEX_FILENAME),
            page_title=f'Analysis of {simulation_name}',
            subtitle=_index_subtitle(published),
            groups=groups,
            prefix='',
            **shared,
        )
    ]

    galleries_path = os.path.join(output_path, GALLERIES_DIRNAME)
    os.makedirs(galleries_path, exist_ok=True)
    for group in groups:
        for gallery in group['galleries']:
            filenames.append(
                _render(
                    environment=environment,
                    template_name='gallery.template',
                    filename=os.path.join(galleries_path, gallery['filename']),
                    page_title=f'{simulation_name}: {gallery["title"]}',
                    subtitle=_gallery_subtitle(group, gallery),
                    index_href=f'../{INDEX_FILENAME}',
                    gallery=gallery,
                    prefix='../',
                    **shared,
                )
            )
    return filenames


def gallery_filename(group, gallery, key=None):
    """
    Get the name of the page holding one gallery

    As with a published product, the name is the facets in a fixed order, so
    that two date ranges of the same gallery coexist.

    Parameters
    ----------
    group : str
        The product group the gallery belongs to

    gallery : str
        The gallery within that group

    key : str, optional
        The zero-padded range of years the gallery covers, if it covers one

    Returns
    -------
    filename : str
        The name of the page within the galleries directory
    """
    parts = [group, gallery]
    if key is not None:
        parts.append(key)
    return f'{"_".join(parts)}.html'


def _build_groups(published):
    """Gather the published products into gallery groups and galleries"""
    groups: dict = {}
    for entry in published:
        key = range_key(entry)
        group_key = (entry['group'], key)
        group = groups.setdefault(
            group_key,
            {'title': _group_title(entry['group'], key), 'galleries': {}},
        )
        gallery = group['galleries'].setdefault(
            entry['gallery'],
            {
                'title': _humanize(entry['gallery']),
                'filename': gallery_filename(
                    entry['group'], entry['gallery'], key
                ),
                'products': [],
            },
        )
        gallery['products'].append(_product(entry))

    # dictionaries keep the order products were published in, and that order
    # is meaning: a gallery reads ANN, DJF, ... because the step plotted them
    # in that order
    return [
        {
            'title': group['title'],
            'galleries': [
                _gallery_summary(gallery)
                for gallery in group['galleries'].values()
            ],
        }
        for group in groups.values()
    ]


def _gallery_summary(gallery):
    """Add what the landing page shows for a gallery to the gallery itself"""
    summary = dict(gallery)
    summary['count'] = len(gallery['products'])
    summary['href'] = f'{GALLERIES_DIRNAME}/{gallery["filename"]}'
    # the gallery is represented by its first product, which is deterministic
    # because order is preserved, so the reader chooses a gallery by looking
    # rather than by reading names
    summary['representative'] = gallery['products'][0]
    return summary


def _product(entry):
    """What a gallery page shows for one product, relative to the tree root"""
    return {
        'title': entry['title'],
        'plot': entry['plot'],
        'data': entry.get('data'),
        'thumbnail': entry['thumbnail'],
        'thumbnail_width': entry['thumbnail_width'],
        'thumbnail_height': entry['thumbnail_height'],
    }


def _group_title(group, key):
    """The heading a gallery group appears under on the landing page"""
    title = _humanize(group)
    if key is None:
        return title
    return f'{title}, years {key}'


def _humanize(name):
    """A facet as it is written on a page rather than in a file name"""
    words = name.replace('_', ' ').strip()
    if not words:
        return name
    return words[0].upper() + words[1:]


def _index_subtitle(published):
    """The simulation's date ranges and how much was published"""
    parts = [_count(len(published), 'product')]
    keys = list(dict.fromkeys(range_key(entry) for entry in published))
    keys = [key for key in keys if key is not None]
    if keys:
        parts.append(f'years {", ".join(keys)}')
    return ' · '.join(parts)


def _gallery_subtitle(group, gallery):
    """The group a gallery belongs to and how many plots it holds"""
    return f'{group["title"]} · {_count(gallery["count"], "plot")}'


def _count(number, noun):
    """A count of something, with the noun made plural if it needs to be"""
    return f'{number} {noun}' if number == 1 else f'{number} {noun}s'


def _render(environment, template_name, filename, **context):
    """Render one page and write it"""
    template = environment.get_template(template_name)
    with open(filename, 'w') as out:
        out.write(template.render(**context))
        out.write('\n')
    return filename
