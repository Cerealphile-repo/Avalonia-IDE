"""Metadata-driven Avalonia completion engine."""
from __future__ import annotations

from dataclasses import dataclass
from .completion_metadata import CompletionMetadataIndex, PropertyMetadata
from .resource import ResourceIndex
from .log import log


@dataclass(frozen=True, slots=True)
class CompletionItem:
    label: str
    insert_text: str
    kind: str = "resource"
    detail: str | None = None


class CompletionEngine:
    """Pure semantic completion engine; no Sublime API and no AXAML parsing."""

    def __init__(self, resources=None, completion_metadata=None):
        self._resources = resources
        self._completion_metadata = completion_metadata

    def update_resources(self, resources: ResourceIndex | None):
        self._resources = resources

    def update_completion_metadata(self, metadata: CompletionMetadataIndex | None):
        self._completion_metadata = metadata
        if metadata is not None:
            log.info(f"Completion metadata updated controls={len(metadata.controls)}")

    def complete_resources(self, prefix=""):
        if self._resources is None:
            return []
        p = (prefix or "").lower()
        return self._sort_unique([
            CompletionItem(k, k, "resource")
            for k in self._resources.by_key
            if k.lower().startswith(p)
        ])

    def complete_controls(self, prefix=""):
        if self._completion_metadata is None:
            return []
        p = (prefix or "").lower()
        return self._sort_unique([
            CompletionItem(c, c, "control", "Avalonia Control")
            for c in self._completion_metadata.controls
            if c.lower().startswith(p)
        ])

    def complete_properties(self, control, prefix="", existing=None):
        if self._completion_metadata is None or not control:
            return []
        p = (prefix or "").lower()
        existing = {str(x).lower() for x in (existing or set())}
        result = []
        for prop in self._completion_metadata.get_properties(control):
            if prop.name.lower() in existing or (p and not prop.name.lower().startswith(p)):
                continue
            detail = "Avalonia Property"
            if prop.declaring_type:
                detail += f" — {prop.declaring_type}"
            result.append(CompletionItem(prop.name, prop.name, "property", detail))
        return self._sort_unique(result)

    def complete_attached_owners(self, prefix=""):
        if self._completion_metadata is None:
            return []
        p = (prefix or "").lower()
        return self._sort_unique([
            CompletionItem(owner, owner, "attached_owner", "Avalonia Attached Property Owner")
            for owner in self._completion_metadata.attached_properties
            if owner.lower().startswith(p)
        ])

    def complete_attached_properties(self, owner, prefix=""):
        if self._completion_metadata is None or not owner:
            return []
        p = (prefix or "").lower()
        result = []
        canonical = self._canonical_attached_owner(owner)
        if canonical is None:
            return []
        for name in self._completion_metadata.get_attached_properties(canonical):
            if p and not name.lower().startswith(p):
                continue
            meta = self._completion_metadata.get_attached_property_metadata(canonical, name)
            detail = "Avalonia Attached Property"
            if meta and meta.declaring_type:
                detail += f" — {meta.declaring_type}"
            result.append(CompletionItem(f"{canonical}.{name}", f"{canonical}.{name}", "attached_property", detail))
        return self._sort_unique(result)

    def complete_property_values(self, control, property_name, prefix=""):
        if self._completion_metadata is None or not property_name:
            return []
        meta = self._completion_metadata.get_property_metadata(control, property_name)
        if meta is None:
            if "." in property_name:
                owner, name = property_name.split(".", 1)
                meta = self._completion_metadata.get_attached_property_metadata(owner, name)
        if meta is None:
            return []
        p = (prefix or "").lower()
        return self._sort_unique([
            CompletionItem(v, v, "value", f"Avalonia Value — {meta.type}" if meta.type else "Avalonia Value")
            for v in meta.values
            if not p or v.lower().startswith(p)
        ])

    def complete_events(self, control, prefix=""):
        if self._completion_metadata is None or not control:
            return []
        p = (prefix or "").lower()
        return self._sort_unique([
            CompletionItem(e, e, "event", "Avalonia Event")
            for e in self._completion_metadata.get_events(control)
            if not p or e.lower().startswith(p)
        ])

    def _canonical_attached_owner(self, owner):
        target = owner.lower()
        for candidate in self._completion_metadata.attached_properties:
            if candidate.lower() == target:
                return candidate
        return None

    def _sort_unique(self, items):
        seen = set()
        result = []
        for item in items:
            key = (item.kind, item.label.lower())
            if key not in seen:
                seen.add(key)
                result.append(item)
        priority = {
            "attached_owner": 0,
            "attached_property": 1,
            "property": 2,
            "event": 3,
            "control": 4,
            "value": 5,
            "resource": 6,
        }
        result.sort(key=lambda x: (priority.get(x.kind, 99), x.label.lower()))
        return result
