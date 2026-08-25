"""
Diagnostic commands.
"""

from __future__ import annotations

import os

import sublime
import sublime_plugin

from .core import app


def _sync_diagnostics(
    window,
    diagnostics,
):
    """
    Synchronize live diagnostics without replacing any existing
    diagnostic source.

    LSP diagnostics are synchronized from Sublime LSP.

    AXAML diagnostics are synchronized for the currently active
    AXAML document using the existing project resource index.
    """

    diagnostics.sync_lsp(
        window
    )

    view = window.active_view()

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
        return

    resources = app.projects.resources(
        window
    )

    if resources is None:
        return

    from pathlib import Path

    # Use the project manager's authoritative C# semantic index.
    # Resolving a project from the active AXAML path can fail while the
    # workspace cache is being refreshed (for example immediately after a
    # rename), which would silently disable AXAML binding diagnostics.
    csharp_index = app.projects.csharp_index(
        window
    )

    diagnostics.sync_axaml(
        Path(filename),
        resources,
        csharp_index=csharp_index,
    )


class AvaloniaShowDiagnosticsCommand(
    sublime_plugin.WindowCommand
):

    def run(self):

        diagnostics = app.projects.diagnostics(
            self.window
        )

        if diagnostics is None:

            sublime.message_dialog(
                "Avalonia: Diagnostics service is not available."
            )

            return

        _sync_diagnostics(
            self.window,
            diagnostics,
        )

        if not diagnostics.items:

            sublime.message_dialog(
                "Avalonia: No diagnostics."
            )

            return

        items = []

        for diagnostic in diagnostics.items:

            items.append(
                [
                    (
                        f"{diagnostic.severity.upper()} "
                        f"{diagnostic.code}"
                    ),
                    (
                        f"{os.path.basename(diagnostic.file)}:"
                        f"{diagnostic.line}:"
                        f"{diagnostic.column}  "
                        f"{diagnostic.message}"
                    ),
                ]
            )

        self.window.show_quick_panel(
            items,
            self.open,
        )

    def open(
        self,
        index,
    ):

        if index < 0:
            return

        diagnostics = app.projects.diagnostics(
            self.window
        )

        if diagnostics is None:
            return

        if index >= len(
            diagnostics.items
        ):
            return

        diagnostic = diagnostics.items[
            index
        ]

        self.goto(
            diagnostic
        )

    def goto(
        self,
        diagnostic,
    ):

        encoded = (
            f"{diagnostic.file}:"
            f"{diagnostic.line}:"
            f"{diagnostic.column}"
        )

        self.window.open_file(
            encoded,
            sublime.ENCODED_POSITION,
        )


class AvaloniaNextErrorCommand(
    sublime_plugin.WindowCommand
):

    def run(self):

        diagnostics = app.projects.diagnostics(
            self.window
        )

        if diagnostics is None:
            return

        _sync_diagnostics(
            self.window,
            diagnostics,
        )

        diagnostic = diagnostics.next()

        if diagnostic is None:

            sublime.status_message(
                "Avalonia: No diagnostics."
            )

            return

        encoded = (
            f"{diagnostic.file}:"
            f"{diagnostic.line}:"
            f"{diagnostic.column}"
        )

        self.window.open_file(
            encoded,
            sublime.ENCODED_POSITION,
        )


class AvaloniaPreviousErrorCommand(
    sublime_plugin.WindowCommand
):

    def run(self):

        diagnostics = app.projects.diagnostics(
            self.window
        )

        if diagnostics is None:
            return

        _sync_diagnostics(
            self.window,
            diagnostics,
        )

        diagnostic = diagnostics.previous()

        if diagnostic is None:

            sublime.status_message(
                "Avalonia: No diagnostics."
            )

            return

        encoded = (
            f"{diagnostic.file}:"
            f"{diagnostic.line}:"
            f"{diagnostic.column}"
        )

        self.window.open_file(
            encoded,
            sublime.ENCODED_POSITION,
        )


class AvaloniaClearDiagnosticsCommand(
    sublime_plugin.WindowCommand
):

    def run(self):

        diagnostics = app.projects.diagnostics(
            self.window
        )

        if diagnostics is not None:

            diagnostics.clear()

        sublime.status_message(
            "Avalonia: Diagnostics cleared."
        )
