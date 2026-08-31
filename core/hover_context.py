"""Cursor-aware AXAML hover context detection.

The classifier deliberately models AXAML syntax instead of treating every
opening tag as a control and every quoted value as a value hover.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class HoverContext:
    kind: str | None = None
    control: str | None = None
    property: str | None = None
    value: str | None = None
    token: str | None = None
    resource_kind: str | None = None
    binding_path: str | None = None
    markup_extension: str | None = None
    binding_parameter: str | None = None
    directive: str | None = None
    namespace_prefix: str | None = None


_IDENT = r"[A-Za-z_][\w.:-]*"
_DIRECTIVES = {
    "x:class", "x:name", "x:datatype", "x:key", "x:compilebindings",
    "x:fieldmodifier", "x:modifier", "x:rootnamespace", "x:array", "x:type",
}
_MARKUP_EXTENSIONS = {
    "binding", "compiledbinding", "reflectionbinding", "staticresource",
    "dynamicresource", "templatebinding", "onplatform", "onformfactor",
    "x:true", "x:false", "x:null", "x:static", "x:type",
}
_BINDING_EXTENSIONS = {"binding", "compiledbinding", "reflectionbinding"}
_BINDING_PARAMETERS = {
    "path", "mode", "priority", "source", "elementname", "relativesource",
    "stringformat", "converter", "converterparameter", "datacontext", "datatype",
    "fallbackvalue", "targetnullvalue", "updatesourcetrigger", "delay",
    "defaultanchor", "anchor", "name",
}


def get_hover_context(text: str, point: int) -> HoverContext:
    if not isinstance(text, str):
        return HoverContext()
    point = max(0, min(point, len(text)))

    # Most-specific markup expressions first.
    context = _markup_at(text, point)
    if context:
        return context

    # Directives and namespace declarations are meaningful AXAML syntax.
    context = _directive_at(text, point)
    if context:
        return context

    tag = _open_tag_at(text, point)
    if tag:
        tag_name, tag_start, attrs_start = tag
        name_start, name_end, full_tag_name = _tag_name_span(text, point)

        # Property-element syntax: <Grid.ColumnDefinitions>, <UserControl.Resources>
        if "." in full_tag_name:
            owner_name, property_name = full_tag_name.split(".", 1)
            return HoverContext(
                kind="property_element",
                control=owner_name,
                property=property_name,
                token=full_tag_name,
            )

        # Object/control/type name. Only return this when the cursor is in the
        # actual element name, not somewhere later in the opening tag.
        if name_start <= point <= name_end:
            return HoverContext(kind="type", token=full_tag_name)

        value_context = _literal_value_at(text, point, tag_start)
        if value_context:
            return value_context

        attr = _attribute_at(text, point, attrs_start)
        if attr:
            if _is_directive_or_namespace(attr):
                return HoverContext()
            return HoverContext(
                kind="property",
                control=tag_name,
                property=attr,
                token=attr,
            )

        return HoverContext()

    # A partially typed opening element, e.g. <But|
    m = re.search(rf"<({_IDENT})$", text[:point])
    if m:
        return HoverContext(kind="type", token=m.group(1))

    return HoverContext()


def _markup_at(text: str, point: int) -> HoverContext | None:
    # Find every markup expression that contains the cursor. Nested markup
    # is intentionally handled by choosing the innermost expression.
    starts = [m for m in re.finditer(r"\{([A-Za-z_][\w.:]*)\b", text) if m.start() <= point]
    if not starts:
        return None

    for start_match in reversed(starts):
        name = start_match.group(1)
        if name.casefold() not in _MARKUP_EXTENSIONS:
            continue
        close = _matching_brace(text, start_match.start(), point)
        if close is None:
            close = len(text)
        if not (start_match.start() <= point <= close):
            continue

        ext = name
        body_start = start_match.end()
        body_end = close
        body = text[body_start:body_end]
        before = text[:start_match.start()]
        control = _current_control(text, point)
        prop = _current_attribute(before)

        # Hover on the extension keyword itself.
        if start_match.start(1) <= point <= start_match.end(1):
            return HoverContext(
                kind="markup_extension",
                control=control,
                property=prop,
                token=ext,
                markup_extension=ext,
            )

        if ext.casefold() in {"staticresource", "dynamicresource"}:
            key_match = re.search(r"[^\s,}]+", body)
            if key_match:
                ks = body_start + key_match.start()
                ke = body_start + key_match.end()
                if ks <= point <= ke:
                    return HoverContext(
                        kind="resource",
                        control=control,
                        property=prop,
                        value=key_match.group(0),
                        token=key_match.group(0),
                        resource_kind=ext,
                        markup_extension=ext,
                    )
            return None

        if ext.casefold() in _BINDING_EXTENSIONS:
            return _binding_context(text, point, start_match, close, control, prop)

        return _markup_parameter_context(body, body_start, point, ext, control, prop)

    return None


def _binding_context(text, point, match, close, control, prop):
    body_start = match.end()
    body_end = close
    body = text[body_start:body_end]

    # First identify named parameters so hovering Mode=, Source=, etc. does
    # not accidentally become a binding-path hover.
    for p in re.finditer(r"(?P<name>[A-Za-z_]\w*)\s*=\s*", body):
        ns = body_start + p.start("name")
        ne = body_start + p.end("name")
        if ns <= point <= ne:
            return HoverContext(
                kind="binding_parameter",
                control=control,
                property=prop,
                token=p.group("name"),
                value=p.group("name"),
                binding_parameter=p.group("name"),
                markup_extension=match.group(1),
            )

    # Positional path or Path=Path. Avoid consuming parameter names.
    candidates = re.finditer(
        r"(?:(?:^|[\s,])Path\s*=\s*|(?:^|[\s,]))(?P<path>[A-Za-z_#$][\w$.-]*(?:\.[A-Za-z_#$][\w$.-]*)*)",
        body,
        re.IGNORECASE,
    )
    for candidate in candidates:
        ps = body_start + candidate.start("path")
        pe = body_start + candidate.end("path")
        if ps <= point <= pe:
            path = candidate.group("path")
            return HoverContext(
                kind="binding",
                control=control,
                property=prop,
                value=path,
                token=path.rsplit(".", 1)[-1],
                binding_path=path,
                markup_extension=match.group(1),
            )

    return None


def _markup_parameter_context(body, body_start, point, ext, control, prop):
    for p in re.finditer(r"(?P<name>[A-Za-z_]\w*)\s*=", body):
        ns = body_start + p.start("name")
        ne = body_start + p.end("name")
        if ns <= point <= ne:
            return HoverContext(
                kind="markup_parameter",
                control=control,
                property=prop,
                token=p.group("name"),
                value=p.group("name"),
                binding_parameter=p.group("name"),
                markup_extension=ext,
            )
    return None


def _directive_at(text: str, point: int) -> HoverContext | None:
    # Attribute name or its quoted value.
    lt = text.rfind("<", 0, point + 1)
    gt = text.rfind(">", 0, point + 1)
    if lt <= gt:
        return None
    segment = text[lt:]

    for m in re.finditer(r"(?P<name>x:[A-Za-z_]\w*|xmlns(?::[A-Za-z_]\w*)?)\s*=\s*(?P<q>[\"'])(?P<value>.*?)(?P=q)", segment, re.S):
        ns = lt + m.start("name")
        ne = lt + m.end("name")
        vs = lt + m.start("value")
        ve = lt + m.end("value")
        name = m.group("name")
        if ns <= point <= ne:
            if name.casefold().startswith("xmlns"):
                return HoverContext(kind="namespace", token=name, directive=name)
            return HoverContext(kind="directive", token=name, directive=name, property=name, value=m.group("value"))
        if vs <= point <= ve:
            if name.casefold().startswith("xmlns"):
                prefix = name.split(":", 1)[1] if ":" in name else ""
                return HoverContext(kind="namespace", token=m.group("value"), value=m.group("value"), namespace_prefix=prefix)
            return HoverContext(kind="directive", token=m.group("value") or name, directive=name, property=name, value=m.group("value"))
    return None


def _tag_name_span(text: str, point: int):
    lt = text.rfind("<", 0, point + 1)
    if lt < 0:
        return point, point, ""
    m = re.match(r"<([A-Za-z_][\w.:-]*)", text[lt:])
    if not m:
        return point, point, ""
    start = lt + 1
    end = lt + len(m.group(1)) + 1
    return start, end, m.group(1)


def _open_tag_at(text: str, point: int):
    before = text[:point]
    lt = before.rfind("<")
    gt = before.rfind(">")
    if lt <= gt:
        return None
    fragment = before[lt:]
    m = re.match(rf"<({_IDENT})(?P<attrs>.*)$", fragment, re.S)
    if not m or fragment.startswith(("</", "<!", "<?")):
        return None
    return m.group(1), lt, lt + m.start("attrs")


def _literal_value_at(text: str, point: int, tag_start: int) -> HoverContext | None:
    segment = text[tag_start:]
    pattern = r"(?P<name>[A-Za-z_][\w:.-]*)\s*=\s*(?P<q>[\"'])(?P<value>[^\"']*)(?P=q)"
    for m in re.finditer(pattern, segment, re.S):
        value_start = tag_start + m.start("value")
        value_end = tag_start + m.end("value")
        if not (value_start <= point <= value_end):
            continue
        name = m.group("name")
        if _is_directive_or_namespace(name):
            return None
        value = m.group("value")
        relative = point - value_start
        left = re.search(r"[A-Za-z_][\w-]*$", value[:relative])
        right = re.match(r"[A-Za-z_][\w-]*", value[relative:])
        token = (left.group(0) if left else "") + (right.group(0) if right else "")
        return HoverContext(
            kind="value",
            control=_current_control(text, point),
            property=name,
            value=value,
            token=token or value,
        )
    return None


def _attribute_at(text: str, point: int, attrs_start: int) -> str | None:
    segment = text[attrs_start:point]
    if _quote_is_open(segment):
        return None
    token = _token_at(text, point, r"[\w:.-]")
    if not token or not re.match(r"^[A-Za-z_]", token):
        return None
    after = text[point:]
    if not re.match(r"[\w:.-]*\s*(?:=|$)", after):
        return None
    return token


def _is_directive_or_namespace(name: str) -> bool:
    low = name.casefold()
    return low in _DIRECTIVES or low.startswith("xmlns")


def _quote_is_open(segment: str) -> bool:
    return sum(1 for q in re.findall(r"[\"']", segment)) % 2 == 1


def _token_at(text: str, point: int, chars: str) -> str:
    left = re.search(rf"{chars}+$", text[:point])
    right = re.match(rf"{chars}*", text[point:])
    return (left.group(0) if left else "") + (right.group(0) if right else "")


def _matching_brace(text: str, start: int, point: int) -> int | None:
    depth = 0
    quote = None
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if ch == quote and (i == 0 or text[i - 1] != "\\"):
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        if i > point and depth == 0:
            break
    return None


def _tag_events(text: str, end: int):
    tag_re = re.compile(r"<\s*(/?)\s*([A-Za-z_][\w.:-]*)([^>]*)>", re.S)
    for m in tag_re.finditer(text, 0, end):
        closing, name, tail = m.groups()
        yield m, bool(closing), name, tail


def _current_control(text: str, point: int | None = None) -> str | None:
    end = len(text) if point is None else max(0, min(point, len(text)))
    source = text[:end]
    stack: list[str] = []
    for m, closing, name, tail in _tag_events(source, len(source)):
        if closing:
            _pop_tag(stack, name)
        elif not tail.rstrip().endswith("/"):
            stack.append(name)
    # Include the unfinished opening tag at the cursor. Property elements are
    # structural containers, not binding controls.
    lt = source.rfind("<")
    gt = source.rfind(">")
    if lt > gt:
        m = re.match(r"<([A-Za-z_][\w.:-]*)", source[lt:])
        if m and "." not in m.group(1):
            return m.group(1)
    for name in reversed(stack):
        if "." not in name:
            return name
    return None


def _nearest_real_control(text: str) -> str | None:
    stack: list[str] = []
    for m, closing, name, tail in _tag_events(text, len(text)):
        if closing:
            _pop_tag(stack, name)
        elif not tail.rstrip().endswith("/"):
            stack.append(name)
    for name in reversed(stack):
        if "." not in name:
            return name
    return None


def _pop_tag(stack: list[str], name: str) -> None:
    for i in range(len(stack) - 1, -1, -1):
        if stack[i].casefold() == name.casefold():
            del stack[i:]
            return


def _current_attribute(text: str) -> str | None:
    lt = text.rfind("<")
    if lt < 0:
        return None
    segment = text[lt:]
    m = re.search(r'([A-Za-z_][\w:.-]*)\s*=\s*"[^"<>]*$', segment, re.S)
    if m:
        return m.group(1)
    m = re.search(r"([A-Za-z_][\w:.-]*)\s*=\s*'[^'<>]*$", segment, re.S)
    return m.group(1) if m else None
