from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
import re
from pathlib import Path
from typing import Iterable

from .axaml import (
    AxamlDocument,
    AxamlResourceReference,
)

from .binding import (
    resolve_data_type,
)

from .avalonia_properties import (
    get_attached_properties,
    get_properties_for_control,
)


#
# ----------------------------------------------------------------------
# AXAML Diagnostic
# ----------------------------------------------------------------------
#


@dataclass(frozen=True, slots=True)
class AxamlDiagnostic:
    """
    A semantic diagnostic produced from an AXAML document.
    """

    path: Path

    line: int

    column: int

    severity: str

    code: str

    message: str

    source: str = "axaml"


#
# ----------------------------------------------------------------------
# Diagnostic Codes
# ----------------------------------------------------------------------
#


_UNRESOLVED_RESOURCE = "AXAML001"

_UNKNOWN_PROPERTY = "AXAML002"

_UNKNOWN_ATTACHED_PROPERTY = "AXAML003"

_BINDING_PROPERTY_NOT_FOUND = "AXAML004"


#
# ----------------------------------------------------------------------
# Resource Diagnostics
# ----------------------------------------------------------------------
#


def _resource_keys(
    resources: Iterable,
) -> set[str]:
    """
    Build a case-sensitive resource-key lookup set.
    """

    result: set[str] = set()

    for resource in resources:

        key = getattr(
            resource,
            "key",
            None,
        )

        if not isinstance(
            key,
            str,
        ):
            continue

        key = key.strip()

        if not key:
            continue

        result.add(
            key
        )

    return result


def _find_reference_location(
    reference: AxamlResourceReference,
) -> tuple[int, int]:
    """
    Return the source location stored by the AXAML parser.
    """

    try:
        line = int(
            reference.line
        )
    except (
        TypeError,
        ValueError,
    ):
        line = 1

    try:
        column = int(
            reference.column
        )
    except (
        TypeError,
        ValueError,
    ):
        column = 1

    return (
        max(1, line),
        max(1, column),
    )


def _check_resource_references(
    document: AxamlDocument,
    resources: Iterable,
) -> list[AxamlDiagnostic]:
    """
    Detect unresolved StaticResource and DynamicResource references.
    """

    available_keys = _resource_keys(
        resources
    )

    diagnostics: list[
        AxamlDiagnostic
    ] = []

    for reference in getattr(
        document,
        "references",
        (),
    ):

        if reference.key in available_keys:
            continue

        line, column = (
            _find_reference_location(
                reference
            )
        )

        diagnostics.append(
            AxamlDiagnostic(
                path=document.path,
                line=line,
                column=column,
                severity="error",
                code=_UNRESOLVED_RESOURCE,
                message=(
                    f"Unable to resolve "
                    f"{reference.kind} "
                    f"'{reference.key}'."
                ),
                source="axaml",
            )
        )

    return diagnostics


#
# ----------------------------------------------------------------------
# Source Position
# ----------------------------------------------------------------------
#


def _source_position(
    text: str,
    offset: int,
) -> tuple[int, int]:
    """
    Convert a zero-based character offset into a one-based
    line and column.
    """

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


#
# ----------------------------------------------------------------------
# AXAML Start-Tag Scanner
# ----------------------------------------------------------------------
#


