"""
AXAML binding semantics.

Provides cursor-aware Binding path completion and data-context resolution
without requiring the C# language server to understand AXAML.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from .csharp_semantic import CSharpSemanticIndex, CSharpProperty


@dataclass(frozen=True, slots=True)
class BindingContext:
    path: str
    prefix: str
    expression_start: int
    expression_end: int
    type_name: str | None
    property: CSharpProperty | None = None


_BINDING_RE = re.compile(
    r"\{(?:Binding|CompiledBinding|ReflectionBinding)\b(?P<body>[^{}]*)$",
    re.IGNORECASE,
)


def get_binding_context(
    text: str,
    point: int,
    *,
    root_type: str | None = None,
    index: CSharpSemanticIndex | None = None,
) -> BindingContext | None:
    # Find the binding expression containing the cursor.  The previous
    # implementation only examined text *before* the cursor.  That meant
    # clicking at the beginning or in the middle of a binding property (for
    # example, on ``Greeting``) could not see the complete property token.
    before = text[:point]
    match = _BINDING_RE.search(before)
    if not match:
        return None

    expression_start = match.start()
    expression_end = text.find("}", point)
    if expression_end < 0:
        expression_end = len(text)

    body_start = match.start("body")
    body_end = expression_end
    body = text[body_start:body_end]

    # Binding Path=Foo.Bar and positional Foo.Bar are both supported.
    # Search the complete expression and select the path token containing
    # (or immediately adjacent to) the cursor.
    path_matches = list(
        re.finditer(
            r"(?:^|[\s,])(?:Path\s*=\s*)?(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\.?)",
            body,
            re.IGNORECASE,
        )
    )

    if not path_matches:
        return None

    absolute_point = point
    selected = None

    for candidate in path_matches:
        candidate_start = body_start + candidate.start("path")
        candidate_end = body_start + candidate.end("path")
        if candidate_start <= absolute_point <= candidate_end:
            selected = candidate
            break

    if selected is None:
        # If the cursor is immediately before the token, use that token.
        for candidate in path_matches:
            candidate_start = body_start + candidate.start("path")
            if candidate_start >= absolute_point:
                selected = candidate
                break

    if selected is None:
        return None

    raw_path = selected.group("path")
    # A trailing dot is a first-class completion state: ``Customer.`` means
    # complete members of Customer rather than members of the root context.
    # Keep the dot in the parsed path but expose an empty completion prefix.
    trailing_dot = raw_path.endswith(".")
    path = raw_path
    prefix = "" if trailing_dot else raw_path.rsplit(".", 1)[-1]

    start = body_start + selected.start("path")
    end = body_start + selected.end("path")

    type_name = root_type
    declaring_property = None

    if index and type_name:
        parts = path.split(".") if path else []
        current_type = type_name
        for part in parts[:-1]:
            prop = _find_property(index, current_type, part)
            if prop is None:
                current_type = None
                break
            current_type = _resolve_property_type(index, prop, current_type)

        if parts:
            declaring_property = _find_property(
                index,
                current_type,
                parts[-1],
            ) if current_type else None

    return BindingContext(
        path=path,
        prefix=prefix,
        expression_start=start,
        expression_end=end,
        type_name=type_name,
        property=declaring_property,
    )


def complete_binding(
    context: BindingContext,
    index: CSharpSemanticIndex,
) -> list[CSharpProperty]:
    if not context.type_name:
        return ()

    parts = context.path.split(".") if context.path else []
    parent_parts = parts[:-1]

    current_type = context.type_name
    for part in parent_parts:
        prop = _find_property(index, current_type, part)
        if prop is None:
            return ()
        current_type = _resolve_property_type(index, prop, current_type)
        if not current_type:
            return ()

    values = index.properties_for(current_type)
    prefix = context.prefix.casefold()
    return tuple(
        prop for prop in values
        if not prefix or prop.name.casefold().startswith(prefix)
    )


def _find_property(
    index: CSharpSemanticIndex,
    type_name: str,
    property_name: str,
) -> CSharpProperty | None:
    for prop in index.properties_for(type_name):
        if prop.name.casefold() == property_name.casefold():
            return prop
    return None


def _resolve_property_type(
    index: CSharpSemanticIndex,
    prop: CSharpProperty,
    current_type: str,
) -> str | None:
    type_name = prop.type_name
    builtin = {
        "string", "bool", "boolean", "byte", "sbyte", "short", "ushort",
        "int", "uint", "long", "ulong", "float", "double", "decimal",
        "char", "object", "dynamic", "void",
    }
    if type_name.casefold() in builtin:
        return None
    if type_name.endswith("[]"):
        return None
    found = index.find_type(type_name)
    return found.full_name if found else type_name


def resolve_data_type(
    axaml_text: str,
    axaml_path: Path,
    *,
    csharp_index: CSharpSemanticIndex,
    viewmodel_fallback: str | None = None,
    point: int | None = None,
) -> str | None:
    """
    Resolve x:DataType.

    Examples:
        xmlns:vm="using:MyApp.ViewModels"
        x:DataType="vm:MainWindowViewModel"
    """
    aliases = dict(
        (prefix, namespace)
        for prefix, namespace in re.findall(
            r'\bxmlns:([A-Za-z_]\w*)\s*=\s*"using:([^"]+)"',
            axaml_text,
        )
    )

    match = re.search(
        r'\bx:DataType\s*=\s*"([^"]+)"',
        axaml_text,
    )
    if match:
        value = match.group(1).strip()
        if value.startswith("{x:Type") and value.endswith("}"):
            value = value[len("{x:Type"): -1].strip()
        if ":" in value:
            prefix, name = value.split(":", 1)
            namespace = aliases.get(prefix)
            if namespace:
                found = csharp_index.find_type(name, namespace)
                if found:
                    return found.full_name
        else:
            found = csharp_index.find_type(value)
            if found:
                return found.full_name

    return viewmodel_fallback


def find_viewmodel_type(
    axaml_path: Path,
    csharp_index: CSharpSemanticIndex,
) -> str | None:
    stem = axaml_path.name
    if stem.lower().endswith(".axaml"):
        stem = stem[:-6]
    candidates = (
        f"{stem}ViewModel",
        f"{stem}Viewmodel",
        "MainWindowViewModel" if stem.casefold() == "mainwindow" else "",
    )
    for name in candidates:
        if not name:
            continue
        found = csharp_index.find_type(name)
        if found:
            return found.full_name
    return None
