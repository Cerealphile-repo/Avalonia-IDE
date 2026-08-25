"""
Avalonia AXAML Parser

Parses a single Avalonia .axaml document into immutable metadata
objects.

This module performs XML parsing only.

It does not:

    - walk the filesystem
    - discover project files
    - build workspace indexes
    - resolve resource scope
    - resolve types
    - interact with Sublime Text
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .log import log


#
# ----------------------------------------------------------------------
# Resource Metadata
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class AxamlResource:
    """
    A keyed resource declared in an AXAML document.

    Line and column are one-based source positions identifying the
    beginning of the resource key.
    """

    key: str

    kind: str

    path: Path

    line: int = 1

    column: int = 1


#
# ----------------------------------------------------------------------
# Resource Reference Metadata
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class AxamlResourceReference:
    """
    A reference to a keyed resource used by an AXAML document.

    The reference kind is currently one of:

        - StaticResource
        - DynamicResource

    Line and column are one-based source positions identifying the
    beginning of the resource expression.
    """

    key: str

    kind: str

    path: Path

    line: int

    column: int


#
# ----------------------------------------------------------------------
# AXAML Element Metadata
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class AxamlElement:
    """
    An element in the AXAML document tree.

    The parser records only structural information at this stage.
    Type resolution and semantic interpretation are intentionally
    left to higher layers.

    ``line`` and ``column`` identify the beginning of the opening
    element tag. ``name_line`` and ``name_column`` identify the first
    character of an ``x:Name`` value when one is present.

    ``parent_index`` refers to another element in the containing
    ``AxamlDocument.elements`` tuple. The root element has no parent.
    """

    type_name: str

    path: Path

    line: int

    column: int

    x_name: Optional[str] = None

    name_line: Optional[int] = None

    name_column: Optional[int] = None

    parent_index: Optional[int] = None


#
# ----------------------------------------------------------------------
# AXAML Document
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class AxamlDocument:
    """
    Immutable semantic metadata extracted from one AXAML document.
    """

    path: Path

    resources: Tuple[AxamlResource, ...]

    references: Tuple[AxamlResourceReference, ...]

    elements: Tuple[AxamlElement, ...] = ()


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

_X_NAME = (
    f"{{{_XAML_NAMESPACE}}}Name"
)


#
# ----------------------------------------------------------------------
# Source Helpers
# ----------------------------------------------------------------------
#


_RESOURCE_REFERENCE_RE = re.compile(
    r"\{"
    r"(?P<kind>StaticResource|DynamicResource)"
    r"\s+"
    r"(?P<key>[^{}]+?)"
    r"\}"
)


_ELEMENT_START_RE = re.compile(
    r"<"
    r"(?!(?:[/!?]))"
    r"(?P<tag>[A-Za-z_][\w.:-]*)"
    r"(?=\s|/?>)"
)


_ELEMENT_NAME_RE = re.compile(
    r"""
    \bx:Name
    \s*=\s*
    (?P<quote>["'])
    (?P<name>.*?)
    (?P=quote)
    """,
    re.VERBOSE,
)


_RESOURCE_KEY_RE = re.compile(
    r"""
    (?P<attribute>
        \bx:Key
        |
        \{\s*
        [^}]+
        \}\s*Key
    )
    \s*=\s*
    (?P<quote>["'])
    (?P<key>.*?)
    (?P=quote)
    """,
    re.VERBOSE,
)


def _source_position(
    text: str,
    offset: int,
) -> tuple[int, int]:
    """
    Convert a zero-based character offset into a one-based
    line/column position.
    """

    if offset < 0:
        offset = 0

    if offset > len(text):
        offset = len(text)

    line = (
        text.count(
            "\n",
            0,
            offset,
        )
        + 1
    )

    last_newline = text.rfind(
        "\n",
        0,
        offset,
    )

    if last_newline < 0:
        column = offset + 1
    else:
        column = (
            offset
            - last_newline
        )

    return (
        line,
        column,
    )


def _find_resource_reference_positions(
    text: str,
) -> list[tuple[str, str, int, int]]:
    """
    Find StaticResource and DynamicResource expressions directly
    in the original AXAML source.

    Returns:

        (kind, key, line, column)

    for each discovered expression.

    The returned line and column identify the opening ``{``.
    """

    result: list[
        tuple[str, str, int, int]
    ] = []

    for match in _RESOURCE_REFERENCE_RE.finditer(
        text
    ):

        kind = match.group(
            "kind"
        )

        key = match.group(
            "key"
        ).strip()

        if not key:
            continue

        line, column = _source_position(
            text,
            match.start(),
        )

        result.append(
            (
                kind,
                key,
                line,
                column,
            )
        )

    return result


def _find_element_positions(
    text: str,
) -> list[tuple[int, int]]:
    """
    Find the source position of each opening AXAML element tag.

    XML parsing determines which elements actually exist. The original
    source supplies one position per element in document order.
    """

    return [
        _source_position(
            text,
            match.start(),
        )
        for match in _ELEMENT_START_RE.finditer(text)
    ]


def _find_element_name_positions(
    text: str,
) -> list[tuple[str, int, int]]:
    """
    Find x:Name values directly in the original AXAML source.

    Returns ``(name, line, column)`` where line and column identify the
    first character of the name value. Source order is preserved so
    names can be matched deterministically with XML elements.
    """

    result: list[tuple[str, int, int]] = []

    for match in _ELEMENT_NAME_RE.finditer(text):

        name = match.group("name").strip()

        if not name:
            continue

        name_start = match.start("name")

        leading_whitespace = (
            len(match.group("name"))
            - len(match.group("name").lstrip())
        )

        name_start += leading_whitespace

        line, column = _source_position(
            text,
            name_start,
        )

        result.append(
            (
                name,
                line,
                column,
            )
        )

    return result


def _find_resource_declaration_positions(
    text: str,
) -> list[tuple[str, int, int]]:
    """
    Find x:Key resource declarations directly in the original
    AXAML source.

    Returns:

        (key, line, column)

    for each discovered declaration.

    The returned line and column identify the first character of
    the resource key value.

    Source order is preserved so duplicate resource keys can be
    matched deterministically with the XML resource declarations.
    """

    result: list[
        tuple[str, int, int]
    ] = []

    for match in _RESOURCE_KEY_RE.finditer(
        text
    ):

        key = match.group(
            "key"
        ).strip()

        if not key:
            continue

        key_start = match.start(
            "key"
        )

        leading_whitespace = (
            len(
                match.group(
                    "key"
                )
            )
            - len(
                match.group(
                    "key"
                ).lstrip()
            )
        )

        key_start += leading_whitespace

        line, column = _source_position(
            text,
            key_start,
        )

        result.append(
            (
                key,
                line,
                column,
            )
        )

    return result


#
# ----------------------------------------------------------------------
# XML Helpers
# ----------------------------------------------------------------------
#


def _local_name(
    tag: str,
) -> str:
    """
    Return the local name of an XML tag.

    ElementTree represents namespaced tags as:

        {namespace}Name

    Plain tags are returned unchanged.
    """

    if "}" not in tag:
        return tag

    return tag.rsplit(
        "}",
        1,
    )[1]


def _resource_key(
    element: ET.Element,
) -> Optional[str]:
    """
    Return the x:Key value declared on an element.

    Empty keys are ignored.
    """

    key = element.attrib.get(
        _X_KEY
    )

    if key is None:
        return None

    key = key.strip()

    if not key:
        return None

    return key




def _element_name(
    element: ET.Element,
) -> Optional[str]:
    """
    Return the x:Name value declared on an element.

    Empty names are ignored.
    """

    name = element.attrib.get(
        _X_NAME
    )

    if name is None:
        return None

    name = name.strip()

    if not name:
        return None

    return name


#
# ----------------------------------------------------------------------
# AXAML Element Extraction
# ----------------------------------------------------------------------
#


def _extract_elements(
    root: ET.Element,
    path: Path,
    source_text: str,
) -> list[AxamlElement]:
    """
    Extract the structural AXAML element tree.

    XML parsing determines element order and parent/child structure.
    The original source supplies precise positions for opening tags and
    x:Name values.
    """

    element_positions = _find_element_positions(
        source_text
    )

    name_positions = _find_element_name_positions(
        source_text
    )

    elements: list[AxamlElement] = []

    position_index = 0
    name_index = 0

    def visit(
        element: ET.Element,
        parent_index: Optional[int],
    ) -> None:
        nonlocal position_index
        nonlocal name_index

        if position_index < len(element_positions):

            line, column = element_positions[position_index]

        else:

            line, column = (1, 1)

        position_index += 1

        x_name = _element_name(element)

        name_line: Optional[int] = None
        name_column: Optional[int] = None

        if x_name is not None:

            while name_index < len(name_positions):

                candidate_name, candidate_line, candidate_column = (
                    name_positions[name_index]
                )
                name_index += 1

                if candidate_name == x_name:

                    name_line = candidate_line
                    name_column = candidate_column
                    break

        element_index = len(elements)

        elements.append(
            AxamlElement(
                type_name=_local_name(element.tag),
                path=path,
                line=line,
                column=column,
                x_name=x_name,
                name_line=name_line,
                name_column=name_column,
                parent_index=parent_index,
            )
        )

        for child in element:
            visit(
                child,
                element_index,
            )

    visit(
        root,
        None,
    )

    return elements


#
# ----------------------------------------------------------------------
# Empty Document
# ----------------------------------------------------------------------
#


def _empty_document(
    path: Path,
) -> AxamlDocument:
    """
    Return an empty semantic document for an unreadable or invalid file.
    """

    return AxamlDocument(
        path=path,
        resources=(),
        references=(),
        elements=(),
    )


#
# ----------------------------------------------------------------------
# Resource Reference Parsing
# ----------------------------------------------------------------------
#


def _parse_resource_reference(
    value: str,
    path: Path,
    line: int,
    column: int,
) -> Optional[AxamlResourceReference]:
    """
    Parse a StaticResource or DynamicResource expression.

    Supported forms are:

        {StaticResource Key}
        {DynamicResource Key}

    Values that are not resource expressions are ignored.
    """

    value = value.strip()

    for kind in (
        "StaticResource",
        "DynamicResource",
    ):

        prefix = (
            "{"
            + kind
            + " "
        )

        if not value.startswith(prefix):
            continue

        if not value.endswith("}"):
            continue

        key = value[
            len(prefix):-1
        ].strip()

        if not key:
            return None

        return AxamlResourceReference(
            key=key,
            kind=kind,
            path=path,
            line=line,
            column=column,
        )

    return None


#
# ----------------------------------------------------------------------
# Resource Extraction
# ----------------------------------------------------------------------
#


def _extract_resources(
    root: ET.Element,
    path: Path,
    source_text: str,
) -> list[AxamlResource]:
    """
    Extract keyed resource declarations from an XML tree.

    XML parsing determines the actual resource declarations.

    The original source text supplies precise source positions for
    the corresponding x:Key values.
    """

    resources: list[AxamlResource] = []

    positions = _find_resource_declaration_positions(
        source_text
    )

    position_map: dict[
        str,
        list[tuple[int, int]],
    ] = {}

    for key, line, column in positions:

        position_map.setdefault(
            key,
            [],
        ).append(
            (
                line,
                column,
            )
        )

    for element in root.iter():

        key = _resource_key(
            element
        )

        if key is None:
            continue

        locations = position_map.get(
            key,
            [],
        )

        if locations:

            line, column = locations.pop(
                0
            )

        else:

            line, column = (
                1,
                1,
            )

        resources.append(
            AxamlResource(
                key=key,
                kind=_local_name(
                    element.tag
                ),
                path=path,
                line=line,
                column=column,
            )
        )

    resources.sort(
        key=lambda resource: (
            resource.key.casefold(),
            resource.kind.casefold(),
            resource.line,
            resource.column,
        )
    )

    return resources


#
# ----------------------------------------------------------------------
# Resource Reference Extraction
# ----------------------------------------------------------------------
#


def _extract_references(
    root: ET.Element,
    path: Path,
    source_text: str,
) -> list[AxamlResourceReference]:

    """
    Extract StaticResource and DynamicResource references from XML
    attribute values.

    XML parsing determines which values are valid AXAML attributes.

    The original source text supplies precise positions for the
    resource expressions.
    """

    references: list[
        AxamlResourceReference
    ] = []

    positions = _find_resource_reference_positions(
        source_text
    )

    position_map: dict[
        tuple[str, str],
        list[tuple[int, int]],
    ] = {}

    for kind, key, line, column in positions:

        position_map.setdefault(
            (
                kind,
                key,
            ),
            [],
        ).append(
            (
                line,
                column,
            )
        )

    for element in root.iter():

        for value in element.attrib.values():

            value = value.strip()

            for kind in (
                "StaticResource",
                "DynamicResource",
            ):

                prefix = (
                    "{"
                    + kind
                    + " "
                )

                if not value.startswith(
                    prefix
                ):
                    continue

                if not value.endswith(
                    "}"
                ):
                    continue

                key = value[
                    len(prefix):-1
                ].strip()

                if not key:
                    continue

                locations = position_map.get(
                    (
                        kind,
                        key,
                    ),
                    [],
                )

                if locations:

                    line, column = locations.pop(
                        0
                    )

                else:

                    line, column = (
                        1,
                        1,
                    )

                reference = _parse_resource_reference(
                    value,
                    path,
                    line,
                    column,
                )

                if reference is None:
                    continue

                references.append(
                    reference
                )

    references.sort(
        key=lambda reference: (
            reference.key.casefold(),
            reference.kind.casefold(),
            reference.line,
            reference.column,
        )
    )

    return references


#
# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------
#


def parse_axaml(
    path: Path,
) -> AxamlDocument:

    """
    Parse one AXAML document.

    The parser extracts:

        - keyed resource declarations
        - StaticResource references
        - DynamicResource references
        - source positions for resource declarations
        - source positions for resource references

    Invalid or temporarily incomplete AXAML produces an empty
    document rather than breaking workspace indexing.
    """

    path = path.resolve()

    try:

        source_text = path.read_text(
            encoding="utf-8"
        )

    except OSError as error:

        log.warning(
            "Unable to read AXAML: "
            f"{path.name} ({error})"
        )

        return _empty_document(
            path
        )

    # An empty (or whitespace-only) AXAML document is a normal editing
    # state, not a malformed document.  In particular, a newly-created
    # .axaml file is commonly empty while the user starts typing.  Treat
    # it as an empty semantic document without emitting a diagnostic.
    if not source_text.strip():

        return _empty_document(
            path
        )

    try:

        root = ET.fromstring(
            source_text
        )

    except ET.ParseError as error:

        log.warning(
            "Unable to parse AXAML: "
            f"{path.name} ({error})"
        )

        return _empty_document(
            path
        )

    elements = _extract_elements(
        root,
        path,
        source_text,
    )

    resources = _extract_resources(
        root,
        path,
        source_text,
    )

    references = _extract_references(
        root,
        path,
        source_text,
    )

    return AxamlDocument(
        path=path,
        resources=tuple(
            resources
        ),
        references=tuple(
            references
        ),
        elements=tuple(
            elements
        ),
    )