def _scan_start_tags(
    text: str,
):
    """
    Yield:

        (
            tag_name,
            [
                (
                    attribute_name,
                    absolute_source_offset,
                ),
                ...
            ],
        )

    for each XML/AXAML start tag.

    This is intentionally a lexical scanner rather than an XML parser.

    ElementTree does not preserve attribute source positions, but
    diagnostics need the exact location of the misspelled property.
    """

    length = len(text)

    index = 0

    while index < length:

        if text[index] != "<":
            index += 1
            continue

        #
        # XML comment
        #

        if text.startswith(
            "<!--",
            index,
        ):

            end = text.find(
                "-->",
                index + 4,
            )

            index = (
                length
                if end < 0
                else end + 3
            )

            continue

        #
        # Processing instruction
        #

        if text.startswith(
            "<?",
            index,
        ):

            end = text.find(
                "?>",
                index + 2,
            )

            index = (
                length
                if end < 0
                else end + 2
            )

            continue

        #
        # Closing tags / declarations
        #

        if (
            text.startswith(
                "</",
                index,
            )
            or text.startswith(
                "<!",
                index,
            )
        ):

            index += 2

            continue

        tag_start = index + 1

        if tag_start >= length:
            break

        if not (
            text[tag_start].isalpha()
            or text[tag_start] == "_"
        ):

            index += 1

            continue

        #
        # Read the element name.
        #
        # IMPORTANT:
        # Do not consume whitespace here.
        #
        # This is what prevents:
        #
        #     <Button Widht="">
        #
        # from becoming the fictitious control:
        #
        #     ButtonWidht
        #

        cursor = tag_start + 1

        while (
            cursor < length
            and (
                text[cursor].isalnum()
                or text[cursor]
                in "_:-."
            )
        ):
            cursor += 1

        tag_name = text[
            tag_start:cursor
        ]

        attributes = []

        index = cursor

        while index < length:

            #
            # Skip whitespace.
            #

            while (
                index < length
                and text[index].isspace()
            ):
                index += 1

            if index >= length:
                break

            #
            # Self-closing tag.
            #

            if text.startswith(
                "/>",
                index,
            ):

                index += 2

                break

            #
            # End of normal start tag.
            #

            if text[index] == ">":

                index += 1

                break

            #
            # An unexpected character.
            #

            if not (
                text[index].isalpha()
                or text[index] == "_"
            ):

                index += 1

                continue

            #
            # Attribute name.
            #

            attribute_start = index

            index += 1

            while (
                index < length
                and (
                    text[index].isalnum()
                    or text[index]
                    in "_:.-"
                )
            ):
                index += 1

            attribute_name = text[
                attribute_start:index
            ]

            attributes.append(
                (
                    attribute_name,
                    attribute_start,
                )
            )

            #
            # Optional whitespace before '='.
            #

            while (
                index < length
                and text[index].isspace()
            ):
                index += 1

            #
            # Attribute value.
            #

            if (
                index < length
                and text[index] == "="
            ):

                index += 1

                while (
                    index < length
                    and text[index].isspace()
                ):
                    index += 1

                #
                # Quoted value.
                #

                if (
                    index < length
                    and text[index] in "\"'"
                ):

                    quote = text[index]

                    index += 1

                    while index < length:

                        if (
                            text[index]
                            == quote
                        ):

                            index += 1

                            break

                        index += 1

        yield (
            tag_name,
            attributes,
        )


#
# ----------------------------------------------------------------------
# Name Helpers
# ----------------------------------------------------------------------
#


def _local_name(
    name: str,
) -> str:
    """
    Return the local portion of a namespaced XML name.
    """

    if "}" in name:

        return name.rsplit(
            "}",
            1,
        )[1]

    return name


def _is_namespace_attribute(
    name: str,
) -> bool:
    """
    Ignore attributes belonging to XML/XAML namespaces.

    Examples:

        xmlns
        xmlns:x
        x:Name
        d:DesignWidth
        mc:Ignorable
        xml:space
    """

    lowered = name.lower()

    return (
        lowered.startswith(
            "xmlns"
        )
        or lowered.startswith(
            "x:"
        )
        or lowered.startswith(
            "d:"
        )
        or lowered.startswith(
            "mc:"
        )
        or lowered.startswith(
            "xml:"
        )
    )


#
# ----------------------------------------------------------------------
# Property Suggestions
# ----------------------------------------------------------------------
#


def _suggest_property(
    name: str,
    candidates: list[str],
) -> str | None:
    """
    Find the closest known property name.

    The threshold is deliberately conservative so ordinary AXAML
    attributes such as event handlers are not reported merely because
    they are not present in the property metadata.
    """

    matches = get_close_matches(
        name,
        candidates,
        n=1,
        cutoff=0.70,
    )

    if not matches:
        return None

    return matches[0]


