import argparse
import importlib.resources as imp_res
from collections import OrderedDict
from typing import Dict

from jinja2 import Template
from lxml import etree
from ruamel.yaml import YAML


class PolarisYaml:
    """
    A class for reading writing and combining config files in yaml format
    (e.g. as used in Omega).

    Attributes
    ----------
    configs : dict
        Nested dictionaries containing config options

    streams : dict
        Nested dictionaries containing data about streams

    streams_section : str
        The name of the streams section

    model : str
        The name of the E3SM component
    """

    def __init__(self):
        """
        Create a yaml config object
        """
        self.configs = dict()
        self.streams_section = 'streams'
        self.streams = dict()
        self.model = None

    @classmethod
    def read(cls, filename, package=None, replacements=None, model=None,
             streams_section='streams'):
        """
        Add config options from a yaml file

        Parameters
        ----------
        filename : str
            A template yaml config file

        package : str, optional
            The name of a package the filename is found in

        replacements : dict, optional
            A dictionary of replacements, which, if provided, is used to
            replace Jinja variables and the yaml file is assumed do be a Jinja
            template

        model : str, optional
            The name of the model to parse if the yaml file might have multiple
            models

        streams_section : str, optional
            The name of the streams section

        Returns
        -------
        yaml : polaris.yaml.PolarisYaml
            A yaml object read in from the given file (and optionally package)
        """
        # read the text from a file (possibly in a package)
        if package is not None:
            text = imp_res.files(package).joinpath(filename).read_text()
        else:
            with open(filename, 'r') as infile:
                text = infile.read()

        # if this is a jinja template, render the template with the
        # replacements
        if replacements is not None:
            template = Template(text)
            text = template.render(**replacements)

        yaml = cls()
        yaml.streams_section = streams_section
        yaml_data = YAML(typ='rt')
        configs = yaml_data.load(text)

        if model is None:
            keys = list(configs)
            if len(keys) > 1:
                raise ValueError(
                    f'Config yaml file contains unexpected sections: \n '
                    f'{keys[1:]}')
            model = keys[0]

        yaml.model = model
        yaml.streams = {}
        if model in configs:
            configs = configs[model]
            if streams_section in configs:
                yaml.streams = configs[streams_section]
                configs = dict(configs)
                configs.pop(streams_section)
        else:
            configs = {}

        yaml.configs = configs
        return yaml

    def update(self, configs=None, options=None, quiet=True):
        """
        Add config options from a dictionary

        Parameters
        ----------
        configs : dict, optional
            A nested dictionary of config sections, options and values

        options : dict, optional
            A flat dictionary of options and values

        quiet : bool, optional
            Whether or not to print the updated config options as they are
            replaced
        """
        if configs is not None:
            if self.model in configs:
                # we want one layer deeper
                configs = configs[self.model]
            _update_section(configs, self.configs, quiet)

        if options is not None:
            _update_options(options, self.configs, quiet)

    def write(self, filename):
        """
        Write config options to a yaml file

        Parameters
        ----------
        filename : str
            A yaml config file
        """
        yaml = YAML(typ='rt')
        configs = dict(self.configs)
        if self.streams:
            configs[self.streams_section] = self.streams

        model_configs = dict()
        model_configs[self.model] = configs

        with open(filename, 'w') as outfile:
            yaml.dump(model_configs, outfile)


def mpas_namelist_and_streams_to_yaml(model, namelist_template=None,
                                      namelist=None,
                                      streams=None):
    """
    Add config options from a yaml file

    Parameters
    ----------
    model : str
        The name of the model

    namelist_template : str
        An MPAS namelist template file

    namelist : str, optional
        An MPAS namelist file

    streams : str, optional
        An MPAS streams file

    Returns
    -------
    yaml : polaris.yaml.PolarisYaml
        A yaml object with the namelists and streams
    """
    yaml = PolarisYaml()
    yaml.model = model
    if namelist is not None:
        yaml.configs = _read_namelist(namelist_template, namelist)
    if streams is not None:
        yaml.streams = _streams_xml_to_dict(streams)

    return yaml


