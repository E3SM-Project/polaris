# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import logging
import os
from datetime import date

import yaml

from polaris.version import __version__

# -- Project information -----------------------------------------------------

project = "Polaris"
copyright = f"{date.today().year}, Energy Exascale Earth System Model Project"
author = "E3SM Development Team"

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
if 'DOCS_VERSION' in os.environ:
    version = os.environ.get('DOCS_VERSION')
    release = version
else:
    # The short X.Y.Z version.
    version = __version__
    # The full version, including alpha/beta/rc tags.
    release = __version__

master_doc = "index"
language = "en"

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "myst_parser",
    "sphinx_rtd_theme",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "sphinx.ext.napoleon",
    "sphinx_jinja",
]

autosummary_generate = ['developers_guide/api.md',
                        'developers_guide/e3sm/init/api.md',
                        'developers_guide/mesh/api.md',
                        'developers_guide/ocean/api.md',
                        'developers_guide/seaice/api.md']

# Otherwise, the Return parameter list looks different from the Parameters list
napoleon_use_rtype = False
# Otherwise, the Attributes parameter list looks different from the Parameters
# list
napoleon_use_ivar = True

suppress_warnings = ['autodoc.typehints']

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    # Convenience docs not intended for rendering
    "users_guide/invalid_quick_start.md",
    # Authoring templates kept in repo but not included in the built docs
    "users_guide/ocean/tasks/template.md",
    "users_guide/seaice/tasks/template.md",
]

intersphinx_mapping = {
    'geometric_features':
        ('https://mpas-dev.github.io/geometric_features/main', None),
    'mache': ('https://docs.e3sm.org/mache/main', None),
    'matplotlib': ('https://matplotlib.org/stable', None),
    'mpas_tools': ('https://mpas-dev.github.io/MPAS-Tools/master', None),
    'mosaic': ('https://docs.e3sm.org/mosaic', None),
    'numpy': ('https://numpy.org/doc/stable', None),
    'python': ('https://docs.python.org', None),
"sphinx": ("https://www.sphinx-doc.org/en/master", None),
    'xarray': ('https://xarray.pydata.org/en/stable', None),
    'tranche': ('https://xylar.github.io/tranche/', None),
}


def _downgrade_unreachable_inventory(record):
    """
    Report an intersphinx inventory that cannot be fetched as information
    rather than a warning, so an outage at another project's docs site does
    not fail a build that treats warnings as errors
    """
    if 'failed to reach any of the inventories' in str(record.msg):
        record.levelno = logging.INFO
        record.levelname = 'INFO'
    return True


# Sphinx puts its loggers under a "sphinx." namespace, so intersphinx's own
# "sphinx.ext.intersphinx" logger is "sphinx.sphinx.ext.intersphinx"
logging.getLogger('sphinx.sphinx.ext.intersphinx').addFilter(
    _downgrade_unreachable_inventory
)

# -- MyST settings ---------------------------------------------------

myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'dollarmath'
]
myst_number_code_blocks = ["typescript"]
myst_heading_anchors = 2
myst_footnote_transition = True
myst_dmath_double_inline = True
myst_enable_checkboxes = True

# -- HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_title = ""

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

html_context = {
    "current_version": os.getenv("DOCS_VERSION", "main"),
}

# -- Jinja context for sphinx-jinja ------------------------------------------

# Load supported machines data from YAML
_machines_yaml_path = os.path.join(
    os.path.dirname(__file__),
    'developers_guide',
    'supported_machines.yaml'
)

with open(_machines_yaml_path, 'r') as f:
    _machines_data = yaml.safe_load(f)

jinja_contexts = {
    'supported_machines': _machines_data,
}

# Trim block whitespace so the generated pipe table has no blank rows
jinja_env_kwargs = {'trim_blocks': True, 'lstrip_blocks': True}