#
# ----------------------------------------------------------------------
# Control Property Diagnostics
# ----------------------------------------------------------------------
#


def _check_property_diagnostics(
    document: AxamlDocument,
) -> list[AxamlDiagnostic]:
    """
    Detect likely misspelled Avalonia control properties.

    Example:

        <Button Widht="" />

    produces:

        AXAML002
        Unknown property 'Widht' on Button.
        Did you mean 'Width'?

    Only controls known by the existing Avalonia metadata are checked.
    Custom project controls therefore remain untouched until their
    metadata is available.
    """

    try:

        source = document.path.read_text(
            encoding="utf-8"
        )

    except OSError:

        return []

    diagnostics: list[
        AxamlDiagnostic
    ] = []

    for (
        control,
        attributes,
    ) in _scan_start_tags(
        source
    ):

        control = _local_name(
            control
        )

        #
        # Existing metadata is authoritative.
        #

        properties = (
            get_properties_for_control(
                control
            )
        )

        if not properties:
            continue

        property_lookup = {
            name.casefold(): name
            for name in properties
        }

        for (
            raw_name,
            offset,
        ) in attributes:

            if _is_namespace_attribute(
                raw_name
            ):
                continue

            name = _local_name(
                raw_name
            )

            #
            # Attached property:
            #
            #     Owner.Property
            #
            if "." in name:

                owner, property_name = (
                    name.split(
                        ".",
                        1,
                    )
                )

                attached = (
                    get_attached_properties(
                        owner
                    )
                )

                #
                # Unknown attached-property owners
                # are left alone. They may belong to
                # application-specific controls.
                #

                if not attached:
                    continue

                attached_lookup = {
                    value.casefold()
                    for value in attached
                }

                if (
                    property_name.casefold()
                    in attached_lookup
                ):
                    continue

                suggestion = (
                    _suggest_property(
                        property_name,
                        attached,
                    )
                )

                if suggestion is None:
                    continue

                line, column = (
                    _source_position(
                        source,
                        offset,
                    )
                )

                diagnostics.append(
                    AxamlDiagnostic(
                        path=document.path,
                        line=line,
                        column=column,
                        severity="error",
                        code=(
                            _UNKNOWN_ATTACHED_PROPERTY
                        ),
                        message=(
                            f"Unknown attached "
                            f"property "
                            f"'{owner}.{property_name}'. "
                            f"Did you mean "
                            f"'{owner}.{suggestion}'?"
                        ),
                        source="axaml",
                    )
                )

                continue

            #
            # Known normal property.
            #

            if (
                name.casefold()
                in property_lookup
            ):
                continue

            #
            # Unknown attribute.
            #
            # Only report it when it is sufficiently close
            # to a known property. This prevents ordinary
            # events and application-specific attributes from
            # becoming false errors.
            #

            suggestion = (
                _suggest_property(
                    name,
                    properties,
                )
            )

            if suggestion is None:
                continue

            line, column = (
                _source_position(
                    source,
                    offset,
                )
            )

            diagnostics.append(
                AxamlDiagnostic(
                    path=document.path,
                    line=line,
                    column=column,
                    severity="error",
                    code=_UNKNOWN_PROPERTY,
                    message=(
                        f"Unknown property "
                        f"'{name}' on "
                        f"{control}. "
                        f"Did you mean "
                        f"'{suggestion}'?"
                    ),
                    source="axaml",
                )
            )

    return diagnostics


_BINDING_RE = re.compile(
    r"\{(?:Binding|CompiledBinding|ReflectionBinding)\b(?P<body>[^{}]*)\}",
    re.IGNORECASE,
)


def _binding_path_matches(body: str):
    return re.finditer(
        r"(?:^|[\s,])(?:Path\s*=\s*)?(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)",
        body,
        re.IGNORECASE,
    )


