"""
Avalonia Workspace Discovery

Locate the active solution or standalone project for a Sublime window.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .domain import ProjectLocation
from .log import log
from .utils import is_project, is_solution, walk


def find_project(window) -> Optional[ProjectLocation]:
    """
    Locate the active workspace.

    Returns a ProjectLocation describing the first discovered
    solution or standalone project, or None if nothing usable
    could be found.
    """

    folders = window.folders()

    if not folders:
        log.warning("Workspace contains no folders.")
        return None

    for folder in folders:

        root = Path(folder).resolve()

        solution: Optional[Path] = None
        project: Optional[Path] = None

        for filename in walk(root):

            log.info(f"Checking: {filename}")

            filename = Path(filename).resolve()

            if solution is None and is_solution(filename):
                solution = filename
                break

            if project is None and is_project(filename):
                project = filename

        if solution is not None:

            return ProjectLocation(
                root=root,
                solution=solution,
                project=None,
            )

        if project is not None:

            return ProjectLocation(
                root=root,
                solution=None,
                project=project,
            )

    log.warning("No solution or project found.")

    return None
