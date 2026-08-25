"""
Avalonia Navigation commands

Provides navigation helpers and Sublime Text commands
for Avalonia source files and resources.
"""

from __future__ import annotations

from pathlib import Path
import re

import sublime
import sublime_plugin

from .core import app
from .core import navigation
from .core.hover_context import get_hover_context
from .core.binding import (
    find_viewmodel_type,
    get_binding_context,
    resolve_data_type,
)
from .core.resource_navigation import find_resource


def current_file(
    window,
):
    view = window.active_view()

    if view is None:
        return None

    filename = view.file_name()

    if filename is None:
        return None

    return Path(filename)


def refresh_workspace(
    window,
):
    """
    Explicitly rebuild the workspace model.

    Normal navigation does not call this.
    """

    return app.refresh(
        window
    )


def open_file(
    window,
    path,
    message,
):
    if path is None:
        sublime.status_message(
            message
        )
        return

    view = window.active_view()

    if view is not None:
        try:
            view.run_command(
                "add_jump_record",
                {
                    "selection": [
                        (region.a, region.b)
                        for region in view.sel()
                    ]
                },
            )
        except Exception:
            pass

    window.open_file(
        str(path)
    )


def _get_axaml_context(
    view,
):
    """
    Return cursor-aware AXAML context.
    """

    if view is None:
        return None

    selections = view.sel()

    if not selections:
        return None

    point = selections[0].begin()

    text = view.substr(
        sublime.Region(
            0,
            view.size(),
        )
    )

    return get_hover_context(
        text,
        point,
    )


def _find_resource_declaration(
    view,
    key,
):
    """
    Find x:Key="key" in the current view.
    """

    text = view.substr(
        sublime.Region(
            0,
            view.size(),
        )
    )

    escaped = (
        key
        .replace("\\", "\\\\")
        .replace(".", "\\.")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("*", "\\*")
        .replace("+", "\\+")
        .replace("?", "\\?")
        .replace("^", "\\^")
        .replace("$", "\\$")
    )

    pattern = (
        r'x:Key\s*=\s*"'
        + escaped
        + r'"'
    )

    region = view.find(
        pattern,
        0,
    )

    if region.empty():
        return None

    return region


def _select_resource_declaration(
    view,
    key,
):
    """
    Select the resource declaration in a view.
    """

    region = _find_resource_declaration(
        view,
        key,
    )

    if region is None:
        sublime.status_message(
            "Avalonia: Resource '{}' opened.".format(
                key
            )
        )
        return

    view.sel().clear()
    view.sel().add(region)
    view.show(
        region,
        True,
    )


def _open_resource(
    window,
    entry,
):
    """
    Open the resource declaration.

    If the resource is already in the active view,
    select its declaration instead of reopening the file.
    """

    active_view = window.active_view()

    if active_view is not None:

        active_filename = active_view.file_name()

        if active_filename is not None:

            try:
                active_path = Path(
                    active_filename
                ).resolve()

                target_path = entry.path.resolve()

                if active_path == target_path:

                    _select_resource_declaration(
                        active_view,
                        entry.key,
                    )

                    return

            except OSError:
                pass

    if active_view is not None:
        try:
            active_view.run_command(
                "add_jump_record",
                {
                    "selection": [
                        (region.a, region.b)
                        for region in active_view.sel()
                    ]
                },
            )
        except Exception:
            pass

    view = window.open_file(
        str(entry.path)
    )

    if view is None:
        return

    def select_key():
        if view.is_loading():
            sublime.set_timeout(
                select_key,
                50,
            )
            return

        _select_resource_declaration(
            view,
            entry.key,
        )

    sublime.set_timeout(
        select_key,
        50,
    )