def _binding_diagnostics(
    document: AxamlDocument,
    source: str,
    csharp_index,
) -> list[AxamlDiagnostic]:
    if csharp_index is None:
        return []

    root_type = resolve_data_type(
        source,
        document.path,
        csharp_index=csharp_index,
    )

    if not root_type:
        return []

    diagnostics: list[AxamlDiagnostic] = []

    for match in _BINDING_RE.finditer(source):
        body = match.group("body")
        body_start = match.start("body")
        candidates = list(_binding_path_matches(body))
        if not candidates:
            continue

        selected = None
        binding_parameters = {
            "mode",
            "source",
            "elementname",
            "relativesource",
            "converter",
            "converterparameter",
            "updatesourcetrigger",
            "priority",
            "fallbackvalue",
            "targetnullvalue",
            "stringformat",
            "twoway",
            "oneway",
            "onetime",
            "default",
            "propertychanged",
        }
        for candidate in candidates:
            token = candidate.group("path")
            if token.casefold() in binding_parameters:
                continue
            selected = candidate
            break

        if selected is None:
            continue

        raw_path = selected.group("path")
        path_start = body_start + selected.start("path")

        current_type = root_type
        parts = raw_path.split(".")

        for index, part in enumerate(parts):
            properties = csharp_index.properties_for(current_type)
            prop = next(
                (item for item in properties if item.name.casefold() == part.casefold()),
                None,
            )

            if prop is None:
                suggestions = [item.name for item in properties]
                suggestion = get_close_matches(
                    part,
                    suggestions,
                    n=1,
                    cutoff=0.60,
                )
                message = (
                    f"Binding property '{part}' was not found "
                    f"on {current_type}."
                )
                if suggestion:
                    message += f" Did you mean '{suggestion[0]}'?"

                line, column = _source_position(
                    source,
                    path_start + sum(len(value) + 1 for value in parts[:index]),
                )
                diagnostics.append(
                    AxamlDiagnostic(
                        path=document.path,
                        line=line,
                        column=column,
                        severity="error",
                        code=_BINDING_PROPERTY_NOT_FOUND,
                        message=message,
                        source="axaml",
                    )
                )
                break

            next_type = prop.type_name
            resolved = csharp_index.find_type(next_type)
            if resolved is None:
                break
            current_type = resolved.full_name

    return diagnostics


#
# ----------------------------------------------------------------------
# Public Diagnostic Builder
# ----------------------------------------------------------------------
#


def build_axaml_diagnostics(
    document: AxamlDocument,
    resources: Iterable,
    csharp_index=None,
) -> list[AxamlDiagnostic]:
    """
    Build all semantic AXAML diagnostics for one document.

    Existing resource diagnostics remain unchanged. Control-property
    diagnostics are added alongside them.
    """

    if document is None:
        return []

    if not isinstance(
        document,
        AxamlDocument,
    ):
        return []

    if resources is None:
        resources = ()

    result = (
        _check_resource_references(
            document,
            resources,
        )
    )

    result.extend(
        _check_property_diagnostics(
            document
        )
    )

    try:
        source = document.path.read_text(encoding="utf-8")
    except OSError:
        source = ""

    result.extend(
        _binding_diagnostics(
            document,
            source,
            csharp_index,
        )
    )

    result.sort(
        key=lambda diagnostic: (
            str(
                diagnostic.path
            ).lower(),
            diagnostic.line,
            diagnostic.column,
            diagnostic.code,
            diagnostic.message,
        )
    )

    return result


#
# ----------------------------------------------------------------------
# Multiple Documents
# ----------------------------------------------------------------------
#


def build_project_axaml_diagnostics(
    documents: Iterable[
        AxamlDocument
    ],
    resources: Iterable,
    csharp_index=None,
) -> list[AxamlDiagnostic]:
    """
    Build semantic diagnostics for multiple AXAML documents.
    """

    if documents is None:
        return []

    result: list[
        AxamlDiagnostic
    ] = []

    for document in documents:

        result.extend(
            build_axaml_diagnostics(
                document,
                resources,
                csharp_index=csharp_index,
            )
        )

    result.sort(
        key=lambda diagnostic: (
            str(
                diagnostic.path
            ).lower(),
            diagnostic.line,
            diagnostic.column,
            diagnostic.code,
            diagnostic.message,
        )
    )

    return result
