"""
sandbox/ — Vercel Sandbox setup package.

Public API:
    from sandbox import setup          # create sandbox + upload files
    from sandbox import generate_files, generate_file_tree  # file dict + tree
"""

from .setup import setup
from .context import generate_files, generate_file_tree

__all__ = ["setup", "generate_files", "generate_file_tree"]
