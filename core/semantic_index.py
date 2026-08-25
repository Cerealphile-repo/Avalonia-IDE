"""
Avalonia Semantic Index Builder

Builds semantic metadata from an existing ProjectIndex.

This module connects filesystem indexing with semantic parsers.

It never walks the filesystem.
It never interacts with Sublime Text.

Filesystem discovery is handled by index.py.
Semantic parsing is handled by parser modules.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Dict, Set
from threading import Event

from .axaml import (
    AxamlDocument,
    parse_axaml,
)

from .domain import ProjectIndex
from .csharp_semantic import build_csharp_index

from .indexing import IndexingCancelled

from .resource import (
    build_resource_index,
    build_resource_reference_index,
    update_resource_index,
    update_resource_reference_index,
)


#
# ----------------------------------------------------------------------
# AXAML Semantic Documents
# ----------------------------------------------------------------------
#


def build_axaml_index(
    index: ProjectIndex,
    cancel_event: Event | None = None,
) -> Dict[Path, AxamlDocument]:

    """
    Parse every AXAML document known to the project index.

    The filesystem index determines which files exist.
    This function only selects AXAML files and parses them.

    Resources can exist in:

        - Views
        - App.axaml
        - Styles
        - Resource dictionaries
        - Test AXAML files

    The filesystem is never walked here.
    """

    axaml_files: Set[Path] = set()

    #
    # Normal views.
    #

    axaml_files.update(
        source_file.path
        for source_file in index.views
    )

    #
    # Styles and themes.
    #

    axaml_files.update(
        source_file.path
        for source_file in index.styles
    )

    #
    # Catch AXAML files that were classified into another category.
    #
    # This keeps semantic parsing independent of the classification
    # rules used by the filesystem indexer.
    #

    axaml_files.update(
        source_file.path
        for source_file in index.files
        if source_file.path.suffix.lower() == ".axaml"
    )

    #
    # Parse deterministically.
    #

    documents: Dict[
        Path,
        AxamlDocument,
    ] = {}

    for path in sorted(
        axaml_files,
        key=lambda item: str(item).lower(),
    ):

        if cancel_event is not None and cancel_event.is_set():
            raise IndexingCancelled()

        document = parse_axaml(
            path
        )

        documents[
            document.path
        ] = document

    return documents


#
# ----------------------------------------------------------------------
# Semantic Project Index
# ----------------------------------------------------------------------
#


def build_semantic_index(
    index: ProjectIndex,
    cancel_event: Event | None = None,
) -> ProjectIndex:

    """
    Enrich an existing filesystem ProjectIndex with semantic data.

    The input ProjectIndex is never mutated.

    The returned ProjectIndex owns:

        - parsed AXAML documents
        - the project resource index
        - the project resource-reference index

    All resource indexes are derived from the same parsed AXAML
    document collection.
    """

    #
    # ------------------------------------------------------------------
    # Parse AXAML
    # ------------------------------------------------------------------
    #

    axaml_documents = build_axaml_index(
        index,
        cancel_event=cancel_event,
    )

    #
    # ------------------------------------------------------------------
    # Build Semantic Indexes
    # ------------------------------------------------------------------
    #

    resource_index = build_resource_index(
        axaml_documents,
        cancel_event=cancel_event,
    )

    resource_reference_index = (
        build_resource_reference_index(
            axaml_documents,
            cancel_event=cancel_event,
        )
    )

    csharp_files = [
        source_file.path
        for source_file in index.files
        if source_file.path.suffix.lower() == ".cs"
        and not source_file.path.name.endswith(".g.cs")
    ]
    csharp_index = build_csharp_index(
        csharp_files,
        cancel_event=cancel_event,
    )

    #
    # ------------------------------------------------------------------
    # Return Enriched ProjectIndex
    # ------------------------------------------------------------------
    #

    return replace(
        index,
        axaml_documents=axaml_documents,
        resource_index=resource_index,
        resource_reference_index=resource_reference_index,
        csharp_documents=csharp_index.documents,
        csharp_index=csharp_index,
    )

#
# ----------------------------------------------------------------------
# Incremental AXAML Update
# ----------------------------------------------------------------------
#


def update_axaml_document(
    index: ProjectIndex,
    path: Path,
) -> ProjectIndex:
    """
    Incrementally replace one AXAML document in a semantic project index.

    Only the changed AXAML file is parsed. The existing C# semantic index
    and all unrelated AXAML documents are preserved. Resource and
    resource-reference indexes are updated only for entries contributed by
    the changed document.

    The filesystem ProjectIndex is never rebuilt here.
    """

    target = path.resolve()

    document = parse_axaml(
        target
    )

    documents = dict(
        index.axaml_documents
    )

    documents[target] = document

    resource_index = index.resource_index

    if resource_index is None:

        resource_index = build_resource_index(
            documents
        )

    else:

        resource_index = update_resource_index(
            resource_index,
            document,
        )

    resource_reference_index = (
        index.resource_reference_index
    )

    if resource_reference_index is None:

        resource_reference_index = (
            build_resource_reference_index(
                documents
            )
        )

    else:

        resource_reference_index = (
            update_resource_reference_index(
                resource_reference_index,
                document,
            )
        )

    return replace(
        index,
        axaml_documents=documents,
        resource_index=resource_index,
        resource_reference_index=resource_reference_index,
    )

