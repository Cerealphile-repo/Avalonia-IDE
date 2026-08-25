"""
Avalonia Solution Builder

Constructs immutable Solution objects from a discovered workspace.

Workspace construction follows three distinct stages:

    1. Parse project and solution metadata.
    2. Build the filesystem ProjectIndex.
    3. Enrich the ProjectIndex with semantic information.

Filesystem discovery and semantic indexing remain separate
responsibilities.
"""

from __future__ import annotations

from typing import Optional
from threading import Event

from .indexing import IndexingCancelled

from .domain import (
    Project,
    ProjectLocation,
    Solution,
)

from .index import build_index
from .parser import (
    parse_project,
    parse_solution,
)
from .semantic_index import build_semantic_index


def build_solution(
    location: ProjectLocation,
    cancel_event: Optional[Event] = None,
) -> Solution:

    """
    Build a complete immutable Solution from a discovered workspace.

    Every project is built through the same pipeline:

        project metadata
            ↓
        filesystem index
            ↓
        semantic index
            ↓
        Project
    """

    projects = []

    startup_project: Optional[Project] = None

    #
    # ------------------------------------------------------------------
    # Determine Project Files
    # ------------------------------------------------------------------
    #

    if location.solution is not None:

        project_files = [
            project.project_file
            for project in parse_solution(
                location.solution
            )
        ]

    elif location.project is not None:

        project_files = [
            location.project
        ]

    else:

        project_files = []

    #
    # ------------------------------------------------------------------
    # Build Projects
    # ------------------------------------------------------------------
    #

    for project_file in project_files:

        if cancel_event is not None and cancel_event.is_set():
            raise IndexingCancelled()

        metadata = parse_project(
            project_file
        )

        #
        # Filesystem discovery.
        #

        index = build_index(
            project_file.parent,
            cancel_event=cancel_event,
        )

        #
        # Semantic enrichment.
        #
        # This is the single point at which the filesystem index
        # becomes a semantic project index.
        #

        index = build_semantic_index(
            index,
            cancel_event=cancel_event,
        )

        project = Project(
            name=metadata.name,
            root=project_file.parent,
            project_file=metadata.project_file,
            sdk=metadata.sdk,
            framework=metadata.framework,
            output_type=metadata.output_type,
            avalonia_version=metadata.avalonia_version,
            executable=metadata.executable,
            index=index,
        )

        projects.append(
            project
        )

        #
        # Use the first executable project as startup.
        #

        if (
            startup_project is None
            and project.executable
        ):
            startup_project = project

    #
    # ------------------------------------------------------------------
    # Startup Fallback
    # ------------------------------------------------------------------
    #

    if startup_project is None and projects:
        startup_project = projects[0]

    #
    # ------------------------------------------------------------------
    # Solution
    # ------------------------------------------------------------------
    #

    return Solution(
        root=location.root,
        solution=location.solution,
        projects=tuple(projects),
        startup_project=startup_project,
    )
