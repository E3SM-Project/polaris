import json
import os

from polaris.analysis.manifest import FRAGMENT_FILENAME, read_fragment

#: The subdirectory of the staging tree holding the published products
PLOTS_DIRNAME = 'plots'

#: The merged manifest at the root of the staging tree
MERGED_FILENAME = 'manifest.json'


def find_fragments(work_dir):
    """
    Find the manifest fragments under a work directory

    Parameters
    ----------
    work_dir : str
        The directory to search, normally the base work directory of the
        suite that was run

    Returns
    -------
    filenames : list of str
        The fragments found, sorted by path so that a publish is
        reproducible
    """
    filenames = []
    for root, _, files in os.walk(work_dir):
        if FRAGMENT_FILENAME in files:
            filenames.append(os.path.join(root, FRAGMENT_FILENAME))
    return sorted(filenames)


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
    range_key = _range_key(product)
    if range_key is not None:
        parts.append(range_key)
    return f'{"_".join(parts)}{suffix}'


def publish(fragment_filenames, output_path, logger=None):
    """
    Publish every product the fragments describe into the staging tree

    Products are published by symlink from the step that owns them, so that
    each file has exactly one owner, Polaris's output checking continues to
    work, and the staging tree is a view rather than a second source of
    truth.

    Parameters
    ----------
    fragment_filenames : list of str
        The manifest fragments to publish, as found by
        :py:func:`~polaris.analysis.publish.find_fragments`

    output_path : str
        The root of the staging tree

    logger : logging.Logger, optional
        A logger for reporting what was published and what was missing

    Returns
    -------
    published : list of dict
        One entry per published product, as written to the merged manifest

    missing : list of str
        The paths named by a fragment that are not on disk.  These are
        reported rather than silently omitted, and do not appear in the
        merged manifest, which is what defines the published set.
    """
    plots_path = os.path.join(output_path, PLOTS_DIRNAME)
    os.makedirs(plots_path, exist_ok=True)

    published: list[dict] = []
    missing: list[str] = []
    for fragment_filename in fragment_filenames:
        manifest = read_fragment(fragment_filename)
        step_path = os.path.dirname(os.path.abspath(fragment_filename))
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

    _report(published, missing, logger)
    write_merged_manifest(published, output_path)
    return published, missing


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


def _range_key(product):
    """The zero-padded range of years, if the product covers one"""
    start = product.facets.get('start_year')
    end = product.facets.get('end_year')
    if start is None or end is None:
        return None
    return f'{int(start):04d}-{int(end):04d}'


def _report(published, missing, logger):
    """Say what was published, and name anything that was not"""
    if logger is None:
        return
    logger.info(f'published {len(published)} products')
    if missing:
        logger.warning(
            f'{len(missing)} products were described by a manifest but their '
            f'files are not on disk, so they were not published:'
        )
        for source in missing:
            logger.warning(f'  {source}')