class AvaloniaGoToDefinitionCommand(
    sublime_plugin.WindowCommand
):
    """
    Navigate to an Avalonia resource declaration
    under the cursor.
    """

    def run(
        self,
    ):
        view = self.window.active_view()

        if view is None:
            return

        filename = view.file_name()

        if not filename:
            return

        if not filename.lower().endswith(
            (
                ".axaml",
                ".xaml",
            )
        ):
            sublime.status_message(
                "Avalonia: Open an AXAML file."
            )
            return

        context = _get_axaml_context(
            view
        )

        print(
            "[Avalonia] navigation context:",
            context,
        )

        if context is None:
            sublime.status_message(
                "Avalonia: No context under cursor."
            )
            return

        key = None

        if context.kind == "resource":
            key = context.token

        elif (
            context.kind == "value"
            and context.property in (
                "Key",
                "x:Key",
            )
        ):
            key = context.token

        if not key:
            sublime.status_message(
                "Avalonia: No resource under cursor."
            )
            return

        resources = app.projects.resources(
            self.window
        )

        if resources is None:
            sublime.status_message(
                "Avalonia: Resource index unavailable."
            )
            return

        entry = find_resource(
            resources,
            key,
        )

        if entry is None:
            sublime.status_message(
                "Avalonia: Resource not found: {}".format(
                    key
                )
            )
            return

        print(
            "[Avalonia] resource:",
            entry,
        )

        _open_resource(
            self.window,
            entry,
        )


class AvaloniaGoToViewCommand(
    sublime_plugin.WindowCommand
):
    """
    Navigate from a code file to its AXAML view.
    """

    def run(
        self,
    ):
        path = current_file(
            self.window
        )

        if path is None:
            return

        target = app.projects.find_view(
            self.window,
            path,
        )

        open_file(
            self.window,
            target,
            "Avalonia: No matching view found.",
        )


class AvaloniaGoToCodeBehindCommand(
    sublime_plugin.WindowCommand
):
    """
    Navigate from AXAML to its code-behind.
    """

    def run(
        self,
    ):
        path = current_file(
            self.window
        )

        if path is None:
            return

        target = app.projects.find_code_behind(
            self.window,
            path,
        )

        open_file(
            self.window,
            target,
            "Avalonia: No matching code-behind found.",
        )


class AvaloniaGoToViewModelCommand(
    sublime_plugin.WindowCommand
):
    """
    Navigate from AXAML to its ViewModel.
    """

    def run(
        self,
    ):
        path = current_file(
            self.window
        )

        if path is None:
            return

        target = app.projects.find_viewmodel(
            self.window,
            path,
        )

        open_file(
            self.window,
            target,
            "Avalonia: No matching ViewModel found.",
        )


class AvaloniaGoToResourceCommand(
    sublime_plugin.WindowCommand
):
    """
    Navigate to an Avalonia keyed resource.
    """

    def run(
        self,
    ):
        def on_done(
            value,
        ):
            key = value.strip()

            if not key:
                return

            resources = app.projects.resources(
                self.window
            )

            if resources is None:
                sublime.status_message(
                    "Avalonia: Resource index unavailable."
                )
                return

            entry = find_resource(
                resources,
                key,
            )

            if entry is None:
                sublime.status_message(
                    "Avalonia: Resource not found: {}".format(
                        key
                    )
                )
                return

            _open_resource(
                self.window,
                entry,
            )

        self.window.show_input_panel(
            "Avalonia Resource:",
            "",
            on_done,
            None,
            None,
        )


class AvaloniaFindResourceReferencesCommand(
    sublime_plugin.WindowCommand
):
    """
    Find AXAML references to a keyed resource.
    """

    def run(
        self,
    ):
        project = app.projects.project(
            self.window
        )

        if project is None:
            sublime.status_message(
                "Avalonia: Project not found."
            )
            return

        reference_index = getattr(
            project.index,
            "resource_reference_index",
            None,
        )

        if reference_index is None:
            sublime.status_message(
                "Avalonia: Resource reference index not available."
            )
            return

        def on_done(
            value,
        ):
            key = value.strip()

            if not key:
                return

            references = navigation.find_resource_references(
                project.index,
                key,
            )

            if not references:
                sublime.status_message(
                    "Avalonia: No resource references found."
                )
                return

            if len(references) == 1:
                self.window.open_file(
                    str(references[0].path)
                )
                return

            items = [
                str(reference.path)
                for reference in references
            ]

            def on_select(
                index,
            ):
                if index < 0:
                    return

                if index >= len(
                    references
                ):
                    return

                self.window.open_file(
                    str(references[index].path)
                )

            self.window.show_quick_panel(
                items,
                on_select,
            )

        self.window.show_input_panel(
            "Avalonia Resource References:",
            "",
            on_done,
            None,
            None,
        )


