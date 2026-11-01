import glob
import importlib.resources as imp_res
import os
import re
from copy import deepcopy
from typing import NamedTuple

from jinja2 import Template
from lxml import etree

#: The fields of an MPAS filename template that this module can match, and
#: the name and pattern of each
_TEMPLATE_FIELDS = {
    '$Y': ('year', r'\d{4,}'),
    '$M': ('month', r'\d{2}'),
    '$D': ('day', r'\d{2}'),
    '$h': ('hour', r'\d{2}'),
    '$m': ('minute', r'\d{2}'),
    '$s': ('second', r'\d{2}'),
    '$S': ('seconds_of_day', r'\d{5}'),
}


class StreamFile(NamedTuple):
    """
    A file a stream wrote, and the date its name gives

    Attributes
    ----------
    path : str
        The absolute path to the file

    year, month, day : int
        The date in the file's name, with month and day 1 if the name has
        none

    seconds : int
        The seconds since midnight in the file's name, 0 if it has none
    """

    path: str
    year: int
    month: int
    day: int
    seconds: int


def read(package, streams_filename, tree=None, replacements=None):
    """
    Parse the given streams file

    Parameters
    ----------
    package : Package
        The package name or module object that contains the streams file

    streams_filename : str
        The name of the streams file to read from

    tree : lxml.etree, optional
        An existing set of streams to add to or modify

    replacements : dict, optional
        A dictionary of replacements, in which case ``streams_filename`` is
        assumed to be a Jinja2 template to be rendered with these replacements

    Returns
    -------
    tree : lxml.etree
        A tree of XML data describing MPAS i/o streams with the content from
        the given streams file
    """
    text = imp_res.files(package).joinpath(streams_filename).read_text()
    if replacements is not None:
        template = Template(text)
        text = template.render(**replacements)

    new_tree = etree.fromstring(text)

    tree = update_tree(tree, new_tree)

    return tree


def read_file(filename):
    """
    Parse a streams file at a path, such as the ``streams.ocean`` that a run
    of MPAS-Ocean read

    Parameters
    ----------
    filename : str
        The path to the streams file

    Returns
    -------
    tree : lxml.etree
        A tree of XML data describing the run's i/o streams
    """
    return etree.parse(filename).getroot()


def get_stream(tree, name):
    """
    Get a stream, mutable or immutable, from a tree of streams

    Parameters
    ----------
    tree : lxml.etree
        A tree of XML data describing MPAS i/o streams

    name : str
        The name of the stream

    Returns
    -------
    stream : lxml.etree.Element
        The stream, whose attributes include ``filename_template``

    Raises
    ------
    ValueError
        If the tree has no stream of that name
    """
    names = []
    for tag in ['stream', 'immutable_stream']:
        for stream in tree.iter(tag):
            stream_name = stream.attrib.get('name')
            if stream_name == name:
                return stream
            names.append(stream_name)
    raise ValueError(
        f'There is no stream named "{name}".  The streams are: '
        f'{", ".join(sorted(names))}'
    )


def find_stream_files(filename_template, directories):
    """
    Find the files that a stream's filename template matches, and the date
    each was named for

    The date fields ``$Y``, ``$M``, ``$D``, ``$h``, ``$m``, ``$s`` and ``$S``
    may appear in the template, each at most once.  A file found in more
    than one directory is taken from the first, so the directories are given
    in order of preference.

    Parameters
    ----------
    filename_template : str
        The stream's ``filename_template``, which may include a relative
        directory

    directories : list of str
        The directories to search

    Returns
    -------
    stream_files : list of polaris.streams.StreamFile
        The files found, in order of their dates
    """
    pattern, regex = _template_to_patterns(filename_template)
    found = dict()
    for directory in directories:
        for path in glob.glob(os.path.join(directory, pattern)):
            relative = os.path.relpath(path, directory)
            if relative in found:
                continue
            match = regex.fullmatch(relative)
            if match is None:
                continue
            found[relative] = _stream_file(os.path.abspath(path), match)
    return sorted(
        found.values(),
        key=lambda stream_file: (
            stream_file.year,
            stream_file.month,
            stream_file.day,
            stream_file.seconds,
        ),
    )


def write(streams, out_filename):
    """write the streams XML data to the file"""

    with open(out_filename, 'w') as stream_file:
        stream_file.write('<streams>\n')

        # Write out all immutable streams first
        for stream in streams.findall('immutable_stream'):
            stream_name = stream.attrib['name']

            stream_file.write('\n')
            stream_file.write(f'<immutable_stream name="{stream_name}"')
            # Process all attributes on the stream
            for attr, val in stream.attrib.items():
                if attr.strip() != 'name':
                    stream_file.write(f'\n                  {attr}="{val}"')

            stream_file.write('/>\n')

        # Write out all immutable streams
        for stream in streams.findall('stream'):
            stream_name = stream.attrib['name']

            stream_file.write('\n')
            stream_file.write(f'<stream name="{stream_name}"')

            # Process all attributes
            for attr, val in stream.attrib.items():
                if attr.strip() != 'name':
                    stream_file.write(f'\n        {attr}="{val}"')

            stream_file.write('>\n\n')

            # Write out all contents of the stream
            for tag in ['stream', 'var_struct', 'var_array', 'var']:
                for child in stream.findall(tag):
                    child_name = child.attrib['name']
                    if tag == 'stream' and child_name == stream_name:
                        # don't include the stream itself
                        continue
                    if 'packages' in child.attrib.keys():
                        package_name = child.attrib['packages']
                        entry = (
                            f'    <{tag} name="{child_name}" '
                            f'packages="{package_name}"/>\n'
                        )
                    else:
                        entry = f'    <{tag} name="{child_name}"/>\n'
                    stream_file.write(entry)

            stream_file.write('</stream>\n')

        stream_file.write('\n')
        stream_file.write('</streams>\n')


