"""Cursor-aware AXAML completion context.

This module deliberately contains no Avalonia names.  It answers only the
syntactic question "what is the cursor completing?" and leaves the set of
valid controls, properties, attached properties, and values to metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re


_NAME = r"[A-Za-z_][\w:.-]*"
_ATTR = rf"{_NAME}(?:\s*\.\s*{_NAME})?"


@dataclass(slots=True)
class CompletionContext:
    kind: str | None = None
    control: str | None = None
    property: str | None = None
    attached_owner: str | None = None
    attached_prefix: str | None = None
    prefix: str = ""
    token_start: int | None = None
    token_end: int | None = None
    existing_properties: set[str] = field(default_factory=set)
    resource_kind: str | None = None

    def __repr__(self):
        return (
            f"<CompletionContext kind={self.kind!r} control={self.control!r} "
            f"property={self.property!r} attached_owner={self.attached_owner!r} "
            f"attached_prefix={self.attached_prefix!r} prefix={self.prefix!r} "
            f"token_start={self.token_start!r} token_end={self.token_end!r} "
            f"existing={len(self.existing_properties)}>"
        )


def get_completion_context(text: str) -> CompletionContext:
    """Return the syntactic completion context at the end of *text*.

    The input is expected to end exactly at the completion cursor.  AXAML is
    intentionally not fully parsed here: this is a recovery-oriented lexer
    for the small amount of structure needed by completion.  Semantic names
    always come from metadata/resource/C# indexes elsewhere.
    """
    if not isinstance(text, str):
        return CompletionContext()

    point = len(text)

    resource = _current_resource(text)
    if resource is not None:
        kind, prefix = resource
        return CompletionContext(kind="resource", prefix=prefix, resource_kind=kind)

    tag = _current_start_tag(text)
    if tag is None:
        return _control_context(text)

    control, _, body_start, body = tag
    existing = _existing_attributes(body)

    # No whitespace after the element name means the cursor is still in the
    # element-name token.  Once whitespace is present, the same text becomes
    # the start of an attribute context.
    if body == "":
        return CompletionContext(kind="control", prefix=control)

    value = _current_value(body, body_start, point)
    if value is not None:
        prop, prefix, _, _ = value
        return CompletionContext(
            kind="value",
            control=control,
            property=prop,
            prefix=prefix,
            existing_properties=existing,
        )

    # A qualified attribute is syntactically Owner.Property.  Owner names
    # are deliberately unrestricted here; the metadata index decides whether
    # the owner exists and which properties it exposes.
    attached = re.search(
        rf"(?:^|\s)({_NAME})\.([A-Za-z_]\w*)?$",
        body,
    )
    if attached:
        owner = attached.group(1)
        prop_prefix = attached.group(2) or ""
        token_rel_start = attached.start(1)
        token_rel_end = attached.end()
        return CompletionContext(
            kind="attached_property",
            control=control,
            attached_owner=owner,
            attached_prefix=prop_prefix,
            prefix=f"{owner}.{prop_prefix}",
            token_start=body_start + token_rel_start,
            token_end=body_start + token_rel_end,
            existing_properties=existing,
        )

    # A bare attribute name is generic property completion.  Attached owners
    # are offered alongside normal properties by the completion engine.
    bare = re.search(rf"(?:^|\s)({_NAME})$", body)
    if bare:
        return CompletionContext(
            kind="property",
            control=control,
            prefix=bare.group(1),
            existing_properties=existing,
        )

    if body and body.strip() == "":
        return CompletionContext(
            kind="property",
            control=control,
            prefix="",
            existing_properties=existing,
        )

    return CompletionContext(
        kind="property",
        control=control,
        prefix="",
        existing_properties=existing,
    )


def _current_start_tag(text: str):
    """Return the unfinished start tag containing the cursor.

    Unlike a simple ``rfind('<')``/``rfind('>')`` check, this ignores angle
    brackets occurring inside quoted attribute values.  That matters for
    incomplete AXAML such as ``Content="<``.
    """
    lt = _last_unquoted(text, "<")
    if lt < 0:
        return None

    gt = _last_unquoted(text, ">")
    if lt <= gt:
        return None

    fragment = text[lt:]
    if fragment.startswith(("</", "<!", "<?")):
        return None

    match = re.match(rf"<({_NAME})(.*)$", fragment, re.DOTALL)
    if not match:
        # Still permit completion immediately after '<'.
        if fragment == "<":
            return "", lt + 1, lt + 1, ""
        return None

    control = match.group(1)
    body_start = lt + match.start(2)
    body = match.group(2)
    return control, lt + 1, body_start, body


def _last_unquoted(text: str, target: str) -> int:
    quote: str | None = None
    last = -1
    escaped = False

    for index, char in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in "\"'":
            quote = char
        elif char == target:
            last = index

    return last


def _existing_attributes(body: str) -> set[str]:
    """Collect completed attribute names from the current start tag."""
    return {
        m.group(1).lower()
        for m in re.finditer(rf"(?:^|\s)({_ATTR})\s*=", body)
    }


def _current_value(body: str, body_start: int, point: int):
    """Return ``(property, prefix, start, end)`` for an open quoted value."""
    # Owner.Property is valid for attached properties, so the property token
    # must include a dot.  The context layer does not validate the owner.
    match = re.search(
        rf"(?:^|\s)({_ATTR})\s*=\s*([\"'])([^\"']*)$",
        body,
        re.DOTALL,
    )
    if not match:
        return None

    prop = match.group(1).replace(" ", "")
    prefix = match.group(3)
    return prop, prefix, body_start + match.start(3), body_start + match.end(3)


def _control_context(text: str) -> CompletionContext:
    """Handle ``<`` and partial element names outside an open start tag."""
    match = re.search(r"<([A-Za-z_][\w:.-]*)?$", text)
    if not match:
        return CompletionContext()
    return CompletionContext(kind="control", prefix=match.group(1) or "")


def _current_resource(text: str):
    """Return ``(resource kind, key prefix)`` for unfinished resource markup."""
    match = re.search(
        r"\{\s*(StaticResource|DynamicResource)\s+([A-Za-z_][\w.:-]*)?$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1), match.group(2) or ""
