"""
Avalonia Phase 4 commands.

This module adds Avalonia-specific resource rename support.

C# semantics remain owned by LSP/Roslyn.
AXAML parsing and resource indexing remain owned by the existing core
semantic model.
"""

from __future__ import annotations

from pathlib import Path
import re

import sublime
import sublime_plugin

from .core import app


_RESOURCE_KEY_RE = re.compile(
    r"""
    \bx:Key\s*=\s*
    (?P<quote>["'])
    (?P<key>.*?)
    (?P=quote)
    """,
    re.VERBOSE,
)

_RESOURCE_REFERENCE_RE = re.compile(
    r"""
    \{
    (?P<kind>StaticResource|DynamicResource)
    \s+
    (?P<key>[^{}]+?)
    \}
    """,
    re.VERBOSE,
)


def _text(view) -> str:
    return view.substr(
        sublime.Region(0, view.size())
    )


def _key_under_cursor(view) -> str | None:
    """Return an indexed resource key whose declaration/reference contains the cursor."""
    point = view.sel()[0].begin()

    source = _text(view)

    for match in _RESOURCE_KEY_RE.finditer(source):
        if match.start("key") <= point <= match.end("key"):
            return match.group("key").strip()

    for match in _RESOURCE_REFERENCE_RE.finditer(source):
        if match.start("key") <= point <= match.end("key"):
            return match.group("key").strip()

    return None


def _affected_paths(project, key: str) -> tuple[Path, ...]:
    """Return AXAML files containing the resource declaration or references."""
    index = project.index
    paths: set[Path] = set()

    resource_index = index.resource_index
    if resource_index is not None:
        for entry in resource_index.by_key.get(key, ()):
            paths.add(entry.path.resolve())

    reference_index = index.resource_reference_index
    if reference_index is not None:
        for entry in reference_index.by_key.get(key, ()):
            paths.add(entry.path.resolve())

    return tuple(sorted(paths, key=lambda p: str(p).casefold()))


def _replace_resource_key(source: str, old: str, new: str) -> str:
    """Replace only exact resource declarations and resource references."""
    def declaration(match):
        key = match.group("key")
        if key.strip() != old:
            return match.group(0)
        prefix = match.group(0)[:match.start("key") - match.start()]
        suffix = match.group(0)[match.end("key") - match.start():]
        return prefix + new + suffix

    source = _RESOURCE_KEY_RE.sub(declaration, source)

    def reference(match):
        key = match.group("key")
        if key.strip() != old:
            return match.group(0)
        prefix = match.group(0)[:match.start("key") - match.start()]
        suffix = match.group(0)[match.end("key") - match.start():]
        return prefix + new + suffix

    return _RESOURCE_REFERENCE_RE.sub(reference, source)


class AvaloniaReplaceResourceKeysCommand(sublime_plugin.TextCommand):
    """Replace exact resource-key tokens without rewriting document formatting."""

    def run(self, edit, old, new):
        source = _text(self.view)
        regions = []

        for match in _RESOURCE_KEY_RE.finditer(source):
            if match.group("key").strip() == old:
                regions.append(sublime.Region(match.start("key"), match.end("key")))

        for match in _RESOURCE_REFERENCE_RE.finditer(source):
            if match.group("key").strip() == old:
                regions.append(sublime.Region(match.start("key"), match.end("key")))

        for region in reversed(regions):
            self.view.replace(edit, region, new)


def _open_and_replace(
    window,
    path: Path,
    old: str,
    new: str,
    remaining: list[Path],
):
    """Edit one file with precise token replacements, then continue."""
    view = None

    for candidate in window.views():
        if candidate.file_name() is None:
            continue
        try:
            if Path(candidate.file_name()).resolve() == path.resolve():
                view = candidate
                break
        except OSError:
            pass

    if view is None:
        view = window.open_file(str(path))

    if view is None:
        sublime.status_message(f"Avalonia: Unable to open {path.name}.")
        return

    def edit():
        if view.is_loading():
            sublime.set_timeout(edit, 50)
            return

        source = _text(view)
        updated = _replace_resource_key(source, old, new)

        if updated == source:
            _finish_next(window, old, new, remaining)
            return

        view.run_command(
            "avalonia_replace_resource_keys",
            {"old": old, "new": new},
        )
        view.run_command("save")

        _finish_next(window, old, new, remaining)

    sublime.set_timeout(edit, 50)


def _finish_next(
    window,
    old: str,
    new: str,
    remaining: list[Path],
):
    if remaining:
        path = remaining.pop(0)
        _open_and_replace(
            window,
            path,
            old,
            new,
            remaining,
        )
        return

    sublime.status_message(
        f"Avalonia: Resource '{old}' renamed to '{new}'."
    )

    # Rebuild the project model so subsequent navigation sees the new key.
    try:
        app.refresh(window)
    except Exception:
        pass


class AvaloniaRenameResourceCommand(
    sublime_plugin.WindowCommand
):
    """Rename an Avalonia x:Key and all indexed Static/DynamicResource references."""

    def is_enabled(self):
        view = self.window.active_view()
        if view is None or not view.file_name():
            return False

        return view.file_name().lower().endswith(
            (".axaml", ".xaml")
        )

    def run(self):
        view = self.window.active_view()
        if view is None:
            return

        project = app.projects.project_for_file(
            self.window,
            Path(view.file_name()).resolve(),
        )

        if project is None:
            sublime.status_message(
                "Avalonia: Project not found."
            )
            return

        old = _key_under_cursor(view)
        if not old:
            sublime.status_message(
                "Avalonia: Place the cursor on an Avalonia resource key."
            )
            return

        resource_index = project.index.resource_index
        if resource_index is None:
            sublime.status_message(
                "Avalonia: Resource index unavailable."
            )
            return

        declarations = resource_index.by_key.get(old, ())
        if not declarations:
            sublime.status_message(
                f"Avalonia: Resource not found: {old}"
            )
            return

        if len(declarations) > 1:
            sublime.status_message(
                "Avalonia: Resource key is ambiguous; "
                "multiple declarations exist."
            )
            return

        paths = list(
            _affected_paths(project, old)
        )

        if not paths:
            sublime.status_message(
                "Avalonia: No indexed resource files found."
            )
            return

        def on_done(value):
            new = value.strip()

            if not new or new == old:
                return

            if any(
                character in new
                for character in ('"', "'", "{", "}", "\n", "\r")
            ):
                sublime.error_message(
                    "Avalonia: Invalid resource key."
                )
                return

            existing = resource_index.by_key.get(new, ())
            if existing:
                sublime.error_message(
                    f"Avalonia: Resource key already exists: {new}"
                )
                return

            # Current file first, then all other affected files.
            current = Path(view.file_name()).resolve()
            paths.sort(
                key=lambda path: (
                    0 if path == current else 1,
                    str(path).casefold(),
                )
            )

            _open_and_replace(
                self.window,
                paths.pop(0),
                old,
                new,
                paths,
            )

        self.window.show_input_panel(
            "Avalonia Resource Name:",
            old,
            on_done,
            None,
            None,
        )
