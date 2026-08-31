"""
Avalonia Hover Metadata

Provides hover-facing metadata lookup for:

    - controls
    - normal properties
    - inherited properties
    - attached properties
    - property values

Normal properties and attached properties intentionally use
separate metadata paths.

The generated metadata is authoritative.
"""

from __future__ import annotations

import json
from pathlib import Path

from .avalonia_properties import (
    KNOWN_BASES,
    _get_metadata_dir,
    _load_classes,
    _load_properties,
    get_values_for_property,
)


_ATTACHED_PROPERTY_RECORDS: list[dict] | None = None


# ---------------------------------------------------------------------------
# Control metadata
# ---------------------------------------------------------------------------

def _resolve_control(
    name: str,
) -> str | None:
    """
    Resolve an exact control name.

    Hover requires an exact metadata match. Prefix resolution belongs
    to completion, not hover.
    """

    if not name:
        return None

    target = name.strip().lower()

    if not target:
        return None

    classes = _load_classes()

    for control in classes:
        if control.lower() == target:
            return control

    return None


def get_control_info(
    control: str,
) -> dict | None:
    """
    Return generated metadata for a control.
    """

    resolved = _resolve_control(
        control
    )

    if resolved is None:
        return None

    classes = _load_classes()

    return classes.get(
        resolved
    )


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------

def _get_inheritance_chain(
    control: str,
) -> list[str]:
    """
    Build the Avalonia property-availability chain for a control.

    The generated class Base relationship is followed first, with
    KNOWN_BASES providing additional Avalonia property ownership
    relationships.
    """

    if not control:
        return []

    classes = _load_classes()

    queue = [control]
    chain = []
    visited = set()

    while queue:
        current = queue.pop(0)

        if not current:
            continue

        key = current.lower()

        if key in visited:
            continue

        visited.add(key)
        chain.append(current)

        info = classes.get(
            current
        )

        if info:
            base = (
                info.get("Base")
                or info.get("base")
            )

            if base:
                queue.append(
                    base
                )

        for extra in KNOWN_BASES.get(
            current,
            [],
        ):
            if extra.lower() not in visited:
                queue.append(
                    extra
                )

    return chain


# ---------------------------------------------------------------------------
# Attached-property metadata
# ---------------------------------------------------------------------------

def _load_attached_property_records() -> list[dict]:
    """
    Load the dedicated attached-property metadata.

    Normal properties are stored in avalonia-properties.json.

    Attached properties are stored in
    avalonia-attached-properties.json.
    """

    global _ATTACHED_PROPERTY_RECORDS

    if _ATTACHED_PROPERTY_RECORDS is not None:
        return _ATTACHED_PROPERTY_RECORDS

    path = (
        _get_metadata_dir()
        / "avalonia-attached-properties.json"
    )

    print(
        "[Avalonia][Hover] Loading attached-property metadata:",
        path,
    )

    if not path.exists():
        print(
            "[Avalonia][Hover] Attached-property metadata missing:",
            path,
        )

        _ATTACHED_PROPERTY_RECORDS = []
        return _ATTACHED_PROPERTY_RECORDS

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as stream:
            data = json.load(
                stream
            )

    except Exception as exc:
        print(
            "[Avalonia][Hover] Attached-property metadata load failed:",
            exc,
        )

        _ATTACHED_PROPERTY_RECORDS = []
        return _ATTACHED_PROPERTY_RECORDS

    if not isinstance(data, list):
        print(
            "[Avalonia][Hover] Attached-property metadata is not a list"
        )

        _ATTACHED_PROPERTY_RECORDS = []
        return _ATTACHED_PROPERTY_RECORDS

    records = []

    for item in data:
        if not isinstance(item, dict):
            continue

        owner = (
            item.get("Owner")
            or item.get("owner")
        )

        name = (
            item.get("Name")
            or item.get("name")
        )

        if not isinstance(owner, str):
            continue

        if not isinstance(name, str):
            continue

        owner = owner.strip()
        name = name.strip()

        if not owner or not name:
            continue

        if (
            name.endswith("Property")
            and len(name) > len("Property")
        ):
            name = name[:-len("Property")]

        record = dict(item)

        record["Owner"] = owner
        record["Name"] = name
        record["Kind"] = "Attached"

        records.append(
            record
        )

    _ATTACHED_PROPERTY_RECORDS = records

    print(
        "[Avalonia][Hover] Attached-property records:",
        len(records),
    )

    return _ATTACHED_PROPERTY_RECORDS


