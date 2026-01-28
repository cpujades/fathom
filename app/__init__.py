"""Retrieve version from package metadata."""

from importlib.metadata import version

__version__ = version("fathom")
