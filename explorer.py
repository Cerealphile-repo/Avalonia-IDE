"""
Avalonia Project Explorer.

Displays the indexed files for the active Avalonia project
and opens the selected file.
"""

from __future__ import annotations

from pathlib import Path

import sublime
import sublime_plugin

from .core import app


class AvaloniaExplorerCommand(
    sublime_plugin.WindowCommand
):
    """
    Display the files indexed for the active Avalonia project.
    """

    def run(self):

        app.projects.ensure_session(
            self.window
        )

        project = app.projects.project(
            self.window
        )

        if project is None:

            sublime.status_message(
                "Avalonia: Project not found."
            )

            return

        files = project.index.files

        if not files:

            sublime.status_message(
                "Avalonia: No project files found."
            )

            return

        root = project.root.resolve()

        entries = []

        for source_file in files:

            path = source_file.path.resolve()

            try:

                relative = path.relative_to(
                    root
                )

                display = str(
                    relative
                )

            except ValueError:

                display = str(
                    path
                )

            entries.append(
                (
                    display,
                    source_file,
                )
            )

        entries.sort(
            key=lambda entry: entry[0].lower()
        )

        items = [
            entry[0]
            for entry in entries
        ]

        def on_select(index):

            if index == -1:
                return

            source_file = entries[index][1]

            self.window.open_file(
                str(source_file.path)
            )

        self.window.show_quick_panel(
            items,
            on_select,
        )
