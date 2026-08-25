"""
Avalonia Project Indexer

Indexes project files and classifies them.

This module is responsible for filesystem indexing
and file classification only.

Semantic parsing is handled by dedicated semantic builders.
Filesystem traversal is handled by utils.walk().
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from threading import Event

from typing import DefaultDict, Dict, List

from .indexing import IndexingCancelled

from .domain import (
    FileKind,
    ProjectIndex,
    SourceFile,
)

from .utils import walk


#
# ----------------------------------------------------------------------
# Classification Rules
# ----------------------------------------------------------------------
#


_ASSET_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".svg",
        ".webp",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
    }
)


_RESOURCE_EXTENSIONS = frozenset(
    {
        ".resx",
        ".json",
        ".xml",
        ".yml",
        ".yaml",
    }
)


_STYLE_NAMES = frozenset(
    {
        "styles.axaml",
        "colors.axaml",
        "theme.axaml",
    }
)


#
# ----------------------------------------------------------------------
# Classification
# ----------------------------------------------------------------------
#


def classify(
    path: Path,
) -> FileKind:

    """
    Classify a project file.

    Classification is based only on the path.
    No file contents are read.
    """

    name = path.name.lower()
    suffix = path.suffix.lower()

    #
    # ------------------------------------------------------------------
    # Solution / Project
    # ------------------------------------------------------------------
    #

    if suffix == ".sln":
        return FileKind.SOLUTION

    if suffix == ".csproj":
        return FileKind.PROJECT

    #
    # ------------------------------------------------------------------
    # Avalonia
    # ------------------------------------------------------------------
    #

    if suffix == ".axaml":

        if name in _STYLE_NAMES:
            return FileKind.STYLE

        return FileKind.VIEW

    #
    # ------------------------------------------------------------------
    # C# Code-Behind
    # ------------------------------------------------------------------
    #
    # Path.suffix for "Main.axaml.cs" is ".cs", so the compound
    # extension must be checked before normal C# classification.
    #

    if name.endswith(".axaml.cs"):
        return FileKind.CODE_BEHIND

    #
    # ------------------------------------------------------------------
    # C#
    # ------------------------------------------------------------------
    #

    if suffix == ".cs":

        stem = path.stem

        if stem.endswith("ViewModel"):
            return FileKind.VIEWMODEL

        if stem.endswith("Model"):
            return FileKind.MODEL

        if _is_test_path(path):
            return FileKind.TEST

        return FileKind.SOURCE

    #
    # ------------------------------------------------------------------
    # Assets
    # ------------------------------------------------------------------
    #

    if suffix in _ASSET_EXTENSIONS:
        return FileKind.ASSET

    #
    # ------------------------------------------------------------------
    # External Resources
    # ------------------------------------------------------------------
    #

    if suffix in _RESOURCE_EXTENSIONS:
        return FileKind.RESOURCE

    return FileKind.OTHER


def _is_test_path(
    path: Path,
) -> bool:

    """
    Return whether a C# file appears to belong to a test directory.
    """

    return any(
        "test" in part.lower()
        for part in path.parts[:-1]
    )


#
# ----------------------------------------------------------------------
# Index Builder
# ----------------------------------------------------------------------
#


def build_index(
    project_root: Path,
    cancel_event: Event | None = None,
) -> ProjectIndex:

    """
    Build the filesystem index for a project.

    This function:

        - walks the project directory
        - classifies discovered files
        - builds lookup tables
        - sorts results deterministically

    It does not:

        - parse AXAML
        - parse C#
        - build resource indexes
        - build semantic indexes
        - interact with Sublime Text
    """

    files: List[SourceFile] = []

    by_path: Dict[
        Path,
        SourceFile,
    ] = {}

    by_name: DefaultDict[
        str,
        List[SourceFile],
    ] = defaultdict(list)

    by_kind: DefaultDict[
        FileKind,
        List[SourceFile],
    ] = defaultdict(list)

    #
    # ------------------------------------------------------------------
    # Filesystem Discovery
    # ------------------------------------------------------------------
    #

    for path in walk(
        project_root
    ):

        if cancel_event is not None and cancel_event.is_set():
            raise IndexingCancelled()

        resolved_path = path.resolve()

        source_file = SourceFile(
            path=resolved_path,
            kind=classify(
                path
            ),
        )

        files.append(
            source_file
        )

        by_path[
            source_file.path
        ] = source_file

        by_name[
            source_file.name
        ].append(
            source_file
        )

        by_kind[
            source_file.kind
        ].append(
            source_file
        )

    #
    # ------------------------------------------------------------------
    # Deterministic Ordering
    # ------------------------------------------------------------------
    #

    files.sort(
        key=lambda item: str(item.path).lower()
    )

    for values in by_name.values():

        values.sort(
            key=lambda item: str(item.path).lower()
        )

    for values in by_kind.values():

        values.sort(
            key=lambda item: str(item.path).lower()
        )

    #
    # ------------------------------------------------------------------
    # Project Index
    # ------------------------------------------------------------------
    #
    # Semantic collections intentionally start empty.
    #
    # semantic_index.py owns the transition from this filesystem-only
    # representation to a semantically enriched ProjectIndex.
    #

    return ProjectIndex(
        files=tuple(
            files
        ),

        views=tuple(
            by_kind[FileKind.VIEW]
        ),

        code_behind=tuple(
            by_kind[FileKind.CODE_BEHIND]
        ),

        viewmodels=tuple(
            by_kind[FileKind.VIEWMODEL]
        ),

        models=tuple(
            by_kind[FileKind.MODEL]
        ),

        resources=tuple(
            by_kind[FileKind.RESOURCE]
        ),

        styles=tuple(
            by_kind[FileKind.STYLE]
        ),

        assets=tuple(
            by_kind[FileKind.ASSET]
        ),

        tests=tuple(
            by_kind[FileKind.TEST]
        ),

        others=tuple(
            by_kind[FileKind.OTHER]
        ),

        #
        # Semantic documents.
        #

        axaml_documents={},

        csharp_documents={},

        #
        # Semantic indexes.
        #
        # These are deliberately absent at this stage. They are
        # populated by build_semantic_index().
        #

        resource_index=None,

        resource_reference_index=None,

        #
        # Lookup tables.
        #

        by_path=by_path,

        by_name={
            key: tuple(
                values
            )
            for key, values in by_name.items()
        },

        by_kind={
            key: tuple(
                values
            )
            for key, values in by_kind.items()
        },
    )
