"""
Avalonia Hover Information

Builds human-readable hover text from
AXAML semantic context and generated Avalonia metadata.
"""

from __future__ import annotations

from .axaml_context import AxamlContext
from .binding import resolve_data_type
from .hover_metadata import (
    get_control_info,
    get_property_info,
    get_property_values,
)


def get_hover_information(
    context: AxamlContext,
    resource=None,
    csharp_index=None,
) -> str | None:
    """
    Generate human-readable hover information for an AXAML context.

    The semantic context determines which metadata provider is used.

    Resource declaration information is supplied separately by the
    workspace layer.
    """

    if context.kind == "control":
        return _hover_control(
            context
        )

    if context.kind == "property":
        return _hover_property(
            context
        )

    if context.kind == "value":
        return _hover_value(
            context
        )

    if context.kind == "binding":
        return _hover_binding(context, csharp_index)

    if context.kind == "resource":
        return _hover_resource(
            context,
            resource,
        )

    return None


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------

def _hover_binding(
    context: AxamlContext,
    csharp_index,
) -> str | None:
    if not csharp_index or not context.binding_path:
        return None

    # The hover listener supplies the resolved root type through a temporary
    # attribute when available. Keep this function useful for direct callers
    # too by accepting a fully-qualified root in resource_type.
    root_type = getattr(context, "binding_root_type", None)
    if not root_type:
        return None

    parts = context.binding_path.split(".")
    current_type = root_type
    lines = [f"# {context.binding_path}", "AXAML Binding", ""]

    for i, part in enumerate(parts):
        prop = next(
            (
                item
                for item in csharp_index.properties_for(current_type)
                if item.name.casefold() == part.casefold()
            ),
            None,
        )
        if prop is None:
            return None

        owner = prop.declaring_type
        lines.append(f"{owner}.{prop.name}")
        lines.append(f"    → {prop.type_name}")
        if i < len(parts) - 1:
            target = csharp_index.find_type(prop.type_name)
            if target is None:
                return "\n".join(lines)
            current_type = target.full_name

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------


def _hover_control(
    context: AxamlContext,
) -> str | None:
    """
    Build hover information for an Avalonia control.
    """

    if not context.token:
        return None

    info = get_control_info(
        context.token
    )

    if info is None:
        return None

    lines = [
        f"# {context.token}",
        "Avalonia Control",
    ]

    base = (
        info.get("Base")
        or info.get("base")
    )

    if base:
        lines.extend(
            (
                "",
                f"Base: {base}",
            )
        )

    namespace = (
        info.get("Namespace")
        or info.get("namespace")
    )

    if namespace:
        lines.extend(
            (
                "",
                f"Namespace: {namespace}",
            )
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------


def _hover_property(
    context: AxamlContext,
) -> str | None:
    """
    Build hover information for an Avalonia property.

    Property resolution is delegated entirely to hover_metadata.

    That keeps this layer concerned only with presentation.
    """

    if not context.property:
        return None

    if not context.control:
        return None

    info = get_property_info(
        context.control,
        context.property,
    )

    if info is None:
        return None

    name = (
        info.get("Name")
        or info.get("name")
        or context.property
    )

    kind = (
        info.get("Kind")
        or info.get("kind")
        or ""
    )

    owner = (
        info.get("Owner")
        or info.get("owner")
    )

    prop_type = (
        info.get("Type")
        or info.get("type")
    )

    inherited_from = (
        info.get("InheritedFrom")
        or info.get("inherited_from")
    )

    description = (
        info.get("Description")
        or info.get("description")
    )

    is_attached = (
        str(kind).casefold() == "attached"
        or "." in context.property
    )

    if is_attached:
        display_name = context.property
    else:
        display_name = name

    lines = [
        f"# {display_name}",
        "Avalonia Property",
    ]

    if prop_type:
        lines.append(
            f"Type: {prop_type}"
        )

    if is_attached:

        if owner:
            lines.append(
                f"Owner: {owner}"
            )

        lines.append(
            "Attached property"
        )

    elif inherited_from:

        lines.append(
            f"Declared on: {inherited_from}"
        )

        lines.append(
            f"Available on: {context.control}"
        )

    elif owner:

        lines.append(
            f"Owner: {owner}"
        )

    if description:
        lines.extend(
            (
                "",
                description,
            )
        )

    values = _get_property_values(
        context
    )

    if values:
        lines.extend(
            (
                "",
                "Values:",
            )
        )

        for value in values:
            lines.append(
                f"- {value}"
            )

    return "\n".join(lines)


def _get_property_values(
    context: AxamlContext,
) -> list[str]:
    """
    Return metadata-backed values for the current property.

    Prefer the control-aware API.

    The fallback keeps hover compatible with metadata providers that
    expose the older property-only signature.
    """

    try:
        values = get_property_values(
            context.control,
            context.property,
        )

    except TypeError:
        values = get_property_values(
            context.property
        )

    if not values:
        return []

    return [
        value
        for value in values
        if isinstance(value, str)
        and value.strip()
    ]


# ---------------------------------------------------------------------------
# Value
# ---------------------------------------------------------------------------


def _hover_value(
    context: AxamlContext,
) -> str | None:
    """
    Build hover information for a property value.
    """

    if (
        context.property in (
            "Key",
            "x:Key",
        )
        and context.value
    ):
        return _hover_resource(
            context,
            None,
        )

    if not context.property:
        return None

    if not context.value:
        return None

    values = _get_property_values(
        context
    )

    lines = [
        f"# {context.value}",
        f"Property: {context.property}",
    ]

    if values:
        lines.extend(
            (
                "",
                "Allowed values:",
            )
        )

        for value in values:
            lines.append(
                f"- {value}"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------


def _hover_resource(
    context: AxamlContext,
    resource=None,
) -> str | None:
    """
    Build hover information for an Avalonia resource.

    Resource declaration information is supplied by the workspace
    layer when available.
    """

    key = (
        context.token
        or context.value
    )

    if not key:
        return None

    lines = [
        f"# {key}",
        "Avalonia Resource",
    ]

    resource_type = getattr(
        context,
        "resource_type",
        None,
    )

    if resource_type:
        lines.append(
            f"Type: {resource_type}"
        )

    if resource is not None:

        path = getattr(
            resource,
            "path",
            None,
        )

        if path:
            lines.extend(
                (
                    "",
                    f"Declared in: {path.name}",
                )
            )

    if context.resource_kind:
        lines.append(
            f"Reference: {context.resource_kind}"
        )

    return "\n".join(lines)
