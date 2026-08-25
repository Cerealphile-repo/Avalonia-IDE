"""
AXAML Semantic Context

Provides reusable cursor context detection for Avalonia files.

This module does not interact with Sublime Text.
It does not load metadata.
It only determines what AXAML element, property,
value, or resource the cursor is currently inside.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class AxamlContext:
    """
    Semantic location inside AXAML.
    """

    kind: str | None = None

    control: str | None = None
    property: str | None = None
    value: str | None = None

    token: str | None = None

    resource_kind: str | None = None
    resource_type: str | None = None
    binding_path: str | None = None
    binding_root_type: str | None = None


def get_axaml_context(
    text: str,
    point: int | None = None,
) -> AxamlContext:
    """
    Determine the semantic context at a cursor location.

    Parameters:
        text:
            Complete AXAML text.

        point:
            Cursor position.
            If omitted, assumes end of text.

    Returns:
        AxamlContext
    """

    if point is None:
        point = len(text)

    point = max(
        0,
        min(point, len(text)),
    )

    before = text[:point]

    # --------------------------------------------------
    # RESOURCE
    #
    # Examples:
    #
    # Background="{StaticResource PrimaryBrush}"
    #                         ^^^^^^^^^^^
    #
    # Background="{DynamicResource PrimaryBrush}"
    #                         ^^^^^^^^^^^
    #
    # The cursor may be anywhere inside the resource key.
    # --------------------------------------------------

    resource_pattern = re.compile(
        r'\{(StaticResource|DynamicResource)\s+([^\s}"\']+)'
    )

    for match in resource_pattern.finditer(text):

        key_start = match.start(2)
        key_end = match.end(2)

        if key_start <= point <= key_end:

            resource_kind = match.group(1)
            token = match.group(2)

            control = _get_current_control(
                before
            )

            prop = _get_current_property(
                before
            )

            return AxamlContext(
                kind="resource",
                control=control,
                property=prop,
                value=token,
                token=token,
                resource_kind=resource_kind,
            )

    # --------------------------------------------------
    # --------------------------------------------------
    # BINDING
    # --------------------------------------------------

    binding_pattern = re.compile(
        r"\{(?:Binding|CompiledBinding|ReflectionBinding)\b[^{}]*?\b(?:Path\s*=\s*)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)",
        re.IGNORECASE,
    )

    for match in binding_pattern.finditer(text):
        start = match.start(1)
        end = match.end(1)
        if start <= point <= end:
            value = match.group(1)
            return AxamlContext(
                kind="binding",
                control=_get_current_control(before),
                value=value,
                token=value.rsplit(".", 1)[-1],
                binding_path=value,
            )

    # VALUE
    #
    # Example:
    #
    # <Button Background="Re|
    #
    # --------------------------------------------------

    value_match = re.search(
        r'(\w+)\s*=\s*"([^"]*)$',
        before,
    )

    if value_match:

        prop = value_match.group(1)
        value = value_match.group(2)

        control = _get_current_control(
            before
        )

        token = value

        return AxamlContext(
            kind="value",
            control=control,
            property=prop,
            value=value,
            token=token,
        )

    # --------------------------------------------------
    # PROPERTY
    #
    # Example:
    #
    # <Button Back|
    #
    # --------------------------------------------------

    tag_match = re.search(
        r'<(\w+)([^<>]*)$',
        before,
    )

    if tag_match:

        control = tag_match.group(1)
        attributes = tag_match.group(2)

        if '"' not in attributes:

            property_match = re.search(
                r'(\w+)$',
                attributes,
            )

            token = (
                property_match.group(1)
                if property_match
                else None
            )

            return AxamlContext(
                kind="property",
                control=control,
                property=token,
                token=token,
            )

    # --------------------------------------------------
    # CONTROL
    #
    # Example:
    #
    # <But|
    #
    # --------------------------------------------------

    control_match = re.search(
        r'<(\w*)$',
        before,
    )

    if control_match:

        token = control_match.group(1)

        return AxamlContext(
            kind="control",
            token=token,
        )

    return AxamlContext()


def _get_current_control(
    text: str,
) -> str | None:
    """
    Find the nearest opening AXAML element.
    """

    matches = re.findall(
        r'<(\w+)',
        text,
    )

    if not matches:
        return None

    return matches[-1]


def _get_current_property(
    text: str,
) -> str | None:
    """
    Find the attribute containing the current value.
    """

    match = re.search(
        r'(\w+)\s*=\s*"[^"]*$',
        text,
    )

    if match:
        return match.group(1)

    return None
