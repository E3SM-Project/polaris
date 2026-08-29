import os

from PIL import Image

#: The subdirectory of the staging tree holding the thumbnails
THUMBNAILS_DIRNAME = 'thumbnails'

#: The default bounding box, in pixels, a thumbnail is scaled to fit inside
DEFAULT_SIZE = (320, 240)

#: The default image format for thumbnails
DEFAULT_FORMAT = 'jpeg'

#: The default compression quality for thumbnails
DEFAULT_QUALITY = 75

_SUFFIXES = {'jpeg': '.jpg', 'webp': '.webp'}


def thumbnail_name(basename, image_format=DEFAULT_FORMAT):
    """
    Get the name of the thumbnail for a published file

    Parameters
    ----------
    basename : str
        The name the plot is published under

    image_format : {'jpeg', 'webp'}, optional
        The format the thumbnail is written in

    Returns
    -------
    name : str
        The name of the thumbnail
    """
    suffix = _suffix(image_format)
    return f'{os.path.splitext(basename)[0]}{suffix}'


def image_size(filename):
    """
    Get the size of an image in pixels

    Parameters
    ----------
    filename : str
        The image to measure

    Returns
    -------
    width : int
        The width in pixels

    height : int
        The height in pixels
    """
    with Image.open(filename) as image:
        return image.size


def make_thumbnail(
    plot_filename,
    thumbnail_filename,
    size=DEFAULT_SIZE,
    image_format=DEFAULT_FORMAT,
    quality=DEFAULT_QUALITY,
):
    """
    Render the thumbnail for one plot, unless it is already up to date

    The plot is flattened onto white before being scaled, because the plots
    carry an alpha channel and JPEG has no transparency to put it in --
    without this the background comes out black.

    The thumbnail is scaled to fit inside ``size`` in *both* dimensions
    rather than to a fixed width.  A width rule charges the most for the
    tallest plots, which are the ones a reader least needs at full size: a
    stack of time series is three times the pixels of a map at the same
    width, and does not sit in a grid beside it.

    Parameters
    ----------
    plot_filename : str
        The plot to render, normally the published symlink

    thumbnail_filename : str
        Where to write the thumbnail

    size : tuple of int, optional
        The bounding box in pixels, as (width, height)

    image_format : {'jpeg', 'webp'}, optional
        The format to write.  ``webp`` is between a third and a half smaller
        at the same quality and every current browser reads it.

    quality : int, optional
        The compression quality, from 1 to 100

    Returns
    -------
    rendered : bool
        Whether the thumbnail was rendered.  It is left alone when it is
        already newer than its plot, so that adding one product to an
        existing analysis costs one thumbnail rather than all of them.
    """
    suffix = _suffix(image_format)
    if os.path.splitext(thumbnail_filename)[1] != suffix:
        raise ValueError(
            f'A {image_format} thumbnail must end in "{suffix}", but '
            f'"{thumbnail_filename}" does not.'
        )

    if _is_up_to_date(plot_filename, thumbnail_filename):
        return False

    with Image.open(plot_filename) as image:
        flattened = _flatten_onto_white(image)
    flattened.thumbnail(size, Image.Resampling.LANCZOS)
    os.makedirs(os.path.dirname(thumbnail_filename) or '.', exist_ok=True)
    flattened.save(thumbnail_filename, image_format.upper(), quality=quality)
    return True


def _suffix(image_format):
    """The file suffix a thumbnail format is written with"""
    if image_format not in _SUFFIXES:
        raise ValueError(
            f'Unsupported thumbnail format "{image_format}".  The formats '
            f'that can be written are: {", ".join(sorted(_SUFFIXES))}.'
        )
    return _SUFFIXES[image_format]


def _flatten_onto_white(image):
    """Composite any transparency onto white, since JPEG has none"""
    if image.mode not in ('RGBA', 'LA', 'P'):
        return image.convert('RGB')
    image = image.convert('RGBA')
    background = Image.new('RGB', image.size, 'white')
    background.paste(image, mask=image.split()[-1])
    return background


def _is_up_to_date(plot_filename, thumbnail_filename):
    """Whether the thumbnail is at least as new as the plot it came from"""
    if not os.path.exists(thumbnail_filename):
        return False
    # getmtime() follows the symlink, so this is the plot's own time
    return os.path.getmtime(thumbnail_filename) >= os.path.getmtime(
        plot_filename
    )