def _get_attached_property_info(
    property_name: str,
) -> dict | None:
    """
    Resolve a qualified attached property.

    Example:

        Owner.Property

    resolves to the generated record whose owner is Grid
    and whose AXAML property name is Row.
    """

    if not property_name:
        return None

    if "." not in property_name:
        return None

    owner_name, name = property_name.split(
        ".",
        1,
    )

    owner_name = owner_name.strip()
    name = name.strip()

    if not owner_name or not name:
        return None

    owner_key = owner_name.lower()
    name_key = name.lower()

    for record in _load_attached_property_records():

        owner = (
            record.get("Owner")
            or record.get("owner")
        )

        record_name = (
            record.get("Name")
            or record.get("name")
        )

        if not isinstance(owner, str):
            continue

        if not isinstance(record_name, str):
            continue

        if owner.lower() != owner_key:
            continue

        if record_name.lower() != name_key:
            continue

        result = dict(record)

        result["Owner"] = owner
        result["Name"] = (
            f"{owner}.{record_name}"
        )
        result["Kind"] = "Attached"

        return result

    print(
        "[Avalonia][Hover] Attached property not found:",
        repr(property_name),
    )

    return None


# ---------------------------------------------------------------------------
# Property metadata
# ---------------------------------------------------------------------------

def get_property_info(
    control: str,
    property_name: str,
) -> dict | None:
    """
    Return metadata for a normal or attached property.

    Normal property:

        HorizontalAlignment

    Attached property:

        Owner.Property
    """

    if not control:
        return None

    if not property_name:
        return None

    # ------------------------------------------------------------------
    # Attached properties
    # ------------------------------------------------------------------

    if "." in property_name:
        return _get_attached_property_info(
            property_name
        )

    # ------------------------------------------------------------------
    # Normal properties
    # ------------------------------------------------------------------

    resolved = _resolve_control(
        control
    )

    if resolved is None:
        return None

    target = property_name.lower()

    chain = _get_inheritance_chain(
        resolved
    )

    print(
        "[Avalonia][Hover] Property inheritance chain:",
        chain,
    )

    matches = []

    for property_info in _load_properties():

        if not isinstance(property_info, dict):
            continue

        name = (
            property_info.get("Name")
            or property_info.get("name")
        )

        if not isinstance(name, str):
            continue

        if name.lower() != target:
            continue

        owner = (
            property_info.get("Owner")
            or property_info.get("owner")
        )

        if not isinstance(owner, str):
            continue

        owner_key = owner.lower()

        if any(
            owner_key == item.lower()
            for item in chain
        ):
            matches.append(
                property_info
            )

    if not matches:
        print(
            "[Avalonia][Hover] Normal property not found:",
            repr(property_name),
            "on",
            repr(resolved),
        )

        return None

    # Prefer the declaration closest to the control in the
    # effective inheritance chain.
    selected = None

    for owner in reversed(chain):

        owner_key = owner.lower()

        for property_info in matches:

            property_owner = (
                property_info.get("Owner")
                or property_info.get("owner")
            )

            if (
                isinstance(property_owner, str)
                and property_owner.lower() == owner_key
            ):
                selected = property_info
                break

        if selected is not None:
            break

    if selected is None:
        selected = matches[0]

    result = dict(
        selected
    )

    owner = (
        result.get("Owner")
        or result.get("owner")
    )

    if (
        isinstance(owner, str)
        and owner.lower() != resolved.lower()
    ):
        result["InheritedFrom"] = owner

    return result


# ---------------------------------------------------------------------------
# Property values
# ---------------------------------------------------------------------------

def get_property_values(
    property_name: str,
) -> list[str]:
    """
    Return known values for a property.

    Qualified attached properties are passed through unchanged.
    """

    if not property_name:
        return []

    return get_values_for_property(
        "",
        property_name,
    )


def get_type_info(type_name: str) -> dict | None:
    """Resolve an AXAML object type for hover.

    Control metadata is authoritative for controls. For other Avalonia
    objects, property metadata still gives us a useful type existence check
    (for example SolidColorBrush is an owner in the generated property data).
    """
    if not type_name:
        return None
    control = get_control_info(type_name)
    if control:
        result = dict(control)
        result.setdefault("Kind", "Control")
        return result
    target = type_name.casefold()
    for item in _load_properties():
        owner = item.get("Owner") or item.get("owner")
        if isinstance(owner, str) and owner.casefold() == target:
            return {"Name": type_name, "Kind": "Avalonia Type"}
    for item in _load_attached_property_records():
        owner = item.get("Owner") or item.get("owner")
        if isinstance(owner, str) and owner.casefold() == target:
            return {"Name": type_name, "Kind": "Avalonia Type"}
    return None
