"""Sphinx configuration for behave-retry documentation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path("..").resolve()))

project = "behave-retry"
author = "Mathias Paulenko"
release = "1.8.4"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

html_theme = "furo"
html_static_path = ["_static"]

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": False,
    "exclude-members": "__weakref__,__dict__,__module__,__init__,__post_init__",
}

autodoc_typehints = "signature"
autodoc_typehints_format = "short"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

myst_enable_extensions = ["colon_fence", "deflist", "substitution"]
myst_heading_anchors = 3
