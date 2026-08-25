"""
Avalonia Completion Metadata

Loads the generated Avalonia reflection metadata.

Actual generated formats:

    avalonia-classes.json
        [
            {"Name": "...", "Base": "..."},
            ...
        ]

    avalonia-properties.json
        [
            {
                "Name": "...",
                "Type": "...",
                "Owner": "...",
                "Kind": "Normal"
            },
            ...
        ]

    avalonia-values.json
        {
            "PropertyName": ["Value1", "Value2", ...],
            ...
        }

    avalonia-attached-properties.json
        [
            {
                "Name": "...",
                "Type": "...",
                "Owner": "...",
                "Kind": "Attached"
            },
            ...
        ]

The index deliberately accepts both the current generated format and
dictionary/list variants so metadata generation can evolve without
breaking the Sublime plugin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from .log import log


@dataclass
class PropertyMetadata:
    name: str
    type: str | None = None
    declaring_type: str | None = None
    description: str | None = None
    default: str | None = None
    values: list[str] = field(default_factory=list)


@dataclass
class EventMetadata:
    name: str
    declaring_type: str | None = None
    description: str | None = None


@dataclass
class ControlMetadata:
    name: str
    properties: dict[str, PropertyMetadata] = field(default_factory=dict)
    events: dict[str, EventMetadata] = field(default_factory=dict)


KNOWN_BASES: dict[str, tuple[str, ...]] = {
    # The generated class metadata intentionally remains the authoritative
    # 524-control universe. These supplemental relationships mirror the
    # existing property completion behavior without creating synthetic
    # controls for Layoutable or Visual.
    "Control": ("Layoutable",),
    "InputElement": ("Visual",),
}


@dataclass
class CompletionMetadataIndex:
    controls: dict[str, ControlMetadata] = field(default_factory=dict)
    inheritance: dict[str, str | None] = field(default_factory=dict)
    attached_properties: dict[str, dict[str, PropertyMetadata]] = field(
        default_factory=dict
    )
    property_owners: dict[str, dict[str, PropertyMetadata]] = field(
        default_factory=dict
    )

    def normalize_name(self, name: str | None) -> str:
        if not name:
            return ""
        return str(name).split(".")[-1]

    def ensure_control(self, name: str) -> ControlMetadata:
        normalized = self.normalize_name(name)

        existing = self.get_control(normalized)
        if existing is not None:
            return existing

        control = ControlMetadata(name=normalized)
        self.controls[normalized] = control
        return control

    def get_control(self, name: str | None) -> ControlMetadata | None:
        if not name:
            return None

        normalized = self.normalize_name(name)
        target = normalized.lower()

        for key, value in self.controls.items():
            if key.lower() == target:
                return value

        return None

    def get_base_type(self, name: str | None) -> str | None:
        if not name:
            return None

        normalized = self.normalize_name(name)
        target = normalized.lower()

        for key, value in self.inheritance.items():
            if key.lower() == target:
                return self.normalize_name(value) if value else None

        return None

    def get_inheritance_chain(self, name: str) -> list[str]:
        result: list[str] = []
        visited: set[str] = set()
        queue = [self.normalize_name(name)]

        while queue:
            current = queue.pop(0)

            if not current:
                continue

            key = current.lower()

            if key in visited:
                continue

            visited.add(key)
            result.append(current)

            base = self.get_base_type(current)
            if base:
                queue.append(base)

            for supplemental in KNOWN_BASES.get(current, ()):
                queue.append(supplemental)

        return result

    def get_properties(self, control: str) -> list[PropertyMetadata]:
        result: list[PropertyMetadata] = []
        seen: set[str] = set()

        for type_name in self.get_inheritance_chain(control):
            item = self.get_control(type_name)
            properties = (
                item.properties
                if item is not None
                else self.property_owners.get(
                    self.normalize_name(type_name),
                    {},
                )
            )

            for prop in properties.values():
                key = prop.name.lower()

                if key in seen:
                    continue

                seen.add(key)
                result.append(prop)

        return result

    def get_property_metadata(
        self,
        control: str,
        property_name: str,
    ) -> PropertyMetadata | None:
        target = property_name.lower()

        for type_name in self.get_inheritance_chain(control):
            item = self.get_control(type_name)
            properties = (
                item.properties
                if item is not None
                else self.property_owners.get(
                    self.normalize_name(type_name),
                    {},
                )
            )

            for prop in properties.values():
                if prop.name.lower() == target:
                    return prop

        # Also allow lookup of attached properties using Owner.Property.
        if "." in property_name:
            owner, name = property_name.split(".", 1)
            return self.get_attached_property_metadata(owner, name)

        return None

    def get_events(self, control: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for type_name in self.get_inheritance_chain(control):
            item = self.get_control(type_name)

            if item is None:
                continue

            for event in item.events.values():
                key = event.name.lower()

                if key in seen:
                    continue

                seen.add(key)
                result.append(event.name)

        return result

    def get_attached_properties(self, owner: str) -> list[str]:
        if not owner:
            return []

        target = self.normalize_name(owner).lower()

        for owner_name, properties in self.attached_properties.items():
            if self.normalize_name(owner_name).lower() == target:
                return [metadata.name for metadata in properties.values()]

        return []

    def get_attached_property_metadata(
        self,
        owner: str,
        name: str,
    ) -> PropertyMetadata | None:
        if not owner or not name:
            return None

        target_owner = self.normalize_name(owner).lower()
        target_name = name.lower()

        for owner_name, properties in self.attached_properties.items():
            if self.normalize_name(owner_name).lower() != target_owner:
                continue

            for prop_name, metadata in properties.items():
                if prop_name.lower() == target_name:
                    return metadata

        return None


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as ex:
        log.error(f"Metadata load failed {path}: {ex}")
        return {}


def _field(value, *names, default=None):
    if not isinstance(value, dict):
        return default

    for name in names:
        if name in value and value[name] is not None:
            return value[name]

    return default


def _as_list(data, *keys):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def _merge_property(
    control: ControlMetadata,
    prop: PropertyMetadata,
):
    key = prop.name.lower()
    existing = control.properties.get(key)

    if existing is None:
        control.properties[key] = prop
        return

    if prop.type:
        existing.type = prop.type

    if prop.declaring_type:
        existing.declaring_type = prop.declaring_type

    if prop.description:
        existing.description = prop.description

    if prop.default:
        existing.default = prop.default

    if prop.values:
        existing.values = list(prop.values)


def parse_property(
    value,
    owner: str | None = None,
) -> PropertyMetadata | None:
    if isinstance(value, str):
        return PropertyMetadata(
            name=value,
            declaring_type=owner,
        )

    if not isinstance(value, dict):
        return None

    name = _field(
        value,
        "Name",
        "name",
        "Property",
        "property",
    )

    if not name:
        return None

    declaring_type = _field(
        value,
        "Owner",
        "owner",
        "DeclaringType",
        "declaringType",
        default=owner,
    )

    values = _field(
        value,
        "Values",
        "values",
        default=[],
    )

    if not isinstance(values, list):
        values = []

    return PropertyMetadata(
        name=str(name),
        type=_field(value, "Type", "type"),
        declaring_type=(
            str(declaring_type)
            if declaring_type
            else None
        ),
        description=_field(
            value,
            "Description",
            "description",
        ),
        default=_field(
            value,
            "Default",
            "default",
        ),
        values=[str(item) for item in values],
    )


def parse_event(
    value,
    owner: str | None = None,
) -> EventMetadata | None:
    if isinstance(value, str):
        return EventMetadata(
            name=value,
            declaring_type=owner,
        )

    if not isinstance(value, dict):
        return None

    name = _field(
        value,
        "Name",
        "name",
    )

    if not name:
        return None

    declaring_type = _field(
        value,
        "Owner",
        "owner",
        "DeclaringType",
        "declaringType",
        default=owner,
    )

    return EventMetadata(
        name=str(name),
        declaring_type=(
            str(declaring_type)
            if declaring_type
            else None
        ),
        description=_field(
            value,
            "Description",
            "description",
        ),
    )


def merge_class_metadata(
    index: CompletionMetadataIndex,
    data,
):
    records = _as_list(
        data,
        "classes",
        "controls",
        "types",
    )

    if records:
        for record in records:
            if not isinstance(record, dict):
                continue

            name = _field(
                record,
                "Name",
                "name",
                "FullName",
                "fullName",
            )

            if not name:
                continue

            control = index.ensure_control(name)

            base = _field(
                record,
                "Base",
                "base",
                "BaseType",
                "baseType",
                "Parent",
                "parent",
            )

            if base:
                index.inheritance[
                    control.name
                ] = index.normalize_name(base)

            for raw_property in _field(
                record,
                "Properties",
                "properties",
                default=[],
            ) or []:
                prop = parse_property(
                    raw_property,
                    owner=control.name,
                )
                if prop:
                    _merge_property(control, prop)

            for raw_event in _field(
                record,
                "Events",
                "events",
                default=[],
            ) or []:
                event = parse_event(
                    raw_event,
                    owner=control.name,
                )
                if event:
                    control.events[
                        event.name.lower()
                    ] = event

        return

    # Fallback for dictionary-shaped metadata.
    if not isinstance(data, dict):
        return

    for name, value in data.items():
        if str(name).startswith("$"):
            continue

        if isinstance(value, str):
            index.ensure_control(name)
            index.inheritance[
                index.normalize_name(name)
            ] = index.normalize_name(value)
            continue

        if not isinstance(value, dict):
            continue

        control = index.ensure_control(name)

        base = _field(
            value,
            "Base",
            "base",
            "BaseType",
            "baseType",
        )

        if base:
            index.inheritance[
                control.name
            ] = index.normalize_name(base)


def merge_property_metadata(
    index: CompletionMetadataIndex,
    data,
):
    """
    Merge normal properties into controls already discovered by the class
    metadata. Property metadata must enrich the 524-control index, not create
    additional synthetic controls.
    """

    records = _as_list(
        data,
        "properties",
    )

    if not records and isinstance(data, dict):
        expanded = []

        for owner, values in data.items():
            if not isinstance(values, list):
                continue

            for value in values:
                if not isinstance(value, dict):
                    continue

                item = dict(value)
                item.setdefault("Owner", owner)
                expanded.append(item)

        records = expanded

    for record in records:
        prop = parse_property(record)

        if prop is None:
            continue

        owner = (
            prop.declaring_type
            or _field(record, "Owner", "owner")
        )

        if not owner:
            continue

        # Never create controls here. The class metadata owns the control
        # index and should remain at 524. Properties whose owner is a
        # supplemental base such as Layoutable are retained in a separate
        # owner index so existing inherited completion behavior is preserved.
        control = index.get_control(owner)

        if control is not None:
            prop.declaring_type = control.name
            _merge_property(
                control,
                prop,
            )
            continue

        owner_name = index.normalize_name(owner)
        prop.declaring_type = owner_name
        bucket = index.property_owners.setdefault(
            owner_name,
            {},
        )
        existing = bucket.get(prop.name.lower())

        if existing is None:
            bucket[prop.name.lower()] = prop
        else:
            _merge_property(
                ControlMetadata(name=owner_name, properties=bucket),
                prop,
            )


def merge_values_metadata(
    index: CompletionMetadataIndex,
    data,
):
    """Attach generated value lists to properties with the same metadata name.

    The generated values table is keyed by the property identifier and is
    case-sensitive.  Do not case-fold this association: unrelated properties
    can legitimately share a spelling with different casing (for example
    ``Level`` versus ``level``).
    """
    if not isinstance(data, dict):
        return

    buckets = (
        [control.properties for control in index.controls.values()]
        + list(index.property_owners.values())
    )

    for property_name, values in data.items():
        if not isinstance(values, list):
            continue

        property_name = str(property_name)
        normalized_values = [str(value) for value in values]

        for properties in buckets:
            for prop in properties.values():
                if prop.name == property_name:
                    prop.values = list(normalized_values)


def merge_attached_metadata(
    index: CompletionMetadataIndex,
    data,
):
    """
    Load avalonia-attached-properties.json.

    The generated file is a list of records:

        {
            "Name": "Row",
            "Type": "Int32",
            "Owner": "Grid",
            "Kind": "Attached"
        }

    Keep this loader independent from the normal property loader because
    attached properties belong to an owner and are referenced as Owner.Name
    in AXAML.
    """

    records = data if isinstance(data, list) else None

    if records is None and isinstance(data, dict):
        records = data.get("attached")
        if not isinstance(records, list):
            records = data.get("properties")

    if isinstance(records, list):
        loaded = 0

        for record in records:
            if not isinstance(record, dict):
                continue

            kind = str(
                record.get("Kind")
                or record.get("kind")
                or "Attached"
            ).lower()

            # This file is dedicated to attached properties, but accepting
            # records without Kind makes the loader tolerant of generators
            # that omit the field.
            if kind and kind not in {"attached", "attachedproperty"}:
                continue

            name = (
                record.get("Name")
                or record.get("name")
                or record.get("Property")
                or record.get("property")
            )

            owner = (
                record.get("Owner")
                or record.get("owner")
                or record.get("DeclaringType")
                or record.get("declaringType")
            )

            if not name or not owner:
                continue

            owner = index.normalize_name(str(owner))
            name = str(name)

            metadata = PropertyMetadata(
                name=name,
                type=(
                    str(record["Type"])
                    if record.get("Type") is not None
                    else (
                        str(record["type"])
                        if record.get("type") is not None
                        else None
                    )
                ),
                declaring_type=owner,
                description=(
                    record.get("Description")
                    or record.get("description")
                ),
                default=(
                    record.get("Default")
                    or record.get("default")
                ),
                values=(
                    record.get("Values")
                    or record.get("values")
                    or []
                ),
            )

            bucket = index.attached_properties.setdefault(
                owner,
                {}
            )

            bucket[name.lower()] = metadata
            loaded += 1

        log.info(
            f"Attached metadata records loaded: {loaded}"
        )
        log.info(
            f"Attached metadata owners loaded: "
            f"{len(index.attached_properties)}"
        )

        return

    # Compatibility with dictionary-shaped metadata.
    if not isinstance(data, dict):
        log.info("Attached metadata format: unsupported")
        return

    owners = data.get("owners", data)

    if not isinstance(owners, dict):
        log.info("Attached metadata format: no owners")
        return

    loaded = 0

    for owner, value in owners.items():
        owner = index.normalize_name(str(owner))

        if isinstance(value, dict):
            records = value.get("properties", [])
        elif isinstance(value, list):
            records = value
        else:
            continue

        bucket = index.attached_properties.setdefault(
            owner,
            {}
        )

        for record in records:
            prop = parse_property(
                record,
                owner=owner,
            )

            if prop:
                bucket[prop.name.lower()] = prop
                loaded += 1

    log.info(
        f"Attached metadata records loaded: {loaded}"
    )
    log.info(
        f"Attached metadata owners loaded: "
        f"{len(index.attached_properties)}"
    )


def build_completion_metadata_index(
    metadata_root: Path,
) -> CompletionMetadataIndex:
    index = CompletionMetadataIndex()

    completion = Path(metadata_root) / "completion"

    if not completion.exists():
        log.error(
            f"Completion metadata directory does not exist: {completion}"
        )
        return index

    # 1. Classes establish the authoritative 524-control index.
    classes_file = completion / "avalonia-classes.json"

    if classes_file.exists():
        log.info(
            f"Loading metadata: {classes_file.name}"
        )

        merge_class_metadata(
            index,
            load_json(classes_file),
        )

    # 2. Normal properties enrich existing controls only.
    properties_file = completion / "avalonia-properties.json"

    if properties_file.exists():
        log.info(
            f"Loading metadata: {properties_file.name}"
        )

        merge_property_metadata(
            index,
            load_json(properties_file),
        )

    # 3. Enumerated/property values enrich existing properties.
    values_file = completion / "avalonia-values.json"

    if values_file.exists():
        log.info(
            f"Loading metadata: {values_file.name}"
        )

        merge_values_metadata(
            index,
            load_json(values_file),
        )

    # 4. Attached properties are a separate index.
    attached_file = (
        completion
        / "avalonia-attached-properties.json"
    )

    if attached_file.exists():
        log.info(
            f"Loading metadata: {attached_file.name}"
        )

        merge_attached_metadata(
            index,
            load_json(attached_file),
        )

    # 5. Inheritance remains authoritative from the dedicated inheritance
    # file and should remain at 524 entries.
    inheritance_file = (
        Path(metadata_root)
        / "inheritance.json"
    )

    if inheritance_file.exists():
        inheritance = load_json(
            inheritance_file
        )

        if isinstance(inheritance, dict):
            for name, base in inheritance.items():
                if name:
                    index.inheritance[
                        index.normalize_name(name)
                    ] = (
                        index.normalize_name(base)
                        if base
                        else None
                    )

    attached_count = sum(
        len(properties)
        for properties in index.attached_properties.values()
    )

    log.info(
        f"Controls indexed: {len(index.controls)}"
    )

    log.info(
        f"Attached owners indexed: "
        f"{len(index.attached_properties)}"
    )

    log.info(
        f"Attached properties indexed: "
        f"{attached_count}"
    )

    log.info(
        f"Inheritance indexed: "
        f"{len(index.inheritance)}"
    )

    return index
