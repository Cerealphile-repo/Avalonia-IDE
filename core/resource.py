"""
Avalonia Resource Index

Builds deterministic lookup indexes from parsed AXAML documents.

This module is responsible for semantic resource indexing only.

It does not:

    - parse XML
    - walk the filesystem
    - interact with Sublime Text
    - resolve Avalonia resource scope
    - determine resource precedence

AXAML parsing is handled by axaml.py.

Project and workspace discovery are handled by the
corresponding project/index/solution modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event

from typing import Dict, Iterable, Tuple

from .axaml import AxamlDocument
from .indexing import IndexingCancelled


#
# ----------------------------------------------------------------------
# Indexed Resource
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class ResourceEntry:
    """
    One keyed resource declaration.
    """

    key: str

    kind: str

    path: Path


#
# ----------------------------------------------------------------------
# Indexed Resource Reference
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class ResourceReferenceEntry:
    """
    One keyed resource reference.
    """

    key: str

    kind: str

    path: Path


#
# ----------------------------------------------------------------------
# Resource Index
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class ResourceIndex:
    """
    Lookup index for resource declarations.

    Each resource key maps to all declarations using that key.

    Multiple entries are intentionally preserved because the same
    resource key may legitimately occur in different scopes or
    dictionaries.
    """

    by_key: Dict[str, Tuple[ResourceEntry, ...]]


#
# ----------------------------------------------------------------------
# Resource Reference Index
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class ResourceReferenceIndex:
    """
    Lookup index for resource references.

    Each resource key maps to every known usage of that key.
    """

    by_key: Dict[
        str,
        Tuple[ResourceReferenceEntry, ...],
    ]


#
# ----------------------------------------------------------------------
# Sorting
# ----------------------------------------------------------------------
#


def _resource_sort_key(
    entry: ResourceEntry,
) -> tuple[str, str, str]:
    """
    Return the deterministic ordering key for a resource.
    """

    return (
        str(entry.path).casefold(),
        entry.kind.casefold(),
        entry.key.casefold(),
    )


def _reference_sort_key(
    entry: ResourceReferenceEntry,
) -> tuple[str, str, str]:
    """
    Return the deterministic ordering key for a resource reference.
    """

    return (
        str(entry.path).casefold(),
        entry.kind.casefold(),
        entry.key.casefold(),
    )


def _key_sort_key(
    key: str,
) -> str:
    """
    Return the deterministic ordering key for an index key.
    """

    return key.casefold()


#
# ----------------------------------------------------------------------
# Resource Index Construction
# ----------------------------------------------------------------------
#


def build_resource_index(
    documents: Dict[Path, AxamlDocument],
    cancel_event: Event | None = None,
) -> ResourceIndex:
    """
    Build a resource declaration index from parsed AXAML documents.

    No parsing or filesystem access occurs here.

    Every resource declaration is preserved, including duplicate keys.
    """

    grouped: Dict[
        str,
        list[ResourceEntry],
    ] = {}

    for document in documents.values():

        if cancel_event is not None and cancel_event.is_set():
            raise IndexingCancelled()

        for resource in document.resources:

            entry = ResourceEntry(
                key=resource.key,
                kind=resource.kind,
                path=resource.path,
            )

            grouped.setdefault(
                resource.key,
                [],
            ).append(
                entry
            )

    return ResourceIndex(
        by_key=_freeze_resource_groups(
            grouped
        )
    )


#
# ----------------------------------------------------------------------
# Resource Index Aggregation
# ----------------------------------------------------------------------
#


def update_resource_index(
    index: ResourceIndex,
    document: AxamlDocument,
) -> ResourceIndex:
    """
    Replace the resource entries contributed by one AXAML document.

    Existing entries from unrelated documents are reused. The changed
    document is removed from the current groups and its current entries
    are inserted. No AXAML documents are reparsed here.
    """

    target = document.path.resolve()

    grouped: Dict[
        str,
        list[ResourceEntry],
    ] = {}

    for key, entries in index.by_key.items():

        remaining = [
            entry
            for entry in entries
            if entry.path.resolve() != target
        ]

        if remaining:
            grouped[key] = remaining

    for resource in document.resources:

        entry = ResourceEntry(
            key=resource.key,
            kind=resource.kind,
            path=resource.path,
        )

        grouped.setdefault(
            resource.key,
            [],
        ).append(
            entry
        )

    return ResourceIndex(
        by_key=_freeze_resource_groups(
            grouped
        )
    )


def merge_resource_indexes(
    indexes: Iterable[ResourceIndex],
) -> ResourceIndex:
    """
    Merge existing resource indexes.

    This is intended for aggregating project indexes into a
    workspace-level index.

    Existing ResourceEntry objects are reused.
    AXAML documents are not reparsed.
    """

    grouped: Dict[
        str,
        list[ResourceEntry],
    ] = {}

    for index in indexes:

        for key, entries in index.by_key.items():

            grouped.setdefault(
                key,
                [],
            ).extend(
                entries
            )

    return ResourceIndex(
        by_key=_freeze_resource_groups(
            grouped
        )
    )


#
# ----------------------------------------------------------------------
# Resource Reference Index Construction
# ----------------------------------------------------------------------
#


def build_resource_reference_index(
    documents: Dict[Path, AxamlDocument],
    cancel_event: Event | None = None,
) -> ResourceReferenceIndex:
    """
    Build a resource-reference index from parsed AXAML documents.

    Every reference is preserved, including repeated references to
    the same key from the same document.
    """

    grouped: Dict[
        str,
        list[ResourceReferenceEntry],
    ] = {}

    for document in documents.values():

        if cancel_event is not None and cancel_event.is_set():
            raise IndexingCancelled()

        for reference in document.references:

            entry = ResourceReferenceEntry(
                key=reference.key,
                kind=reference.kind,
                path=reference.path,
            )

            grouped.setdefault(
                reference.key,
                [],
            ).append(
                entry
            )

    return ResourceReferenceIndex(
        by_key=_freeze_reference_groups(
            grouped
        )
    )


#
# ----------------------------------------------------------------------
# Resource Reference Index Aggregation
# ----------------------------------------------------------------------
#


def update_resource_reference_index(
    index: ResourceReferenceIndex,
    document: AxamlDocument,
) -> ResourceReferenceIndex:
    """
    Replace the resource-reference entries contributed by one AXAML
    document.

    Existing entries from unrelated documents are reused.
    """

    target = document.path.resolve()

    grouped: Dict[
        str,
        list[ResourceReferenceEntry],
    ] = {}

    for key, entries in index.by_key.items():

        remaining = [
            entry
            for entry in entries
            if entry.path.resolve() != target
        ]

        if remaining:
            grouped[key] = remaining

    for reference in document.references:

        entry = ResourceReferenceEntry(
            key=reference.key,
            kind=reference.kind,
            path=reference.path,
        )

        grouped.setdefault(
            reference.key,
            [],
        ).append(
            entry
        )

    return ResourceReferenceIndex(
        by_key=_freeze_reference_groups(
            grouped
        )
    )


def merge_resource_reference_indexes(
    indexes: Iterable[ResourceReferenceIndex],
) -> ResourceReferenceIndex:
    """
    Merge existing resource-reference indexes.

    This is intended for aggregating project-level semantic indexes
    into a workspace-level reference index.
    """

    grouped: Dict[
        str,
        list[ResourceReferenceEntry],
    ] = {}

    for index in indexes:

        for key, entries in index.by_key.items():

            grouped.setdefault(
                key,
                [],
            ).extend(
                entries
            )

    return ResourceReferenceIndex(
        by_key=_freeze_reference_groups(
            grouped
        )
    )


#
# ----------------------------------------------------------------------
# Immutable Result Construction
# ----------------------------------------------------------------------
#


def _freeze_resource_groups(
    grouped: Dict[
        str,
        list[ResourceEntry],
    ],
) -> Dict[
    str,
    Tuple[ResourceEntry, ...],
]:
    """
    Sort and freeze grouped resource entries.
    """

    result: Dict[
        str,
        Tuple[ResourceEntry, ...],
    ] = {}

    for key in sorted(
        grouped,
        key=_key_sort_key,
    ):

        values = grouped[key]

        values.sort(
            key=_resource_sort_key
        )

        result[key] = tuple(
            values
        )

    return result


def _freeze_reference_groups(
    grouped: Dict[
        str,
        list[ResourceReferenceEntry],
    ],
) -> Dict[
    str,
    Tuple[ResourceReferenceEntry, ...],
]:
    """
    Sort and freeze grouped resource-reference entries.
    """

    result: Dict[
        str,
        Tuple[ResourceReferenceEntry, ...],
    ] = {}

    for key in sorted(
        grouped,
        key=_key_sort_key,
    ):

        values = grouped[key]

        values.sort(
            key=_reference_sort_key
        )

        result[key] = tuple(
            values
        )

    return result