def _binding_definition(
    view,
):
    """
    Resolve the C# property represented by the AXAML binding under the
    cursor using the existing AXAML binding and C# semantic indexes.

    The semantic index is only used to identify the declaring source file;
    no second C# parser or semantic engine is introduced here.
    """

    filename = view.file_name()

    if not filename:
        return None

    path = Path(filename).resolve()
    text = view.substr(
        sublime.Region(
            0,
            view.size(),
        )
    )
    point = view.sel()[0].begin()

    project = app.projects.project_for_file(
        view.window(),
        path,
    )

    if project is None:
        return None

    index = getattr(
        project.index,
        "csharp_index",
        None,
    )

    if index is None:
        return None

    root_type = resolve_data_type(
        text,
        path,
        csharp_index=index,
        viewmodel_fallback=find_viewmodel_type(
            path,
            index,
        ),
    )

    if not root_type:
        return None

    context = get_binding_context(
        text,
        point,
        root_type=root_type,
        index=index,
    )

    if context is None or context.property is None:
        return None

    property_info = context.property
    declaring_type = index.find_type(
        property_info.declaring_type
    )

    if declaring_type is None:
        return None

    for document in index.documents.values():
        for type_info in document.types:
            if type_info.full_name != declaring_type.full_name:
                continue

            return (
                document.path,
                property_info.name,
            )

    return None


def _select_csharp_property(
    window,
    path,
    property_name,
):
    """Open and select a C# property declaration."""

    active = window.active_view()

    if active is not None:
        try:
            active.run_command(
                "add_jump_record",
                {
                    "selection": [
                        (region.a, region.b)
                        for region in active.sel()
                    ]
                },
            )
        except Exception:
            pass

    view = window.open_file(
        str(path)
    )

    if view is None:
        return

    pattern = re.compile(
        r"\b" + re.escape(property_name) + r"\s*\{"
    )

    def select():
        if view.is_loading():
            sublime.set_timeout(
                select,
                50,
            )
            return

        text = view.substr(
            sublime.Region(
                0,
                view.size(),
            )
        )
        match = pattern.search(text)

        if match is None:
            sublime.status_message(
                "Avalonia: Binding property declaration not found: {}".format(
                    property_name
                )
            )
            return

        point = match.start() + len(property_name)
        view.sel().clear()
        view.sel().add(sublime.Region(point, point))
        view.show(
            point,
            True,
        )

    sublime.set_timeout(
        select,
        50,
    )


class AvaloniaGoToBindingCommand(
    sublime_plugin.WindowCommand
):
    """Navigate from an AXAML binding property to its C# declaration."""

    def is_enabled(self):
        view = self.window.active_view()
        if view is None:
            return False
        filename = view.file_name()
        if not filename:
            return False
        return filename.lower().endswith(
            (".axaml", ".xaml")
        )

    def run(self):
        view = self.window.active_view()
        if view is None:
            return

        target = _binding_definition(
            view
        )

        if target is None:
            sublime.status_message(
                "Avalonia: No C# binding property found under cursor."
            )
            return

        path, property_name = target
        _select_csharp_property(
            self.window,
            path,
            property_name,
        )


