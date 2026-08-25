"""
Avalonia Navigation Logic

Provides semantic navigation helpers for relationships between
Avalonia views, code-behind files, and view models.

This module contains no Sublime Text API calls.

It operates only on ProjectIndex and SourceFile domain objects.

Navigation is intentionally conservative:

    View.axaml
        -> View.axaml.cs
        -> ViewModel.cs

The index is responsible for discovering files.

This module is responsible only for determining relationships
between already-indexed files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from .domain import (
    FileKind,
    ProjectIndex,
    SourceFile,
)

from .resource import (
    ResourceEntry,
    ResourceReferenceEntry,
)


#
# ----------------------------------------------------------------------
# Naming Helpers
# ----------------------------------------------------------------------
#


def _view_stem(
    source: SourceFile,
) -> str:
    """
    Return the logical view name for a source file.

    Examples:

        MainView.axaml      -> MainView
        MainView.axaml.cs   -> MainView
        MainViewModel.cs    -> MainView
        MainView.cs         -> MainView
    """

    name = source.path.name

    if name.endswith(".axaml.cs"):
        return name[:-len(".axaml.cs")]

    if name.endswith(".axaml"):
        return name[:-len(".axaml")]

    if name.endswith("ViewModel.cs"):
        return name[:-len("ViewModel.cs")]

    if name.endswith(".cs"):
        return name[:-len(".cs")]

    return source.path.stem


def _same_directory(
    left: SourceFile,
    right: SourceFile,
) -> bool:
    """
    Return True when two source files share the same directory.
    """

    return left.path.parent == right.path.parent


def _candidate_key(
    source: SourceFile,
) -> tuple[str, str]:
    """
    Return a deterministic ordering key for a source candidate.
    """

    return (
        str(source.path).casefold(),
        source.path.name.casefold(),
    )


def _select_candidate(
    source: SourceFile,
    candidates: list[SourceFile],
) -> Optional[SourceFile]:
    """
    Select the best candidate from a collection of related files.

    Same-directory candidates are preferred because a conventional
    Avalonia view relationship normally keeps the related files
    together.

    Remaining candidates are selected deterministically.
    """

    if not candidates:
        return None

    local = [
        candidate
        for candidate in candidates
        if _same_directory(
            source,
            candidate,
        )
    ]

    if local:
        candidates = local

    candidates.sort(
        key=_candidate_key
    )

    return candidates[0]


#
# ----------------------------------------------------------------------
# View / Code Relationships
# ----------------------------------------------------------------------
#


def find_code_behind(
    index: ProjectIndex,
    source: SourceFile,
) -> Optional[SourceFile]:
    """
    Find the code-behind file associated with an AXAML view.

    The expected relationship is:

        MainView.axaml
            -> MainView.axaml.cs

    Only files already classified as CODE_BEHIND are considered.
    """

    if source.kind != FileKind.VIEW:
        return None

    stem = _view_stem(source)

    candidates = [
        candidate
        for candidate in index.code_behind
        if _view_stem(candidate) == stem
    ]

    return _select_candidate(
        source,
        candidates,
    )


def find_view(
    index: ProjectIndex,
    source: SourceFile,
) -> Optional[SourceFile]:
    """
    Find the AXAML view associated with a source file.

    Supported relationships include:

        MainView.axaml.cs
            -> MainView.axaml

        MainViewModel.cs
            -> MainView.axaml

        MainView.cs
            -> MainView.axaml

    The search prefers a view in the same directory.
    """

    if source.kind not in (
        FileKind.CODE_BEHIND,
        FileKind.VIEWMODEL,
        FileKind.SOURCE,
    ):
        return None

    stem = _view_stem(source)

    candidates = [
        candidate
        for candidate in index.views
        if _view_stem(candidate) == stem
    ]

    return _select_candidate(
        source,
        candidates,
    )


def find_viewmodel(
    index: ProjectIndex,
    source: SourceFile,
) -> Optional[SourceFile]:
    """
    Find the ViewModel associated with an AXAML view.

    The expected relationship is:

        MainView.axaml
            -> MainViewModel.cs

    The search prefers a ViewModel in the same directory.
    """

    if source.kind != FileKind.VIEW:
        return None

    stem = _view_stem(source)

    expected_stem = (
        stem + "ViewModel"
    )

    candidates = [
        candidate
        for candidate in index.viewmodels
        if _view_stem(candidate) == expected_stem
    ]

    return _select_candidate(
        source,
        candidates,
    )


#
# ----------------------------------------------------------------------
# Related Files
# ----------------------------------------------------------------------
#


def related_files(
    index: ProjectIndex,
    source: SourceFile,
) -> Tuple[SourceFile, ...]:
    """
    Return the files directly related to a source file.

    The result may contain:

        - the associated view
        - the associated code-behind
        - the associated ViewModel

    Duplicate paths are removed while preserving relationship order.
    """

    related: list[SourceFile] = []

    if source.kind == FileKind.VIEW:

        code_behind = find_code_behind(
            index,
            source,
        )

        if code_behind is not None:
            related.append(
                code_behind
            )

        viewmodel = find_viewmodel(
            index,
            source,
        )

        if viewmodel is not None:
            related.append(
                viewmodel
            )

    else:

        view = find_view(
            index,
            source,
        )

        if view is not None:
            related.append(
                view
            )

            code_behind = find_code_behind(
                index,
                view,
            )

            if code_behind is not None:
                related.append(
                    code_behind
                )

            viewmodel = find_viewmodel(
                index,
                view,
            )

            if viewmodel is not None:
                related.append(
                    viewmodel
                )

    result: list[SourceFile] = []

    seen: set[Path] = set()

    for item in related:

        if item.path in seen:
            continue

        seen.add(
            item.path
        )

        result.append(
            item
        )

    return tuple(
        result
    )


#
# ----------------------------------------------------------------------
# Resource Navigation
# ----------------------------------------------------------------------
#


def find_resource(
    index: ProjectIndex,
    key: str,
) -> Optional[ResourceEntry]:
    """
    Find a resource declaration by key.

    The ProjectIndex already contains the semantic resource index.

    This function performs lookup only.

    It does not parse AXAML or rebuild an index.

    When multiple declarations exist, the first deterministic entry
    is returned. Resource scope and precedence are intentionally not
    resolved here yet.
    """

    resource_index = index.resource_index

    if resource_index is None:
        return None

    entries = resource_index.by_key.get(
        key
    )

    if not entries:
        return None

    return entries[0]


def find_resource_references(
    index: ProjectIndex,
    key: str,
) -> Tuple[ResourceReferenceEntry, ...]:
    """
    Find AXAML references to a resource key.

    The ProjectIndex already contains the semantic reference index.

    This function performs lookup only.
    """

    reference_index = (
        index.resource_reference_index
    )

    if reference_index is None:
        return ()

    return reference_index.by_key.get(
        key,
        (),
    )
