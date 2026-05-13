# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys
from datetime import datetime

import freva_gpt_client

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath("../../src"))


# debug that building expected version
print(f"Building Documentation for FrevaGPT Client: {freva_gpt_client.__version__}")

project = "freva-gpt-client"
copyright = f"{datetime.now().year}, DKRZ"
author = "Felix Oertel"
# extract version tag, label as "latest" if version string includes more than just a version tag
full_version: str = str(freva_gpt_client.__version__)
version_parts = full_version.split("+")
version = "latest" if len(version_parts) > 1 else full_version
release = version

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-options

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
clude_patterns = []  # type: ignore[var-annotated]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]

# Theme options
html_theme_options = {
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/freva-org/freva-gpt-client",
            "icon": "fa-brands fa-github",
        }
    ],
    "navigation_with_keys": False,
    "show_toc_level": 4,
    "collapse_navigation": True,
    "navigation_depth": 4,
    "navbar_align": "left",
    "show_nav_level": 4,
    "navigation_depth": 4,
    "navbar_center": ["navbar-nav"],
    "secondary_sidebar_items": ["page-toc"],
}

html_sidebars = {"**": []}  # type: ignore[var-annotated]
html_context = {"default_mode": "light"}

# Custom CSS
html_css_files = ["custom.css"]

autosummary_generate = True

# Napoleon settings for Google/NumPy-style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True


# -- Options for intersphinx -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "httpx": ("https://www.python-httpx.org/", None),
}

# -- Options for internationalization ----------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#internationalization-options

language = "en"

# -- Options for LaTeX output -----------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-latex-output

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    "papersize": "a4paper",
    # The font size ('10pt', '11pt' or '12pt').
    "pointsize": "10pt",
    # Additional stuff for the LaTeX preamble.
    "preamble": "",
    # Latex figure (float) alignment
    "figure_align": "htbp",
}

# -- Options for manual page output -----------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-manual-page-output

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    ("index", "freva-gpt-client", "FrevaGPT Client Documentation", [author], 1),
]

# -- Options for Texinfo output ---------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-texinfo-output

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, description, category, toctree only).
texinfo_documents = [
    (
        "index",
        "freva_gpt_client",
        "FrevaGPT Client Documentation",
        author,
        "freva_gpt_client",
        "A Python client library for interacting with the FrevaGPT backend.",
        "Miscellaneous",
    ),
]