class AvaloniaPeekDefinitionCommand(
    sublime_plugin.WindowCommand
):
    """
    Peek at a C# definition using the installed LSP/Roslyn definition
    provider without changing the active editor view.
    """

    def is_enabled(self):
        view = self.window.active_view()
        if view is None:
            return False

        filename = view.file_name()
        return bool(
            filename
            and filename.lower().endswith(".cs")
        )

    def run(self):
        view = self.window.active_view()
        if view is None or not view.sel():
            return

        try:
            from LSP.plugin.core.protocol import Request
            from LSP.plugin.core.registry import windows
            from LSP.plugin.core.url import parse_uri
            from LSP.plugin.core.views import text_document_position_params
        except ImportError:
            sublime.status_message(
                "Avalonia: LSP integration unavailable."
            )
            return

        point = view.sel()[0].begin()
        listener = windows.listener_for_view(view)

        if listener is None:
            sublime.status_message(
                "Avalonia: C# language server unavailable."
            )
            return

        session = listener.session_async(
            "definitionProvider",
            point,
        )

        if session is None:
            sublime.status_message(
                "Avalonia: C# definition provider unavailable."
            )
            return

        request = Request(
            "textDocument/definition",
            text_document_position_params(
                view,
                point,
            ),
            view,
        )

        session.send_request(
            request,
            self._on_definition_response,
        )

    def _on_definition_response(self, response):
        if isinstance(response, dict):
            locations = [response]
        elif isinstance(response, list):
            locations = response
        else:
            locations = []

        if not locations:
            sublime.set_timeout(
                lambda: sublime.status_message(
                    "Avalonia: No definition found."
                )
            )
            return

        if len(locations) == 1:
            sublime.set_timeout(
                lambda: self._show_definition_popup(
                    locations[0]
                )
            )
            return

        items = []

        for location in locations:
            items.append(
                self._location_label(
                    location
                )
            )

        def on_select(index):
            if index < 0 or index >= len(locations):
                return

            self._show_definition_popup(
                locations[index]
            )

        sublime.set_timeout(
            lambda: self.window.show_quick_panel(
                items,
                on_select,
            )
        )

    @staticmethod
    def _location_parts(location):
        from LSP.plugin.core.url import parse_uri

        uri = (
            location.get("targetUri")
            or location.get("uri")
        )

        location_range = (
            location.get("targetSelectionRange")
            or location.get("targetRange")
            or location.get("range")
        )

        if not uri or not location_range:
            return None

        scheme, path = parse_uri(uri)

        if scheme != "file":
            return None

        return Path(path), location_range

    def _location_label(self, location):
        try:
            parts = self._location_parts(
                location
            )
            if parts is None:
                return "Definition"

            path, location_range = parts
            line = (
                location_range["start"]["line"]
                + 1
            )
            return "{}:{}".format(
                path.name,
                line,
            )
        except (KeyError, TypeError, ValueError):
            return "Definition"

    def _show_definition_popup(self, location):
        try:
            parts = self._location_parts(
                location
            )

            if parts is None:
                sublime.status_message(
                    "Avalonia: Invalid definition location."
                )
                return

            path, location_range = parts
            start_line = location_range["start"]["line"]
            end_line = location_range["end"]["line"]
        except (KeyError, TypeError, ValueError):
            sublime.status_message(
                "Avalonia: Invalid definition location."
            )
            return

        source_view = None

        for candidate in self.window.views():
            if candidate.file_name() is None:
                continue

            try:
                if Path(candidate.file_name()).resolve() == path.resolve():
                    source_view = candidate
                    break
            except OSError:
                if candidate.file_name() == str(path):
                    source_view = candidate
                    break

        try:
            if source_view is not None:
                source = source_view.substr(
                    sublime.Region(
                        0,
                        source_view.size(),
                    )
                )
            else:
                source = path.read_text(
                    encoding="utf-8",
                )
        except (OSError, UnicodeError):
            sublime.status_message(
                "Avalonia: Unable to read definition: {}".format(
                    path.name
                )
            )
            return

        lines = source.splitlines()

        if not lines:
            sublime.status_message(
                "Avalonia: Definition is empty."
            )
            return

        context = 8
        first = max(
            0,
            start_line - context,
        )
        last = min(
            len(lines),
            max(
                start_line + context + 1,
                end_line + context + 1,
            ),
        )

        import html

        rendered = []

        for index in range(first, last):
            text = html.escape(
                lines[index]
            )
            prefix = "&gt;" if start_line <= index <= end_line else " "
            rendered.append(
                "<span class='line'>{} {:>5} | {}</span>".format(
                    prefix,
                    index + 1,
                    text,
                )
            )

        content = (
            "<h3>{}</h3>"
            "<pre>{}</pre>"
        ).format(
            html.escape(
                path.name
            ),
            "\n".join(rendered),
        )

        active = self.window.active_view()

        if active is None:
            return

        point = active.sel()[0].begin() if active.sel() else 0

        active.show_popup(
            content,
            flags=sublime.PopupFlags.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            max_width=900,
            max_height=600,
        )


