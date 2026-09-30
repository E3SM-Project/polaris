import re

# camel case broken before an upper-case letter that begins a word, and
# between a lower-case letter or digit and the upper-case letter after it, so
# that an acronym stays whole: "velocityZonal" gives "velocity_zonal" and
# "sshMaxSSH" gives "ssh_max_ssh"
_WORD_START = re.compile(r'(.)([A-Z][a-z]+)')
_AFTER_LOWER = re.compile(r'([a-z0-9])([A-Z])')

# The prefix of the config section holding the plotting options for maps of
# one field
_MAP_PREFIX = 'ocean_analysis_map'


def camel_to_snake(name):
    """
    Convert a model's camel-case variable name to the lower case with
    underscores that Polaris config sections and options are spelled with

    Parameters
    ----------
    name : str
        A variable name in the spelling a model writes it with, such as
        ``velocityZonal``

    Returns
    -------
    snake_name : str
        The same name in lower case with underscores, such as
        ``velocity_zonal``
    """
    snake_name = _WORD_START.sub(r'\1_\2', name)
    snake_name = _AFTER_LOWER.sub(r'\1_\2', snake_name)
    return snake_name.lower()


def map_section(field):
    """
    Get the config section with the plotting options for maps of a field

    Field names are the models' own and are therefore camel case, while
    Polaris config sections are lower case with underscores, so the section
    name is not the field name pasted onto a prefix.  This is the one place
    that knows both the prefix and the spelling rule.

    Parameters
    ----------
    field : str
        The field being mapped, using the name the model writes it with,
        such as ``velocityZonal``

    Returns
    -------
    section : str
        The name of the config section, such as
        ``ocean_analysis_map_velocity_zonal``
    """
    return f'{_MAP_PREFIX}_{camel_to_snake(field)}'
