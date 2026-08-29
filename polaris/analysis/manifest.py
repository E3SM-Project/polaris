import json
import os

FRAGMENT_FILENAME = 'manifest.json'

#: The keys a product always has, in the order they are written.  Everything
#: else a step supplies is a facet, and is written after these.
_RESERVED = ('plot', 'data', 'group', 'gallery', 'title')


class Product:
    """
    One published product: a plot, the data behind it, and the facets that
    identify it

    Attributes
    ----------
    plot : str
        The name of the plot file, relative to the step's work directory

    data : str or None
        The name of the netCDF file holding what was plotted, relative to the
        step's work directory, or ``None`` for a product with no data file

    group : str
        The product group this belongs to, which becomes a gallery group in
        the published index

    gallery : str
        The gallery within that group

    title : str
        A one-line description, used as the caption under the thumbnail

    facets : dict
        Everything else that identifies the product --- field, season,
        vertical reduction, date range, and later region and observational
        reference.  These are caption and filter material; only ``group`` and
        ``gallery`` shape the index.
    """

    def __init__(self, plot, group, gallery, title, data=None, **facets):
        """
        Describe one product

        Parameters
        ----------
        plot : str
            The name of the plot file, relative to the step's work directory

        group : str
            The product group this belongs to

        gallery : str
            The gallery within that group

        title : str
            A one-line description, used as the caption

        data : str, optional
            The name of the netCDF file holding what was plotted

        facets
            Any other keys that identify the product
        """
        required = {
            'plot': plot,
            'group': group,
            'gallery': gallery,
            'title': title,
        }
        for name, value in required.items():
            if not value:
                raise ValueError(
                    f'A product needs a non-empty "{name}"; got {value!r}.'
                )
        overlap = sorted(set(facets) & set(_RESERVED))
        if overlap:
            raise ValueError(
                f'These facet names are reserved and cannot be reused: '
                f'{", ".join(overlap)}.'
            )
        self.plot = plot
        self.data = data
        self.group = group
        self.gallery = gallery
        self.title = title
        self.facets = dict(facets)

    def to_dict(self):
        """
        Get the product as a dictionary ready to be written to JSON

        Returns
        -------
        entry : dict
            The reserved keys first, in a fixed order, then the facets
        """
        entry = {
            'plot': self.plot,
            'data': self.data,
            'group': self.group,
            'gallery': self.gallery,
            'title': self.title,
        }
        entry.update(self.facets)
        return entry

    @staticmethod
    def from_dict(entry):
        """
        Build a product from a dictionary read back from JSON

        Parameters
        ----------
        entry : dict
            One entry of a manifest fragment's ``products`` list

        Returns
        -------
        product : polaris.analysis.manifest.Product
            The product the entry describes
        """
        entry = dict(entry)
        missing = [
            key
            for key in ('plot', 'group', 'gallery', 'title')
            if key not in entry
        ]
        if missing:
            raise ValueError(
                f'A manifest entry is missing {", ".join(missing)}: {entry!r}'
            )
        plot = entry.pop('plot')
        data = entry.pop('data', None)
        group = entry.pop('group')
        gallery = entry.pop('gallery')
        title = entry.pop('title')
        return Product(
            plot=plot,
            group=group,
            gallery=gallery,
            title=title,
            data=data,
            **entry,
        )


class Manifest:
    """
    The products one step made, written beside its outputs so that a collector
    can find them without knowing how the work was divided into steps

    Products keep the order they were added in.  That order is meaning: a
    gallery reads ANN, DJF, MAM, JJA, SON because that is the order the step
    plotted them in, so no sort key or season-ordering table has to exist.

    Attributes
    ----------
    step_name : str
        The name of the step that made these products, for reporting

    products : list of polaris.analysis.manifest.Product
        The products, in the order they were added
    """

    def __init__(self, step_name):
        """
        Create an empty manifest for a step

        Parameters
        ----------
        step_name : str
            The name of the step that will fill it
        """
        self.step_name = step_name
        self.products: list = []

    def add(self, plot, group, gallery, title, data=None, **facets):
        """
        Describe one product this step has just made

        Parameters
        ----------
        plot : str
            The name of the plot file, relative to the step's work directory

        group : str
            The product group this belongs to

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
        product = Product(
            plot=plot,
            group=group,
            gallery=gallery,
            title=title,
            data=data,
            **facets,
        )
        duplicate = [
            other for other in self.products if other.plot == product.plot
        ]
        if duplicate:
            raise ValueError(
                f'The step "{self.step_name}" described two products plotted '
                f'in "{product.plot}".  Each plot is one product.'
            )
        self.products.append(product)
        return product

    def write(self, path):
        """
        Write the fragment describing everything this step made

        Parameters
        ----------
        path : str
            The directory to write ``manifest.json`` into, normally the step's
            work directory

        Returns
        -------
        filename : str
            The path of the fragment that was written
        """
        filename = os.path.join(path, FRAGMENT_FILENAME)
        contents = {
            'step': self.step_name,
            'products': [product.to_dict() for product in self.products],
        }
        with open(filename, 'w') as out:
            json.dump(contents, out, indent=2)
            out.write('\n')
        return filename


def read_fragment(filename):
    """
    Read one manifest fragment written by a step

    Parameters
    ----------
    filename : str
        The path of the fragment, or of the directory containing it

    Returns
    -------
    manifest : polaris.analysis.manifest.Manifest
        The step's manifest, with its products in the order they were written
    """
    if os.path.isdir(filename):
        filename = os.path.join(filename, FRAGMENT_FILENAME)
    with open(filename) as data:
        contents = json.load(data)
    for key in ('step', 'products'):
        if key not in contents:
            raise ValueError(
                f'The manifest fragment {filename} has no "{key}".'
            )
    manifest = Manifest(step_name=contents['step'])
    for entry in contents['products']:
        product = Product.from_dict(entry)
        manifest.add(
            plot=product.plot,
            group=product.group,
            gallery=product.gallery,
            title=product.title,
            data=product.data,
            **product.facets,
        )
    return manifest
