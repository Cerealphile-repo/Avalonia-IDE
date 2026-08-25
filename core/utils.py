"""
Avalonia Utilities

Shared filesystem helpers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Union


PathLike = Union[str, Path]


#
# ----------------------------------------------------------------------
# Filesystem
# ----------------------------------------------------------------------
#

_IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".vs",
    ".vscode",
    "bin",
    "node_modules",
    "obj",
    "packages",
}


def is_solution(filename: PathLike) -> bool:
    """
    Return True if the filename is a Visual Studio solution.
    """

    return Path(filename).suffix.lower() == ".sln"


def is_project(filename: PathLike) -> bool:
    """
    Return True if the filename is an MSBuild project.
    """

    return Path(filename).suffix.lower() == ".csproj"


def walk(root: PathLike) -> Iterator[Path]:
    """
    Yield every file beneath root.

    Common build and metadata directories are skipped to avoid
    unnecessary filesystem traversal.
    """

    root = Path(root)

    for path, directories, files in os.walk(root):

        #
        # Prevent os.walk() from descending into ignored directories.
        #

        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in _IGNORED_DIRECTORIES
        )

        path = Path(path)

        for name in sorted(files):
            yield path / name