def main_mpas_to_yaml():
    parser = argparse.ArgumentParser(
        description='Convert a namelist and/or streams file to yaml')
    parser.add_argument("-n", "--namelist", dest="namelist",
                        required=False,
                        help="MPAS namelist file")
    parser.add_argument("-s", "--streams", dest="streams",
                        required=False,
                        help="MPAS streams file")
    parser.add_argument("-t", "--namelist_template", dest="namelist_template",
                        required=False,
                        help="MPAS namelist template file (with all namelist "
                             "options). For MPAS-Ocean, this will typically be"
                             " ${PATH_TO_MPASO}/default_inputs/"
                             "namelist.ocean.forward")
    parser.add_argument("-y", "--yaml", dest="yaml",
                        required=True,
                        help="Output yaml file")
    parser.add_argument("-m", "--model", dest="model", default='mpas-ocean',
                        help="Model name for the yaml")

    args = parser.parse_args()

    yaml = mpas_namelist_and_streams_to_yaml(
        model=args.model,
        namelist_template=args.namelist_template,
        namelist=args.namelist,
        streams=args.streams)

    yaml.write(args.yaml)


def yaml_to_mpas_streams(processed_registry_filename, yaml):
    """
    Add config options from a yaml file

    Parameters
    ----------
    processed_registry_filename : str
        The processed registry file, used to determine the types of variables
        each steam (since the yaml format doesn't supply that information).

    yaml : polaris.yaml.PolarisYaml
        A yaml object with the namelists and streams

    Returns
    -------
    tree : lxml.etree
        A tree of XML data describing MPAS i/o streams with the content from
        the streams in the yaml file
    """
    with open(processed_registry_filename, 'r') as reg_file:
        registry_string = reg_file.read()
    registry_string = registry_string.lstrip('\n')
    registry = etree.fromstring(registry_string)

    root = etree.Element('streams')
    for stream in yaml.streams:
        # find out if stream or immutable_stream
        tag = _get_stream_tag(registry, stream)
        attrs = dict(yaml.streams[stream])
        contents = None
        if 'contents' in attrs:
            contents = attrs.pop('contents')
        attrs['name'] = stream
        child = etree.SubElement(root, tag, attrib=attrs)
        if contents is not None:
            for var in contents:
                # find out what type it has
                tag = _get_var_tag(registry, var)
                etree.SubElement(child, tag, attrib=dict(name=var))

    tree = etree.ElementTree(element=root)
    return tree


def _update_section(src, dst, quiet, print_section=None):
    """
    Recursively update config options in a section of a config from a source
    section to the associate destination dictionary
    """
    for name in src:
        if isinstance(src[name], (dict, OrderedDict)):
            if print_section is not None:
                print_subsection = f'{print_section}: {name}'
            else:
                print_subsection = name
            if name not in dst:
                raise ValueError(
                    f'Attempting to modify config options to a '
                    f'nonexistent config\n'
                    f'(sub)section: {print_subsection}')
            # this is a subsection
            src_sub = src[name]
            dst_sub = dst[name]
            _update_section(src_sub, dst_sub, quiet, print_subsection)
        else:
            if name not in dst:
                raise ValueError(
                    f'Attempting to modify a nonexistent config '
                    f'options: {print_section}: {name}')
            if not quiet:
                print(f'  {print_section}: {name} = {src[name]}')
            dst[name] = src[name]


def _update_options(src, dst, quiet):
    """
    Update config options by searching in the destination nested dictionary
    """
    for name in src:
        success = _update_option(name, src[name], dst, quiet)
        if not success:
            raise ValueError(
                f'Attempting to modify a nonexistent config '
                f'options: {name}')


def _update_option(option, value, dst, quiet, print_section=None):
    """
    Recursively attempt to find and replace the value of the
    given option
    """
    for name in dst:
        if isinstance(dst[name], (dict, OrderedDict)):
            if print_section is not None:
                print_subsection = f'{print_section}: {name}'
            else:
                print_subsection = name
            success = _update_option(option, value, dst[name], quiet,
                                     print_subsection)
            if success:
                return True
        elif name == option:
            dst[name] = value
            if not quiet:
                print(f'  {print_section}: {name} = {value}')
            return True
    return False


