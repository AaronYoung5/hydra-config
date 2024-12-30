# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

import sys
from datetime import date

# The full version, including alpha/beta/rc tags
from importlib.metadata import version as get_version
from pathlib import Path

root_path = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, root_path)
sys.setrecursionlimit(1500)

# -- Project information -----------------------------------------------------

project = "hydra-config"
copyright = f"{date.today().year}, Aaron Young"
author = "Aaron Young"
release = get_version(project)

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.viewcode",
    "sphinx.ext.githubpages",
    "autoapi.extension",
    "myst_parser",
    "sphinx_copybutton",
    "sphinxcontrib.video",
    "sphinxcontrib.googleanalytics",
]

# autoapi config
autoapi_type = "python"
autoapi_dirs = ["../hydra_config"]
autoapi_options = [
    "members",
    "show-inheritance",
    "show-module-summary",
    "special-members",
    "imported-members",
    # "inherited-members"  # Doesn't work with viewcode extension
]
autoapi_ignore = []
autoapi_keep_files = False
autoapi_keep_files = True
autoapi_generate_api_docs = True
autoapi_add_toctree_entry = False
autoapi_root = "reference/api/"
# autoapi_template_dir = "_templates"
# autoapi_member_order = "groupwise"

# suppress_warnings = ["autoapi"]

add_module_names = False
autodoc_typehints = "none"

# Napoleon
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_ivar = True
napoleon_use_param = False
napoleon_use_rtype = False
napoleon_type_aliases = None
napoleon_attr_annotations = True

# MyST
myst_heading_anchors = 7

viewcode_enable_epub = True

# Display todos by setting to True
todo_include_todos = True

# Add any paths that contain templates here, relative to this directory.
# templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

# Google Analytics
googleanalytics_id = "G-4SJ32LRS8B"


# -- Options for HTML output -------------------------------------------------

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = "friendly"

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "furo"
html_favicon = "_static/doc.png"
html_theme_options = {
    "announcement": """
        <a style=\"text-decoration: none; color: white;\"
           href=\"https://AaronYoung5.github.io\">
           Check out my other projects!
        </a>
    """,
    "sidebar_hide_name": True,
    "light_logo": "doc.png",
    "dark_logo": "doc.png",
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# These paths are either relative to html_static_path
# or fully qualified paths (eg. https://...)
html_css_files = [
    "css/custom.css",
]
