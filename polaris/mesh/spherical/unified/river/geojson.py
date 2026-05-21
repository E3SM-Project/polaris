import json


def read_geojson(filename):
    """
    Read a GeoJSON file into a dictionary.

    Parameters
    ----------
    filename : str
        The path to the GeoJSON file

    Returns
    -------
    feature_collection : dict
        The GeoJSON feature collection as a dictionary
    """
    with open(filename, 'r', encoding='utf-8') as infile:
        return json.load(infile)


def write_geojson(feature_collection, filename):
    """
    Write a GeoJSON feature collection.

    Parameters
    ----------
    feature_collection : dict
        The GeoJSON feature collection as a dictionary

    filename : str
        The path to the output GeoJSON file
    """
    with open(filename, 'w', encoding='utf-8') as outfile:
        json.dump(feature_collection, outfile, indent=2, sort_keys=True)