def _read_namelist(namelist_template, namelist_filename):
    """ Read the defaults file """
    record_map = _read_namelist_template(namelist_template)

    with open(namelist_filename, 'r') as f:
        lines = f.readlines()

    namelist: Dict[str, Dict[str, int | float | bool | str]] = dict()
    for line in lines:
        _, opt, value = _read_namelist_line(line)
        if opt is not None and value is not None:
            record = record_map[opt]
            if record not in namelist:
                namelist[record] = dict()
            namelist[record][opt] = value

    return namelist


def _read_namelist_template(namelist_template):
    """ Read the defaults file """
    with open(namelist_template, 'r') as f:
        lines = f.readlines()

    record_map: Dict[str, str] = dict()
    record = None
    for line in lines:
        new_record, opt, _ = _read_namelist_line(line)
        if new_record is not None:
            record = new_record
        elif opt is not None and record is not None:
            record_map[opt] = record

    return record_map


def _read_namelist_line(line):
    record = None
    opt = None
    value: int | float | bool | str | None = None
    if '&' in line:
        record = line.strip('&').strip('\n').strip()
    elif '=' in line:
        opt, val = line.strip('\n').split('=')
        opt = opt.strip()
        str_value = \
            val.strip().strip('\"').strip('\'').strip()
        try:
            value = int(str_value)
        except ValueError:
            try:
                value = float(str_value)
            except ValueError:
                if str_value in ['true', '.true.']:
                    value = True
                elif str_value in ['false', '.false.']:
                    value = False
        if value is None:
            value = str_value

    return record, opt, value


def _streams_xml_to_dict(streams_filename):
    """ Convert a streams XML file to nested dictionaries """
    streams: Dict[str, Dict[str, str | list]] = dict()
    tree = etree.parse(streams_filename)
    xml_streams = next(tree.iter('streams'))
    for child in xml_streams:
        if child.tag not in ['stream', 'immutable_stream']:
            raise ValueError(f'Unexpected tag {child.tag} instead of stream or'
                             f'immutable stream')
        stream_name = child.attrib['name']
        streams[stream_name] = dict()
        for attr, value in child.attrib.items():
            if attr != 'name':
                streams[stream_name][attr] = value

        contents = list()
        for grandchild in child:
            if grandchild.tag == 'var':
                contents.append(grandchild.attrib['name'])
            elif grandchild.tag == 'var_struct':
                contents.append(grandchild.attrib['name'])
            elif grandchild.tag == 'var_array':
                contents.append(grandchild.attrib['name'])
            elif grandchild.tag == 'stream':
                contents.append(grandchild.attrib['name'])
            else:
                raise ValueError(f'Unexpected tag {grandchild.tag}')
        if len(contents) > 0:
            streams[stream_name]['contents'] = contents

    return streams


def _get_stream_tag(registry, stream):
    """ Get the xml tag, 'stream' or 'immutable_stream' for a given stream """
    streams = next(next(registry.iter('registry')).iter('streams'))
    # if we don't find the stream, it can't be an immutable stream
    tag = 'stream'
    for child in streams:
        if child.tag == 'stream' and child.attrib['name'] == stream:
            if 'immutable' in child.attrib and \
                    child.attrib['immutable'] == 'true':
                tag = 'immutable_stream'
            break
    return tag


def _get_var_tag(registry, variable):
    """
    Get the xml tag -- 'stream', 'var_struct', 'var_array' or 'var' -- for a
    variable
    """
    tag = None
    streams = next(next(registry.iter('registry')).iter('streams'))
    for child in streams:
        if child.tag == 'stream' and child.attrib['name'] == variable:
            return 'stream'

    tree = next(registry.iter('registry'))
    for child in tree:
        if child.tag == 'var_struct':
            if child.attrib['name'] == variable:
                return 'var_struct'

            for grandchild in child:
                if grandchild.tag in ['var_struct', 'var_array', 'var'] and \
                        grandchild.attrib['name'] == variable:
                    return grandchild.tag
                if grandchild.tag in ['var_struct', 'var_array']:
                    for greatgrand in grandchild:
                        if greatgrand.tag in ['var_array', 'var'] and \
                                greatgrand.attrib['name'] == variable:
                            return greatgrand.tag

    if tag is None:
        raise ValueError(f'Could not find {variable} in preprocessed registry')
    return tag
