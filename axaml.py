"""
Avalonia AXAML document commands.

AXAML formatting uses the bundled XAML Styler.  The bundled Avalonia
language server currently exposes completion/hover/text synchronization,
not semantic rename or code-action providers, so those commands use
explicit AXAML-aware editor operations instead of silently invoking
unsupported LSP methods.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile

import sublime
import sublime_plugin

from .core.axaml_context import get_axaml_context


def _is_axaml_view(view):
    if view is None:
        return False

    filename = view.file_name()
    if filename and filename.lower().endswith((".axaml", ".xaml")):
        return True

    syntax = view.settings().get("syntax", "")
    return syntax.lower().endswith(("avalonia.sublime-syntax", "xaml.sublime-syntax"))


def _text(view):
    return view.substr(sublime.Region(0, view.size()))


def _styler_path():
    return Path(__file__).resolve().parent / "language-server" / "xaml-styler" / "xstyler"


def _format_text(source: str) -> str | None:
    styler = _styler_path()
    if not styler.is_file():
        return None

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".axaml",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(source)
        path = Path(handle.name)

    try:
        result = subprocess.run(
            [str(styler), "-f", str(path), "-i"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def _replace_text(view, source: str, updated: str):
    if updated == source:
        sublime.status_message("Avalonia: No changes were required.")
        return

    view.run_command(
        "avalonia_replace_axaml_text",
        {"text": updated},
    )


class AvaloniaReplaceAxamlTextCommand(sublime_plugin.TextCommand):
    """Replace an AXAML document as one undoable edit."""

    def run(self, edit, text):
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)


class AvaloniaReplaceTextCommand(sublime_plugin.TextCommand):
    """Replace an arbitrary editor document as one undoable edit."""

    def run(self, edit, text):
        self.view.replace(edit, sublime.Region(0, self.view.size()), text)


def _cursor_on_attribute_value(source: str, point: int, attribute: str):
    """Return the quoted value under the cursor for an AXAML attribute."""

    pattern = re.compile(
        rf'{re.escape(attribute)}\s*=\s*(["\'])([^"\']*)\1'
    )
    for match in pattern.finditer(source):
        value_start = match.start(2)
        value_end = match.end(2)
        if value_start <= point <= value_end:
            return match.group(2)
    return None


def _codebehind_path(view):
    filename = view.file_name()
    if not filename:
        return None
    return Path(filename).with_suffix(Path(filename).suffix + ".cs")


class AvaloniaAxamlRenameCommand(sublime_plugin.WindowCommand):
    """Rename a supported AXAML symbol at the cursor."""

    def is_enabled(self):
        return _is_axaml_view(self.window.active_view())

    def run(self):
        view = self.window.active_view()
        if not _is_axaml_view(view):
            return

        source = _text(view)
        point = view.sel()[0].begin() if view.sel() else 0

        class_name = _cursor_on_attribute_value(source, point, "x:Class")
        if class_name is not None:
            old_name = class_name.rsplit(".", 1)[-1]
            self._rename_class(view, source, class_name, old_name)
            return

        axaml_name = _cursor_on_attribute_value(source, point, "x:Name")
        if axaml_name is not None:
            self._rename_axaml_name(view, source, axaml_name)
            return

        sublime.status_message(
            "Avalonia: AXAML Rename supports x:Class and x:Name; place the cursor on the name."
        )

    def _rename_class(self, view, source, old_full, old_name):
        namespace = old_full.rsplit(".", 1)[0] if "." in old_full else ""

        def on_done(new_name):
            new_name = new_name.strip()
            if not new_name or new_name == old_name:
                return
            if not re.fullmatch(r"[A-Za-z_]\w*", new_name):
                sublime.status_message("Avalonia: Invalid class name.")
                return

            new_full = f"{namespace}.{new_name}" if namespace else new_name
            updated = source.replace(old_full, new_full, 1)

            codebehind = _codebehind_path(view)
            if codebehind is not None and codebehind.is_file():
                codebehind_view = self.window.open_file(str(codebehind))
                if codebehind_view is None:
                    sublime.status_message("Avalonia: Could not open the code-behind file.")
                    return

                def update_codebehind():
                    if codebehind_view.is_loading():
                        sublime.set_timeout(update_codebehind, 50)
                        return

                    cs = _text(codebehind_view)
                    cs_updated = _rename_codebehind_class(cs, old_name, new_name)
                    if cs_updated != cs:
                        codebehind_view.run_command(
                            "avalonia_replace_text",
                            {"text": cs_updated},
                        )
                        codebehind_view.run_command("save")

                    _replace_text(view, source, updated)
                    view.run_command("save")
                    sublime.status_message(
                        f"Avalonia: Renamed class {old_name} to {new_name}."
                    )

                sublime.set_timeout(update_codebehind, 50)
                return

            _replace_text(view, source, updated)
            view.run_command("save")
            sublime.status_message(
                f"Avalonia: Renamed class {old_name} to {new_name}."
            )

        self.window.show_input_panel(
            f"Rename AXAML class ({old_name}):",
            old_name,
            on_done,
            None,
            None,
        )

    def _rename_axaml_name(self, view, source, old_name):
        def on_done(new_name):
            new_name = new_name.strip()
            if not new_name or new_name == old_name:
                return
            if not re.fullmatch(r"[A-Za-z_]\w*", new_name):
                sublime.status_message("Avalonia: Invalid x:Name.")
                return

            pattern = re.compile(
                rf'(x:Name\s*=\s*["\']){re.escape(old_name)}(["\'])'
            )
            updated, count = pattern.subn(
                rf'\g<1>{new_name}\g<2>',
                source,
            )
            if count == 0:
                sublime.status_message("Avalonia: x:Name was not found.")
                return

            _replace_text(view, source, updated)
            view.run_command("save")
            sublime.status_message(
                f"Avalonia: Renamed x:Name {old_name} to {new_name}."
            )

        self.window.show_input_panel(
            f"Rename x:Name ({old_name}):",
            old_name,
            on_done,
            None,
            None,
        )


def _rename_codebehind_class(source: str, old_name: str, new_name: str) -> str:
    """Rename the class declaration and constructors belonging to old_name."""

    class_pattern = re.compile(
        rf'(\bclass\s+){re.escape(old_name)}\b'
    )
    updated, class_count = class_pattern.subn(
        rf'\g<1>{new_name}',
        source,
        count=1,
    )
    if class_count == 0:
        return source

    constructor_pattern = re.compile(
        rf'(\b(?:public|protected|private|internal)?\s*){re.escape(old_name)}(\s*\()'
    )
    return constructor_pattern.sub(
        rf'\g<1>{new_name}\g<2>',
        updated,
    )


class AvaloniaAxamlCodeActionsCommand(sublime_plugin.WindowCommand):
    """Offer concrete AXAML editor actions at the current cursor context."""

    def is_enabled(self):
        return _is_axaml_view(self.window.active_view())

    def run(self):
        view = self.window.active_view()
        if not _is_axaml_view(view):
            return

        source = _text(view)
        point = view.sel()[0].begin() if view.sel() else 0
        context = get_axaml_context(source, point)
        actions = []

        if _cursor_on_attribute_value(source, point, "x:Class") is not None:
            actions.append(("Rename AXAML Class", "avalonia_axaml_rename"))
        elif _cursor_on_attribute_value(source, point, "x:Name") is not None:
            actions.append(("Rename x:Name", "avalonia_axaml_rename"))
        elif context.kind == "resource":
            actions.extend(
                [
                    ("Rename Resource", "avalonia_rename_resource"),
                    ("Go To Resource Definition", "avalonia_go_to_definition"),
                    ("Find Resource References", "avalonia_find_resource_references"),
                ]
            )
        elif context.kind == "binding":
            actions.append(("Go To Binding Property", "avalonia_go_to_binding"))

        actions.append(("Format Document", "avalonia_axaml_format"))

        labels = [item[0] for item in actions]

        def on_select(index):
            if index < 0:
                return
            self.window.run_command(actions[index][1])

        self.window.show_quick_panel(labels, on_select)


class AvaloniaAxamlFormatCommand(sublime_plugin.WindowCommand):
    """Format the current AXAML document with the bundled XAML Styler."""

    def is_enabled(self):
        return _is_axaml_view(self.window.active_view())

    def run(self):
        view = self.window.active_view()
        if not _is_axaml_view(view):
            return

        source = _text(view)
        formatted = _format_text(source)
        if formatted is None:
            sublime.status_message("Avalonia: AXAML formatting failed.")
            return

        _replace_text(view, source, formatted)
        sublime.status_message("Avalonia: AXAML document formatted.")
