"""
AXAML Hover Context

Provides cursor-aware semantic context for hover and navigation.

This module does not interact with Sublime Text.
It does not load metadata.

It determines what AXAML element, property, value,
or resource reference the cursor is currently over.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class HoverContext:
    """
    Semantic location inside AXAML.
    """

    kind: str | None = None

    control: str | None = None
    property: str | None = None
    value: str | None = None

    token: str | None = None

    resource_kind: str | None = None
    binding_path: str | None = None


# AXAML identifiers used by this context parser.
_IDENTIFIER = r"[A-Za-z_][\w.-]*"


def get_hover_context(
    text: str,
    point: int,
) -> HoverContext:
    """
    Determine semantic context at cursor position.

    The important rule here is that hover detection is based on the
    token immediately surrounding the cursor, not on whether the
    surrounding element happens to contain quoted attributes.

    In particular, an earlier quoted attribute must not prevent hover
    over a later property such as:

        <Button Content="Hello" Owner.Property="1">
                                  ^^^^^^^^^^^
    """

    if not isinstance(text, str):
        return HoverContext()

    point = max(0, min(point, len(text)))

    before = text[:point]
    after = text[point:]

    # Resource references have their own syntax and take priority.
    resource_context = _get_resource_context(text, point)
    if resource_context is not None:
        return resource_context

    # Binding paths also have their own syntax.
    binding_match = re.search(
        r"\{(?:Binding|CompiledBinding|ReflectionBinding)\b"
        r"[^{}]*?\b(?:Path\s*=\s*)?"
        r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)",
        text,
        re.IGNORECASE,
    )

    if binding_match:
        start = binding_match.start(1)
        end = binding_match.end(1)
        if start <= point <= end:
            path_value = binding_match.group(1)
            return HoverContext(
                kind="binding",
                control=_get_current_control(before),
                value=path_value,
                token=_expand_token(before, after),
                binding_path=path_value,
            )

    # Find the currently open tag at the cursor. This deliberately uses
    # the text before the cursor so an unrelated later tag cannot affect
    # the context.
    tag = _get_open_tag_context(before)
    if tag is not None:
        control, attributes_start, attributes = tag

        # If the cursor is inside a quoted value, handle that as VALUE.
        value_context = _get_value_context(
            text,
            point,
            control,
            attributes_start,
        )
        if value_context is not None:
            return value_context

        # If the cursor is in the tag's attribute area, inspect the
        # identifier immediately surrounding it. This works even when
        # earlier attributes contain quoted values.
        if point >= attributes_start:
            token = _expand_token(before, after)

            if token and re.fullmatch(
                r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?",
                token,
            ):
                return HoverContext(
                    kind="property",
                    control=control,
                    property=token,
                    token=token,
                )

            # Empty/whitespace attribute position.
            if _is_attribute_position(before, attributes_start):
                return HoverContext(
                    kind="property",
                    control=control,
                )

    # Control name hover, e.g. <Button.
    control_match = re.search(
        rf"<({_IDENTIFIER})$",
        before,
    )
    if control_match:
        token = _expand_token(before, after)
        if token and re.fullmatch(_IDENTIFIER, token):
            return HoverContext(
                kind="control",
                token=token,
            )

    return HoverContext()


def _get_value_context(
    text: str,
    point: int,
    control: str,
    attributes_start: int,
) -> HoverContext | None:
    """
    Return value context when the cursor is inside an attribute value.

    This is cursor-aware and does not require all earlier attributes in
    the element to be unquoted.
    """

    before = text[:point]

    # The nearest unmatched opening quote after the attribute name is the
    # one containing the cursor. Restrict the search to the current tag.
    segment = before[attributes_start:]
    match = re.search(
        r'([A-Za-z_][\w.]*)\s*=\s*"([^"]*)$',
        segment,
    )

    if not match:
        return None

    property_name = match.group(1)
    value_prefix = match.group(2)

    return HoverContext(
        kind="value",
        control=control,
        property=property_name,
        value=value_prefix,
        token=_expand_token(before, text[point:]),
    )


def _get_open_tag_context(
    before: str,
) -> tuple[str, int, str] | None:
    """
    Return the nearest currently open start tag.

    The returned tuple is:

        (control_name, attributes_start_offset, attributes_text)

    A tag is considered current only when the last '<' has not been
    closed by '>' and is not itself a closing tag.
    """

    lt = before.rfind("<")
    gt = before.rfind(">")

    if lt <= gt:
        return None

    fragment = before[lt:]

    # Closing tags and markup declarations are not start-tag contexts.
    if re.match(r"</|<!|\?", fragment):
        return None

    match = re.match(
        rf"<({_IDENTIFIER})(.*)$",
        fragment,
        re.DOTALL,
    )
    if not match:
        return None

    control = match.group(1)
    attributes = match.group(2)
    attributes_start = lt + match.start(2)

    # If the cursor is inside an unfinished quoted value, this is still
    # the current tag; _get_value_context handles it.
    return control, attributes_start, attributes


def _is_attribute_position(
    before: str,
    attributes_start: int,
) -> bool:
    """
    Determine whether the cursor is in whitespace after the control name
    and before a new attribute token.
    """

    attributes = before[attributes_start:]
    return bool(re.search(r"(?:^|\s)$", attributes))


def _get_resource_context(
    text: str,
    point: int,
) -> HoverContext | None:
    """
    Return resource context when the cursor is inside:

        {StaticResource Key}

    or:

        {DynamicResource Key}
    """

    pattern = re.compile(
        r"\{"
        r"(StaticResource|DynamicResource)"
        r"\s+"
        r'([^\s}"\']+)'
        r"\}",
    )

    for match in pattern.finditer(text):
        if not (match.start() <= point <= match.end()):
            continue

        resource_kind = match.group(1)
        key = match.group(2)
        before = text[:point]

        return HoverContext(
            kind="resource",
            control=_get_current_control(before),
            property=_get_current_property(before),
            value=key,
            token=key,
            resource_kind=resource_kind,
        )

    return None


def _expand_token(
    before: str,
    after: str,
) -> str:
    """
    Expand the identifier around the cursor.

    Includes:

        .
        :
        -

    so AXAML names such as:

        Owner.Property
        Owner.Property
        x:Name

    remain a single hover token.
    """

    left = re.search(r"[\w.:-]+$", before)
    right = re.match(r"[\w.:-]*", after)

    result = ""

    if left:
        result += left.group(0)

    if right:
        result += right.group(0)

    return result


def _get_current_control(
    text: str,
) -> str | None:
    """
    Find the nearest opening AXAML element before the cursor.

    Closing tags and tags that have already ended are ignored.
    """

    # Walk backwards through tag boundaries and use the nearest unfinished
    # start tag when one exists. Otherwise fall back to the latest opening
    # element, which preserves the behavior needed by resource/value hover.
    lt = text.rfind("<")
    gt = text.rfind(">")

    if lt > gt:
        match = re.match(
            rf"<({_IDENTIFIER})",
            text[lt:],
        )
        if match:
            return match.group(1)

    matches = list(
        re.finditer(
            rf"<({_IDENTIFIER})",
            text,
        )
    )

    return matches[-1].group(1) if matches else None


def _get_current_property(
    text: str,
) -> str | None:
    """
    Find the attribute containing the current value.
    """

    match = re.search(
        r'([A-Za-z_][\w.]*)\s*=\s*"[^"]*$',
        text,
    )

    return match.group(1) if match else None
