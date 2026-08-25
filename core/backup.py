"""
Avalonia AXAML Parser

Parses a single Avalonia .axaml document into immutable metadata
objects.

This module performs XML parsing only.

It never walks the filesystem, interacts with Sublime Text,
or indexes workspace files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple
import xml.etree.ElementTree as ET


#
# ----------------------------------------------------------------------
# Resource Metadata
# ----------------------------------------------------------------------
#


@dataclass(frozen=True)
class AxamlResource:
    """
    A keyed resource declared in an AXAML document.
    """

    key: str

    kind: str

    path: Path


#
# ----------------------------------------------------------------------
# AXAML Document
# ----------------------------------------------------------------------
#


@dataclass(frozen=True)
class AxamlDocument:
    """
    Immutable metadata extracted from an AXAML document.
    """

    path: Path

    resources: Tuple[AxamlResource, ...]


#
# ----------------------------------------------------------------------
# XML Constants
# ----------------------------------------------------------------------
#


_XAML_NAMESPACE = (
    "http://schemas.microsoft.com/winfx/2006/xaml"
)

_X_KEY = (
    f"{{{_XAML_NAMESPACE}}}Key"
)


#
# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------
#


def parse_axaml(path: Path) -> AxamlDocument:
    """
    Parse an AXAML document.

    Currently extracts keyed resources.

    Future milestones may extend this parser to include:

        - Styles
        - ControlThemes
        - DataTemplates
        - Converters
        - x:Name declarations
        - Bindings
    """

    path = path.resolve()

    tree = ET.parse(path)

    root = tree.getroot()

    resources = []

    for element in root.iter():

        key = element.attrib.get(_X_KEY)

        if not key:
            continue

        #
        # Strip the XML namespace from the element name.
        #
        kind = element.tag.split("}")[-1]

        resources.append(
            AxamlResource(
                key=key,
                kind=kind,
                path=path,
            )
        )

    return AxamlDocument(
        path=path,
        resources=tuple(resources),
    )