class AvaloniaFindReferencesCommand(
    sublime_plugin.WindowCommand
):
    """
    Find C# references to the symbol under the cursor.

    C# symbol semantics remain owned by the installed LSP/Roslyn
    integration. Resource references use the dedicated command above.
    """

    def is_enabled(
        self,
    ):
        view = self.window.active_view()

        if view is None:
            return False

        filename = view.file_name()

        if not filename:
            return False

        return filename.lower().endswith(".cs")

    def run(
        self,
        include_declaration=False,
        output_mode="quick_panel",
    ):
        view = self.window.active_view()

        if view is None:
            return

        view.run_command(
            "lsp_symbol_references",
            {
                "include_declaration": include_declaration,
                "output_mode": output_mode,
            },
        )


class AvaloniaOutlineCommand(
    sublime_plugin.WindowCommand
):
    """
    Show document structure.

    C# documents are delegated to the installed LSP/Roslyn document
    symbol provider. AXAML documents use the existing Avalonia
    structural index so we do not duplicate the AXAML parser.
    """

    def is_enabled(
        self,
    ):
        view = self.window.active_view()

        if view is None:
            return False

        filename = view.file_name()

        if not filename:
            return False

        return filename.lower().endswith(
            (".cs", ".axaml", ".xaml")
        )

    def run(
        self,
    ):
        view = self.window.active_view()

        if view is None:
            return

        filename = view.file_name()

        if not filename:
            return

        suffix = Path(filename).suffix.lower()

        if suffix == ".cs":
            view.run_command(
                "lsp_document_symbols"
            )
            return

        if suffix not in (".axaml", ".xaml"):
            return

        self._show_axaml_outline(
            view
        )

    def _show_axaml_outline(
        self,
        view,
    ):
        project = app.projects.project(
            self.window
        )

        if project is None:
            sublime.status_message(
                "Avalonia: Project not found."
            )
            return

        filename = view.file_name()

        if not filename:
            return

        try:
            path = Path(filename).resolve()
        except OSError:
            path = Path(filename)

        document = project.index.axaml_documents.get(
            path
        )

        if document is None:
            # The semantic index may use normalized paths; try a direct
            # suffix/name comparison as a safe fallback without reparsing.
            for candidate, candidate_document in (
                project.index.axaml_documents.items()
            ):
                try:
                    if candidate.resolve() == path:
                        document = candidate_document
                        break
                except OSError:
                    if candidate == path:
                        document = candidate_document
                        break

        if document is None:
            sublime.status_message(
                "Avalonia: AXAML document is not indexed."
            )
            return

        elements = getattr(
            document,
            "elements",
            (),
        )

        if not elements:
            sublime.status_message(
                "Avalonia: No AXAML elements found."
            )
            return

        items = []
        targets = []

        children = {}

        for index, element in enumerate(elements):
            parent = getattr(
                element,
                "parent_index",
                None,
            )
            children.setdefault(
                parent,
                [],
            ).append(index)

        def append_element(
            index,
            depth,
        ):
            element = elements[index]

            type_name = getattr(
                element,
                "type_name",
                "Element",
            )

            x_name = getattr(
                element,
                "x_name",
                None,
            )

            label = type_name

            if x_name:
                label += "  (x:Name={})".format(
                    x_name
                )

            items.append(
                "{}{}".format(
                    "  " * depth,
                    label,
                )
            )
            targets.append(
                element
            )

            for child in children.get(
                index,
                (),
            ):
                append_element(
                    child,
                    depth + 1,
                )

        for root in children.get(
            None,
            (),
        ):
            append_element(
                root,
                0,
            )

        def on_select(
            index,
        ):
            if index < 0 or index >= len(targets):
                return

            element = targets[index]

            line = max(
                0,
                getattr(
                    element,
                    "line",
                    1,
                ) - 1,
            )
            column = max(
                0,
                getattr(
                    element,
                    "column",
                    1,
                ) - 1,
            )

            point = view.text_point(
                line,
                column,
            )

            view.sel().clear()
            view.sel().add(
                sublime.Region(
                    point,
                    point,
                )
            )
            view.show(
                point,
                True,
            )

        self.window.show_quick_panel(
            items,
            on_select,
        )
