from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Any

from .log import log


# Caches
_PROPERTIES: List[Dict[str, Any]] | None = None
_ATTACHED_PROPERTIES: Dict[str, List[str]] | None = None
_CLASSES: Dict[str, Dict[str, Any]] | None = None
_VALUES: Dict[str, List[str]] | None = None


# Avalonia property ownership relationships.
KNOWN_BASES: Dict[str, List[str]] = {
    "Control": [
        "Layoutable",
    ],
    "InputElement": [
        "Visual",
    ],
}


def _get_metadata_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "metadata" / "completion"


def _load_properties() -> List[Dict[str, Any]]:
    """Load normal Avalonia property metadata only."""
    global _PROPERTIES

    if _PROPERTIES is not None:
        return _PROPERTIES

    path = _get_metadata_dir() / "avalonia-properties.json"

    log.debug(f"MODULE: {Path(__file__).resolve()}")
    log.debug(f"METADATA DIR: {path.parent}")
    log.debug(f"PROPERTY FILE: {path}")
    log.debug(f"PROPERTY FILE EXISTS: {path.exists()}")

    if not path.exists():
        _PROPERTIES = []
        return _PROPERTIES

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.error(f"JSON ERROR: {e!r}")
        _PROPERTIES = []
        return _PROPERTIES

    log.debug(f"JSON TYPE: {type(data).__name__}")

    if not isinstance(data, list):
        _PROPERTIES = []
        return _PROPERTIES

    properties: List[Dict[str, Any]] = []

    for prop in data:
        if not isinstance(prop, dict):
            continue

        # The normal-property file is authoritative for normal properties.
        # Do not import attached records from another/legacy representation.
        if str(prop.get("Kind", "Normal")).lower() == "attached":
            continue

        name = prop.get("Name") or prop.get("name")
        owner = prop.get("Owner") or prop.get("owner")

        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(owner, str) or not owner.strip():
            continue

        properties.append({
            **prop,
            "Name": name.strip(),
            "Owner": owner.strip(),
        })

    _PROPERTIES = properties

    log.debug(
        f"LOADED NORMAL PROPERTIES: {len(_PROPERTIES)}"
    )
    return _PROPERTIES


def _normalize_attached_name(name: str) -> str:
    """Convert generated CLR backing names such as RowProperty to AXAML Row."""
    name = name.strip()
    if name.endswith("Property") and len(name) > len("Property"):
        return name[:-len("Property")]
    return name


def _load_attached_properties() -> Dict[str, List[str]]:
    """Load the dedicated generated attached-property metadata file."""
    global _ATTACHED_PROPERTIES

    if _ATTACHED_PROPERTIES is not None:
        return _ATTACHED_PROPERTIES

    path = _get_metadata_dir() / "avalonia-attached-properties.json"

    log.debug(f"ATTACHED PROPERTY FILE: {path}")
    log.debug(f"ATTACHED PROPERTY FILE EXISTS: {path.exists()}")

    if not path.exists():
        _ATTACHED_PROPERTIES = {}
        return _ATTACHED_PROPERTIES

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.error(f"ATTACHED JSON ERROR: {e!r}")
        _ATTACHED_PROPERTIES = {}
        return _ATTACHED_PROPERTIES

    if not isinstance(data, list):
        log.debug(
            f"ATTACHED JSON TYPE: {type(data).__name__}"
        )
        _ATTACHED_PROPERTIES = {}
        return _ATTACHED_PROPERTIES

    result: Dict[str, List[str]] = {}
    seen: Dict[str, set[str]] = {}

    for prop in data:
        if not isinstance(prop, dict):
            continue

        owner = prop.get("Owner") or prop.get("owner")
        name = prop.get("Name") or prop.get("name")

        if not isinstance(owner, str) or not owner.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue

        owner = owner.strip()
        name = _normalize_attached_name(name)
        if not name:
            continue

        owner_seen = seen.setdefault(owner.lower(), set())
        if name.lower() in owner_seen:
            continue
        owner_seen.add(name.lower())
        result.setdefault(owner, []).append(name)

    for names in result.values():
        names.sort(key=str.lower)

    _ATTACHED_PROPERTIES = result

    log.debug(
        "LOADED ATTACHED PROPERTIES: "
        f"{sum(len(v) for v in result.values())} "
        f"owners: {len(result)}"
    )
    return _ATTACHED_PROPERTIES


def get_attached_owners(prefix: str = "") -> List[str]:
    p = (prefix or "").lower()
    return sorted(
        [
            owner
            for owner in _load_attached_properties()
            if not p or owner.lower().startswith(p)
        ],
        key=str.lower,
    )


def get_attached_properties(
    owner: str,
    prefix: str = "",
) -> List[str]:
    if not owner:
        return []

    target = owner.lower()
    names: List[str] = []

    for actual_owner, properties in _load_attached_properties().items():
        if actual_owner.lower() == target:
            names = properties
            break

    p = (prefix or "").lower()
    if p:
        names = [
            name
            for name in names
            if name.lower().startswith(p)
        ]

    return list(names)


def _load_classes() -> Dict[str, Dict[str, Any]]:
    global _CLASSES

    if _CLASSES is not None:
        return _CLASSES

    path = _get_metadata_dir() / "avalonia-classes.json"

    if not path.exists():
        _CLASSES = {}
        return _CLASSES

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        classes = {}
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = item.get("Name")
                if name:
                    classes[name] = item
        _CLASSES = classes
    except Exception as e:
        log.error(
            f"CLASS JSON ERROR: {e!r}"
        )
        _CLASSES = {}

    return _CLASSES


def _load_values() -> Dict[str, List[str]]:
    global _VALUES

    if _VALUES is not None:
        return _VALUES

    path = _get_metadata_dir() / "avalonia-values.json"

    if not path.exists():
        _VALUES = {}
        return _VALUES

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _VALUES = data if isinstance(data, dict) else {}
    except Exception:
        _VALUES = {}

    return _VALUES


def _get_class_chain(control_name: str) -> List[str]:
    classes = _load_classes()
    chain: List[str] = []
    queue = [control_name]
    visited = set()

    while queue:
        current = queue.pop(0)
        if not current or current in visited:
            continue
        visited.add(current)
        chain.append(current)

        info = classes.get(current)
        if info:
            base = info.get("Base", "")
            if base:
                queue.append(base)

        for extra in KNOWN_BASES.get(current, []):
            if extra not in visited:
                queue.append(extra)

    return chain


def _get_properties_for_owner(owner: str) -> List[str]:
    result = []
    for prop in _load_properties():
        if prop.get("Owner") != owner:
            continue
        name = prop.get("Name")
        if name:
            result.append(name)
    return result


def get_properties_for_control(
    control_name: str,
) -> List[str]:
    """Return normal properties available to a control."""
    if not control_name:
        return []

    result = []
    seen = set()
    chain = _get_class_chain(control_name)

    log.debug(
        f"CLASS CHAIN: {control_name} -> {chain}"
    )

    for cls in chain:
        owner_properties = _get_properties_for_owner(cls)

        log.debug(
            f"OWNER: {cls} "
            f"PROPERTIES: {len(owner_properties)}"
        )

        for prop in owner_properties:
            if prop not in seen:
                seen.add(prop)
                result.append(prop)

    log.debug(
        f"RESULT: {control_name} {len(result)}"
    )

    return result


def get_values_for_property(
    control_name: str,
    property_name: str,
) -> List[str]:
    if not property_name:
        return []

    values = _load_values()
    if property_name in values:
        return values[property_name]

    if "." in property_name:
        _, prop = property_name.split(".", 1)
        return values.get(prop, [])

    return []
