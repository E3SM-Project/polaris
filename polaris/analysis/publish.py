import json
import os

from polaris.analysis.manifest import range_key, read_fragment
from polaris.analysis.thumbnail import (
    DEFAULT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
    THUMBNAILS_DIRNAME,
    image_size,
    make_thumbnail,
    thumbnail_name,
)

#: The subdirectory of the staging tree holding the published products
PLOTS_DIRNAME = 'plots'

#: The merged manifest at the root of the staging tree
MERGED_FILENAME = 'manifest.json'


def published_basename(product, filename):
    """
    Get the name one of a product's files is published under

    The name is the facets in a fixed order, so that it sorts usefully, greps
    usefully, and cannot collide between two date ranges.

    Parameters
    ----------
    product : polaris.analysis.manifest.Product
        The product the file belongs to

    filename : str
        The name of the file within the step's work directory

    Returns
    -------
    basename : str
        The name to publish it under
    """
    stem, suffix = os.path.splitext(os.path.basename(filename))
    parts = [product.group, stem]
    key = range_key(product.facets)
    if key is not None:
        parts.append(key)
    return f'{"_".join(parts)}{suffix}'


def publish(
    fragment_filenames,
    output_path,
    logger=None,
    thumbnail_size=DEFAULT_SIZE,
    thumbnail_format=DEFAULT_FORMAT,
    thumbnail_quality=DEFAULT_QUALITY,
):
    """
    Publish every product the fragments describe into the staging tree

    Products are published by symlink from the step that owns them, so that
    each file has exactly one owner, Polaris's output checking continues to
    work, and the staging tree is a view rather than a second source of
    truth.

    Parameters
    ----------
    fragment_filenames : list of str
        The manifest fragments to publish, one per step that makes products.
        Every such step writes one, empty if it made nothing, which is what
        lets a step declare them as inputs and have Polaris check them.  A
        fragment that is not on disk is nonetheless reported here rather than
        raising, so that this is usable on a list nothing has checked; the
        ``publish`` step does not rely on it, since a declared input that is
        missing stops it before it runs.

    output_path : str
        The root of the staging tree

    logger : logging.Logger, optional
        A logger for reporting what was published and what was missing

    thumbnail_size : tuple of int, optional
        The bounding box in pixels each thumbnail is scaled to fit inside

    thumbnail_format : {'jpeg', 'webp'}, optional
        The format thumbnails are written in

    thumbnail_quality : int, optional
        The compression quality of thumbnails, from 1 to 100

    Returns
    -------
    published : list of dict
        One entry per published product, as written to the merged manifest

    missing : list of str
        The paths that are not on disk: first the fragments that were named
        but never written, then the files a fragment named.  Both are
        reported rather than silently omitted, and neither appears in the
        merged manifest, which is what defines the published set.  A fragment
        that was never written is only worth a message, since whoever called
        this may not have had it checked; a fragment that promised a file
        that is not there is worth a warning.
    """
    plots_path = os.path.join(output_path, PLOTS_DIRNAME)
    thumbnails_path = os.path.join(output_path, THUMBNAILS_DIRNAME)
    os.makedirs(plots_path, exist_ok=True)
    os.makedirs(thumbnails_path, exist_ok=True)

    published: list[dict] = []
    unwritten: list[str] = []
    missing: list[str] = []
    for fragment_filename in fragment_filenames:
        if not os.path.exists(fragment_filename):
            unwritten.append(fragment_filename)
            continue
        manifest = read_fragment(fragment_filename)
        # a product is named relative to the step that wrote the fragment,
        # and the fragment is normally reached through a symlink into that
        # step, so the step's directory is the real one rather than the one
        # the link sits in
        step_path = os.path.dirname(os.path.realpath(fragment_filename))
        for product in manifest.products:
            entry = _publish_product(
                product=product,
                step_path=step_path,
                plots_path=plots_path,
                step_name=manifest.step_name,
                missing=missing,
            )
            if entry is not None:
                published.append(entry)

    rendered = _add_thumbnails(
        published=published,
        output_path=output_path,
        size=thumbnail_size,
        image_format=thumbnail_format,
        quality=thumbnail_quality,
    )

    _report(published, unwritten, missing, rendered, logger)
    write_merged_manifest(published, output_path)
    return published, unwritten + missing


def write_merged_manifest(published, output_path):
    """
    Write the merged manifest that defines the published set

    Parameters
    ----------
    published : list of dict
        The published products, in the order they were published

    output_path : str
        The root of the staging tree

    Returns
    -------
    filename : str
        The path of the manifest that was written
    """
    filename = os.path.join(output_path, MERGED_FILENAME)
    with open(filename, 'w') as out:
        json.dump({'products': published}, out, indent=2)
        out.write('\n')
    return filename


def _publish_product(product, step_path, plots_path, step_name, missing):
    """Symlink one product's files, or record it as missing"""
    sources = {'plot': product.plot}
    if product.data is not None:
        sources['data'] = product.data

    targets = {}
    for key, filename in sources.items():
        source = os.path.join(step_path, filename)
        if not os.path.exists(source):
            missing.append(source)
            return None
        targets[key] = (source, published_basename(product, filename))

    entry = product.to_dict()
    entry['step'] = step_name
    for key, (source, basename) in targets.items():
        _symlink(source, os.path.join(plots_path, basename))
        entry[key] = os.path.join(PLOTS_DIRNAME, basename)
    return entry


def _symlink(source, link_path):
    """Point link_path at source, replacing a link left by an earlier run"""
    if os.path.islink(link_path) or os.path.exists(link_path):
        os.remove(link_path)
    os.symlink(source, link_path)


def _add_thumbnails(published, output_path, size, image_format, quality):
    """Render a thumbnail for each published plot and record it"""
    rendered = 0
    for entry in published:
        basename = os.path.basename(entry['plot'])
        name = thumbnail_name(basename, image_format)
        filename = os.path.join(output_path, THUMBNAILS_DIRNAME, name)
        if make_thumbnail(
            plot_filename=os.path.join(output_path, entry['plot']),
            thumbnail_filename=filename,
            size=size,
            image_format=image_format,
            quality=quality,
        ):
            rendered += 1
        entry['thumbnail'] = os.path.join(THUMBNAILS_DIRNAME, name)
        # the generated page gives every image its own width and height, so
        # that lazy loading does not make the page reflow as they arrive
        width, height = image_size(filename)
        entry['thumbnail_width'] = width
        entry['thumbnail_height'] = height
    return rendered


def _report(published, unwritten, missing, rendered, logger):
    """Say what was published, and name anything that was not"""
    if logger is None:
        return
    logger.info(
        f'published {len(published)} products, rendering {rendered} thumbnails'
    )
    if unwritten:
        logger.info(
            f'{len(unwritten)} manifests were named but never written, so '
            f'nothing from them was published:'
        )
        for filename in unwritten:
            logger.info(f'  {filename}')
    if missing:
        logger.warning(
            f'{len(missing)} products were described by a manifest but their '
            f'files are not on disk, so they were not published:'
        )
        for source in missing:
            logger.warning(f'  {source}')
