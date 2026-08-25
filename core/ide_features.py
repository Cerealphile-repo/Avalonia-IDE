"""High-level Avalonia IDE features.

Pure-Python helpers used by the Sublime commands.  The goal is to keep
refactoring, scope resolution, binding analysis, related-file discovery and
scaffolding testable without a Sublime runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .binding import get_binding_context, resolve_data_type, find_viewmodel_type
from .csharp_semantic import CSharpSemanticIndex
from .resource import ResourceIndex


@dataclass(frozen=True, slots=True)
class BindingIssue:
    path: Path
    line: int
    column: int
    expression: str
    message: str
    suggestion: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceResolution:
    key: str
    kind: str
    entry: object | None
    scope: str
    candidates: tuple[object, ...] = ()


def line_col(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, max(0, offset)) + 1
    last = text.rfind("\n", 0, max(0, offset))
    return line, offset + 1 if last < 0 else offset - last


def _nearest_resource_dictionary(text: str, offset: int) -> tuple[str, ...]:
    """Return a conservative stack of resource containers around offset."""
    before = text[:offset]
    stack: list[str] = []
    token_re = re.compile(r"<(/?)([A-Za-z_][\w.:-]*)(?:\s[^<>]*?)?(/?)>", re.S)
    for m in token_re.finditer(before):
        closing, tag, selfclose = m.groups()
        if selfclose:
            continue
        if closing:
            if stack and stack[-1] == tag:
                stack.pop()
        else:
            stack.append(tag)
    return tuple(stack)


def resource_scope_candidates(
    key: str,
    current_file: Path,
    resource_index: ResourceIndex | None,
    text: str = "",
    point: int | None = None,
) -> ResourceResolution:
    candidates = tuple((resource_index.by_key.get(key) or ())) if resource_index else ()
    if not candidates:
        return ResourceResolution(key, "", None, "unresolved", ())
    point = len(text) if point is None else point
    containers = _nearest_resource_dictionary(text, point)
    # Prefer declarations in the current file, then the closest lexical
    # dictionary name.  Full Avalonia resource precedence still belongs to the
    # framework; this is an editor-safe approximation.
    same_file = tuple(x for x in candidates if Path(x.path).resolve() == current_file.resolve())
    pool = same_file or candidates
    entry = pool[0]
    scope = "current file" if same_file else "workspace"
    if containers:
        scope += f" ({containers[-1]})"
    return ResourceResolution(key, getattr(entry, "kind", ""), entry, scope, pool)


def _iter_binding_expressions(text: str):
    pattern = re.compile(r"\{(?:Binding|CompiledBinding|ReflectionBinding)\b[^{}]*\}", re.I)
    for m in pattern.finditer(text):
        expr = m.group(0)
        body = re.sub(r"^\{(?:Binding|CompiledBinding|ReflectionBinding)\b", "", expr, flags=re.I)
        path_match = re.search(r"(?:Path\s*=\s*)?(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", body, re.I)
        if path_match:
            yield m.start(), expr, path_match.group("path")


def analyze_bindings(
    text: str,
    path: Path,
    root_type: str | None,
    index: CSharpSemanticIndex | None,
) -> list[BindingIssue]:
    """Validate binding paths and offer typo suggestions."""
    if not index or not root_type:
        return []
    issues: list[BindingIssue] = []
    for offset, expression, binding_path in _iter_binding_expressions(text):
        current_type = root_type
        parts = binding_path.split(".")
        for i, part in enumerate(parts):
            props = index.properties_for(current_type)
            prop = next((p for p in props if p.name.casefold() == part.casefold()), None)
            if prop is None:
                names = [p.name for p in props]
                suggestion = get_close_matches(part, names, n=1, cutoff=0.65)
                message = f"'{part}' does not exist on {current_type}."
                if suggestion:
                    message += f" Did you mean '{suggestion[0]}'?"
                line, column = line_col(text, offset + max(0, expression.find(part)))
                issues.append(BindingIssue(path, line, column, expression, message, suggestion[0] if suggestion else None))
                break
            if i < len(parts) - 1:
                target = index.find_type(prop.type_name)
                if target is None:
                    break
                current_type = target.full_name
    return issues


def safe_replace_binding(text: str, old: str, new: str) -> tuple[str, int]:
    """Rename an exact binding path segment, never arbitrary source text."""
    count = 0
    pattern = re.compile(r"(\{(?:Binding|CompiledBinding|ReflectionBinding)\b[^{}]*?)(\b" + re.escape(old) + r"\b)", re.I)
    def repl(m):
        nonlocal count
        count += 1
        return m.group(1) + new
    return pattern.sub(repl, text), count


def rename_resource_text(text: str, old: str, new: str) -> tuple[str, int]:
    patterns = [
        re.compile(r"(x:Key\s*=\s*[\"'])" + re.escape(old) + r"([\"'])"),
        re.compile(r"(\{(?:StaticResource|DynamicResource)\s+)" + re.escape(old) + r"(\s*\})"),
    ]
    count = 0
    for pattern in patterns:
        text, n = pattern.subn(r"\1" + new + r"\2", text)
        count += n
    return text, count


def extract_resource(
    text: str,
    value: str,
    key: str,
    resource_type: str = "SolidColorBrush",
    target_offset: int | None = None,
    reference_type: str | None = None,
) -> str:
    """Extract a literal AXAML attribute value into the nearest Resources block.

    The editor passes the selected value and its offset.  The implementation
    deliberately refuses to extract markup extensions/bindings and chooses a
    sensible resource representation for common literal values.  Existing
    callers can still force ``resource_type`` for brush extraction.
    """
    if not value or not key:
        return text

    key = key.strip()
    if not re.fullmatch(r"[A-Za-z_][\w.:-]*", key):
        return text

    # Resolve the selected occurrence against the original document before
    # inserting the resource itself.
    target_start = None
    if target_offset is not None:
        matches = list(re.finditer(re.escape(value), text))
        if matches:
            target_start = min(matches, key=lambda m: abs(m.start() - target_offset)).start()

    # A resource extraction should operate on a literal value, not another
    # markup extension.
    if value.strip().startswith("{") and value.strip().endswith("}"):
        return text

    import html
    escaped = html.escape(value, quote=False)

    # Infer the resource representation when the caller did not explicitly
    # provide one.  Color literals are the common Avalonia brush case.
    is_color = bool(re.fullmatch(
        r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", value.strip()
    ))
    if resource_type == "SolidColorBrush" and not is_color:
        resource_type = "x:String"

    if resource_type == "SolidColorBrush":
        resource = f'<SolidColorBrush x:Key="{key}" Color="{html.escape(value, quote=True)}" />'
    elif resource_type == "x:String":
        resource = f'<x:String x:Key="{key}">{escaped}</x:String>'
    else:
        resource = f'<{resource_type} x:Key="{key}">{escaped}</{resource_type}>'

    insertion_at = None
    insertion_text = ""
    match = re.search(r"<([A-Za-z_][\w.:-]*\.Resources|Resources)\s*>", text)
    if match:
        end_tag = text.find("</", match.end())
        if end_tag >= 0:
            insertion_at = end_tag
            insertion_text = "\n    " + resource + "\n"
    else:
        root = re.search(r"<([A-Za-z_][\w.:-]*)(?:\s[^<>]*?)?>", text, re.S)
        if root:
            insertion_at = root.end()
            insertion_text = (
                f'\n    <{root.group(1)}.Resources>\n'
                f'        {resource}\n'
                f'    </{root.group(1)}.Resources>'
            )

    if insertion_at is not None:
        text = text[:insertion_at] + insertion_text + text[insertion_at:]
        if target_start is not None and insertion_at <= target_start:
            target_start += len(insertion_text)

    reference_type = (reference_type or ("DynamicResource" if resource_type == "SolidColorBrush" else "StaticResource"))
    if reference_type not in {"StaticResource", "DynamicResource"}:
        reference_type = "StaticResource"
    replacement = "{" + reference_type + " " + key + "}"
    if target_start is not None:
        return text[:target_start] + replacement + text[target_start + len(value):]
    return re.sub(re.escape(value), replacement, text, count=1)

def extract_style(text: str, control: str, key: str, properties: dict[str, str]) -> str:
    lines = [f'<Style Selector="{control}" x:Key="{key}">']
    for name, value in properties.items():
        lines.append(f'    <Setter Property="{name}" Value="{value}" />')
    lines.append('</Style>')
    style = "\n".join(lines)

    match = re.search(r"<([A-Za-z_][\w.:-]*\.Resources|Resources)(?:\s[^>]*)?>", text)
    if match:
        resources_tag = match.group(1)
        closing_name = resources_tag
        end_match = re.search(r"</" + re.escape(closing_name) + r"\s*>", text[match.end():])
        if end_match:
            close_start = match.end() + end_match.start()
            close_line_start = text.rfind("\n", 0, close_start) + 1
            open_line_start = text.rfind("\n", 0, match.start()) + 1
            resources_indent = re.match(r"[ \t]*", text[open_line_start:match.start()]).group(0)
            child_indent = resources_indent + "    "
            indented_style = "\n".join(child_indent + line for line in style.split("\n"))
            closing_end = match.end() + end_match.end()
            closing_tag = text[close_start:closing_end]
            text = (
                text[:close_line_start]
                + indented_style
                + "\n"
                + resources_indent
                + closing_tag
                + text[match.end() + end_match.end():]
            )
    else:
        root = re.search(r"<([A-Za-z_][\w.:-]*)[^<>]*>", text)
        if root:
            root_name = root.group(1)
            indented_style = "\n".join("        " + line for line in style.split("\n"))
            block = (
                f"\n    <{root_name}.Resources>\n"
                f"{indented_style}\n"
                f"    </{root_name}.Resources>"
            )
            text = text[:root.end()] + block + text[root.end():]
    return text


def convert_attribute_to_property_element(text: str, control: str, prop: str) -> str:
    pattern = re.compile(
        r"(<" + re.escape(control) + r"\b[^<>]*?)\s+"
        + re.escape(prop)
        + r"\s*=\s*([\"\'])(.*?)\2([^<>]*>)",
        re.S,
    )

    def repl(m):
        prefix, value, suffix = m.group(1), m.group(3), m.group(4)
        suffix = re.sub(r"\s*/?\s*>$", ">", suffix)
        line_start = text.rfind("\n", 0, m.start()) + 1
        indent_match = re.match(r"[ \t]*", text[line_start:m.start()])
        control_indent = indent_match.group(0) if indent_match else ""
        child_indent = control_indent + "    "
        return (
            f"{prefix}{suffix}\n"
            f"{child_indent}<{control}.{prop}>{value}</{control}.{prop}>\n"
            f"{control_indent}</{control}>"
        )

    return pattern.sub(repl, text, count=1)


def related_files(path: Path, project_root: Path | None = None) -> list[Path]:
    """Find Avalonia files related to *path*.

    Relationships are inferred from both conventional filenames and AXAML
    metadata.  In particular, a view can explicitly declare its ViewModel
    with ``x:DataType="vm:MainViewModel"``; that relationship is more
    reliable than assuming ``Test.axaml`` must have ``TestViewModel.cs``.

    The search is deliberately filesystem-based so the command also works
    before the project index has finished rebuilding.
    """
    path = path.resolve()
    root = (project_root or path.parent).resolve()

    def valid(p: Path) -> bool:
        return (
            p.exists()
            and p.is_file()
            and p.resolve() != path
            and not any(part in {".git", "bin", "obj"} for part in p.parts)
        )

    found: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path | None) -> None:
        if p is None:
            return
        p = p.resolve()
        if valid(p) and p not in seen:
            seen.add(p)
            found.append(p)

    # Search locally first, then the project tree.  rglob is intentionally
    # restricted to the project root rather than the entire workspace.
    def find_name(name: str) -> list[Path]:
        local = path.parent / name
        result = [local] if valid(local) else []
        if root != path.parent:
            result.extend(p for p in root.rglob(name) if valid(p))
        return result

    stem = path.stem
    lower_name = path.name.casefold()

    # Conventional companion files.
    if lower_name.endswith(".axaml") or lower_name.endswith(".xaml"):
        for name in (
            f"{stem}.axaml.cs",
            f"{stem}.xaml.cs",
            f"{stem}ViewModel.cs",
        ):
            for candidate in find_name(name):
                add(candidate)

        if stem.casefold().endswith("view"):
            base = stem[:-4]
            for name in (
                f"{base}ViewModel.cs",
                f"{base}.axaml",
                f"{base}.xaml",
            ):
                for candidate in find_name(name):
                    add(candidate)

        # Read AXAML metadata so explicit x:Class/x:DataType relationships
        # work even when filenames and folders do not follow conventions.
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            text = ""

        aliases = dict(re.findall(
            r'\bxmlns:([A-Za-z_]\w*)\s*=\s*["\']using:([^"\']+)["\']',
            text,
        ))

        data_match = re.search(
            r'\bx:DataType\s*=\s*["\']([^"\']+)["\']', text
        )
        if data_match:
            value = data_match.group(1).strip()
            if value.startswith("{x:Type") and value.endswith("}"):
                value = value[len("{x:Type"): -1].strip()
            if ":" in value:
                prefix, type_name = value.split(":", 1)
                namespace = aliases.get(prefix)
                full_name = f"{namespace}.{type_name}" if namespace else type_name
            else:
                full_name = value

            vm_name = full_name.rsplit(".", 1)[-1]
            for candidate in find_name(f"{vm_name}.cs"):
                add(candidate)

            # If the file name doesn't match the declared type, locate the
            # declaration by namespace + class name as a fallback.
            if not any(p.stem == vm_name for p in found):
                namespace, _, simple = full_name.rpartition(".")
                pattern = re.compile(
                    r'\b(?:class|record|struct)\s+' + re.escape(simple) + r'\b'
                )
                for candidate in root.rglob("*.cs"):
                    if not valid(candidate):
                        continue
                    try:
                        source = candidate.read_text(encoding="utf-8")
                    except (OSError, UnicodeError):
                        continue
                    if pattern.search(source):
                        if not namespace or re.search(
                            r'\bnamespace\s+' + re.escape(namespace) + r'\s*(?:[;{])',
                            source,
                        ):
                            add(candidate)

        class_match = re.search(
            r'\bx:Class\s*=\s*["\']([^"\']+)["\']', text
        )
        if class_match:
            class_name = class_match.group(1).rsplit(".", 1)[-1]
            for name in (f"{class_name}.axaml.cs", f"{class_name}.xaml.cs"):
                for candidate in find_name(name):
                    add(candidate)

    elif lower_name.endswith(".axaml.cs") or lower_name.endswith(".xaml.cs"):
        view_stem = path.name.rsplit(".", 2)[0]
        for name in (f"{view_stem}.axaml", f"{view_stem}.xaml", f"{view_stem}ViewModel.cs"):
            for candidate in find_name(name):
                add(candidate)

    elif lower_name.endswith("viewmodel.cs"):
        base = path.stem[:-9]
        for name in (f"{base}.axaml", f"{base}View.axaml", f"{base}.xaml", f"{base}View.xaml"):
            for candidate in find_name(name):
                add(candidate)

    # Final fallback for a plain C# ViewModel whose filename does not encode
    # the exact AXAML view name: scan AXAML x:DataType declarations.
    if lower_name.endswith(".cs") and not lower_name.endswith(".axaml.cs"):
        vm_name = stem
        for candidate in root.rglob("*.axaml"):
            if not valid(candidate):
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            if re.search(
                r'\bx:DataType\s*=\s*["\'][^"\']*(?::|\.)' + re.escape(vm_name) + r'["\']',
                text,
            ) or re.search(
                r'\bx:DataType\s*=\s*["\']' + re.escape(vm_name) + r'["\']',
                text,
            ):
                add(candidate)

    return found


def infer_namespace(project, source_path: Path | None = None) -> str:
    """Best-effort .NET namespace discovery for generated files."""
    project_file = Path(project.project_file)
    try:
        root = ET.parse(project_file).getroot()
        for group in root.findall("PropertyGroup"):
            value = group.findtext("RootNamespace")
            if value and value.strip():
                return value.strip()
    except (OSError, ET.ParseError):
        pass

    search_root = Path(project.root)
    if source_path:
        nearby = source_path.parent / f"{source_path.stem}.axaml.cs"
        files = [nearby] if nearby.exists() else []
    else:
        files = []
    if not files:
        files = list(search_root.rglob("*.cs"))[:200]
    ns_re = re.compile(r"\bnamespace\s+([A-Za-z_][\w.]*)")
    for candidate in files:
        if ".git" in candidate.parts or "bin" in candidate.parts or "obj" in candidate.parts:
            continue
        try:
            match = ns_re.search(candidate.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if match:
            return match.group(1)
    return project.name


def _safe_name(name: str) -> str:
    name = Path(name.strip()).name
    if name.endswith(('.axaml', '.xaml', '.cs')):
        name = Path(name).stem
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("Name must be a valid C# identifier")
    return name


def scaffold_view(root: Path, name: str, namespace: str, kind: str = "UserControl") -> dict[Path, str]:
    name = _safe_name(name)
    if kind not in {"UserControl", "Window", "ResourceDictionary"}:
        raise ValueError("kind must be UserControl, Window, or ResourceDictionary")
    if kind == "ResourceDictionary":
        return {root / f"{name}.axaml": '<ResourceDictionary xmlns="https://github.com/avaloniaui" xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" />\n'}
    axaml = f'''<{kind}\n    xmlns="https://github.com/avaloniaui"\n    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"\n    x:Class="{namespace}.{name}">\n</{kind}>\n'''
    cs = f'''using Avalonia.Controls;\n\nnamespace {namespace};\n\npublic partial class {name} : {kind}\n{{\n    public {name}()\n    {{\n        InitializeComponent();\n    }}\n}}\n'''
    return {root / f"{name}.axaml": axaml, root / f"{name}.axaml.cs": cs}


def scaffold_viewmodel(root: Path, name: str, namespace: str) -> dict[Path, str]:
    name = _safe_name(name)
    return {root / f"{name}.cs": f'''using System.ComponentModel;\nusing System.Runtime.CompilerServices;\n\nnamespace {namespace};\n\npublic class {name} : INotifyPropertyChanged\n{{\n    public event PropertyChangedEventHandler? PropertyChanged;\n    protected void OnPropertyChanged([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));\n}}\n'''}