def update_defaults(new_child, defaults):
    """
    Update a stream or its children (sub-stream, var, etc.) starting from the
    defaults or add it if it's new.
    """
    if 'name' not in new_child.attrib:
        return

    name = new_child.attrib['name']
    found = False
    for child in defaults:
        if child.attrib['name'] == name:
            found = True
            if child.tag != new_child.tag:
                raise ValueError(
                    f'Trying to update stream "{name}" with '
                    f'inconsistent tags {child.tag} vs. '
                    f'{new_child.tag}.'
                )

            # copy the attributes
            for attr, value in new_child.attrib.items():
                child.attrib[attr] = value

            if len(new_child) > 0:
                # we don't want default grandchildren
                for grandchild in child:
                    child.remove(grandchild)

            # copy or add the grandchildren's contents
            for new_grandchild in new_child:
                update_defaults(new_grandchild, child)

    if not found:
        # add a deep copy of the element
        defaults.append(deepcopy(new_child))


def update_tree(tree, new_tree):
    """
    Parse the given streams file

    Parameters
    ----------
    tree : lxml.etree
        An existing set of streams to add to or modify

    new_tree : lxml.etree
        A new set of streams to add or modify

    Returns
    -------
    tree : lxml.etree
        A tree of XML data describing MPAS i/o streams with the content from
        the given streams file
    """

    if tree is None:
        tree = new_tree
    else:
        streams = next(tree.iter('streams'))
        new_streams = next(new_tree.iter('streams'))

        for new_stream in new_streams:
            _update_element(new_stream, streams)

    return tree


def _update_element(new_child, elements):
    """
    add the new child/grandchildren or add/update attributes if they exist
    """
    if 'name' not in new_child.attrib:
        return

    name = new_child.attrib['name']
    found = False
    for child in elements:
        if child.attrib['name'] == name:
            found = True
            if child.tag != new_child.tag:
                raise ValueError(
                    f'Trying to update stream "{name}" with '
                    f'inconsistent tags {child.tag} vs. '
                    f'{new_child.tag}.'
                )

            # copy the attributes
            for attr, value in new_child.attrib.items():
                child.attrib[attr] = value

            # copy or add the grandchildren's contents
            for new_grandchild in new_child:
                _update_element(new_grandchild, child)

    if not found:
        # add a deep copy of the element
        elements.append(deepcopy(new_child))


def set_default_io_type(tree, io_type='pnetcdf,cdf5'):
    """
    Set io_type attribute for all <stream> and <immutable_stream>
    elements if not already set, except for immutable_stream with name 'mesh'.
    """
    streams = next(tree.iter('streams'))
    all_streams = streams.findall('stream') + streams.findall(
        'immutable_stream'
    )
    for stream in all_streams:
        stream_type = stream.attrib.get('type')
        if 'io_type' not in stream.attrib and 'output' in stream_type:
            stream.attrib['io_type'] = io_type


def _template_to_patterns(filename_template):
    """
    Make a glob pattern and a regular expression from a filename template
    """
    pieces = re.split(r'(\$[A-Za-z])', filename_template)
    glob_pattern = ''
    regex = ''
    seen = set()
    for piece in pieces:
        if piece.startswith('$') and len(piece) == 2:
            if piece not in _TEMPLATE_FIELDS:
                raise ValueError(
                    f'The filename template "{filename_template}" has the '
                    f'field {piece}, which cannot be matched.  The fields '
                    f'that can are {", ".join(_TEMPLATE_FIELDS)}.'
                )
            if piece in seen:
                raise ValueError(
                    f'The filename template "{filename_template}" has the '
                    f'field {piece} more than once.'
                )
            seen.add(piece)
            name, field_regex = _TEMPLATE_FIELDS[piece]
            glob_pattern += '*'
            regex += f'(?P<{name}>{field_regex})'
        else:
            glob_pattern += glob.escape(piece)
            regex += re.escape(piece)
    return glob_pattern, re.compile(regex)


def _stream_file(path, match):
    """
    Make a stream file from the path and the match of its name
    """
    fields = match.groupdict()
    seconds = int(fields.get('seconds_of_day') or 0)
    seconds += 3600 * int(fields.get('hour') or 0)
    seconds += 60 * int(fields.get('minute') or 0)
    seconds += int(fields.get('second') or 0)
    return StreamFile(
        path=path,
        year=int(fields['year']) if 'year' in fields else 0,
        month=int(fields.get('month') or 1),
        day=int(fields.get('day') or 1),
        seconds=seconds,
    )
