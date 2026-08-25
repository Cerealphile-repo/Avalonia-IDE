"""
Avalonia Domain Model

Immutable objects describing an Avalonia workspace.

This module contains domain data only.

It does not:

    - parse XML
    - parse C#
    - walk the filesystem
    - execute processes
    - interact with Sublime Text
    - build semantic indexes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional, Tuple


if TYPE_CHECKING:

    from .axaml import AxamlDocument

    from .csharp_semantic import CSharpDocument, CSharpSemanticIndex

    from .resource import (
        ResourceIndex,
        ResourceReferenceIndex,
    )


#
# ----------------------------------------------------------------------
# File Classification
# ----------------------------------------------------------------------
#


class FileKind(Enum):
    """
    Classification assigned to a discovered project file.
    """

    VIEW = auto()
    CODE_BEHIND = auto()
    VIEWMODEL = auto()
    MODEL = auto()
    RESOURCE = auto()
    STYLE = auto()
    ASSET = auto()
    SOURCE = auto()
    PROJECT = auto()
    SOLUTION = auto()
    TEST = auto()
    OTHER = auto()


#
# ----------------------------------------------------------------------
# Workspace Discovery
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class ProjectLocation:
    """
    Location of a discovered workspace.

    A workspace may contain either:

        - a solution
        - a standalone project

    `root` always identifies the workspace root.
    """

    root: Path

    solution: Optional[Path]

    project: Optional[Path]


#
# ----------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class SourceFile:
    """
    A single file discovered by the project indexer.
    """

    path: Path

    kind: FileKind

    @property
    def name(self) -> str:
        """
        Return the filename including its extension.
        """

        return self.path.name

    @property
    def stem(self) -> str:
        """
        Return the filename without its final extension.
        """

        return self.path.stem

    @property
    def suffix(self) -> str:
        """
        Return the lowercase final extension.
        """

        return self.path.suffix.lower()

    @property
    def parent(self) -> Path:
        """
        Return the containing directory.
        """

        return self.path.parent


#
# ----------------------------------------------------------------------
# Project Index
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    """
    Immutable representation of a project's indexed contents.

    ProjectIndex has two logical stages.

    Stage 1
        The filesystem indexer discovers and classifies files and
        constructs the lookup tables.

    Stage 2
        Semantic builders derive parsed documents and semantic indexes
        from the filesystem index.

    The object is immutable, so semantic enrichment produces a new
    ProjectIndex rather than mutating the filesystem index.

    This class contains data only. It contains no indexing, parsing,
    filesystem, or editor logic.
    """

    #
    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    #

    files: Tuple[SourceFile, ...] = ()

    views: Tuple[SourceFile, ...] = ()

    code_behind: Tuple[SourceFile, ...] = ()

    viewmodels: Tuple[SourceFile, ...] = ()

    models: Tuple[SourceFile, ...] = ()

    resources: Tuple[SourceFile, ...] = ()

    styles: Tuple[SourceFile, ...] = ()

    assets: Tuple[SourceFile, ...] = ()

    tests: Tuple[SourceFile, ...] = ()

    others: Tuple[SourceFile, ...] = ()

    #
    # ------------------------------------------------------------------
    # Semantic Documents
    # ------------------------------------------------------------------
    #
    # Keys are normalized absolute file paths.
    #
    # The filesystem indexer leaves these empty.
    # Semantic builders populate them.
    #

    axaml_documents: Dict[
        Path,
        AxamlDocument,
    ] = field(
        default_factory=dict
    )

    csharp_documents: Dict[
        Path,
        CSharpDocument,
    ] = field(default_factory=dict)

    csharp_index: Optional[CSharpSemanticIndex] = None

    #
    # ------------------------------------------------------------------
    # Semantic Indexes
    # ------------------------------------------------------------------
    #
    # These are derived from the semantic documents.
    #
    # They are None on a filesystem-only ProjectIndex and populated
    # by semantic_index.build_semantic_index().
    #

    resource_index: Optional[
        ResourceIndex
    ] = None

    resource_reference_index: Optional[
        ResourceReferenceIndex
    ] = None

    #
    # ------------------------------------------------------------------
    # Lookup Tables
    # ------------------------------------------------------------------
    #

    by_path: Dict[
        Path,
        SourceFile,
    ] = field(
        default_factory=dict
    )

    by_name: Dict[
        str,
        Tuple[SourceFile, ...],
    ] = field(
        default_factory=dict
    )

    by_kind: Dict[
        FileKind,
        Tuple[SourceFile, ...],
    ] = field(
        default_factory=dict
    )


#
# ----------------------------------------------------------------------
# Projects
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class Project:
    """
    Immutable representation of a single Avalonia/.NET project.
    """

    #
    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    #

    name: str

    #
    # ------------------------------------------------------------------
    # Filesystem
    # ------------------------------------------------------------------
    #

    root: Path

    project_file: Path

    #
    # ------------------------------------------------------------------
    # Build Metadata
    # ------------------------------------------------------------------
    #

    sdk: Optional[str]

    framework: Optional[str]

    output_type: Optional[str]

    avalonia_version: Optional[str]

    executable: bool

    #
    # ------------------------------------------------------------------
    # Indexed Contents
    # ------------------------------------------------------------------
    #

    index: ProjectIndex


#
# ----------------------------------------------------------------------
# Solution
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class Solution:
    """
    Immutable representation of a complete Avalonia workspace.

    A solution may contain multiple projects, including class
    libraries, applications, and test projects.
    """

    root: Path

    solution: Optional[Path]

    projects: Tuple[Project, ...]

    startup_project: Optional[Project]
