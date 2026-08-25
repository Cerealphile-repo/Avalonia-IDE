"""
Avalonia Project Listener

Keeps the application services synchronized with the current window
and updates semantic AXAML diagnostics when AXAML documents change.

Workspace discovery and indexing are cached by ProjectManager.

Normal file loading does not rebuild the workspace.

Solution/project changes invalidate the cached workspace lazily.
"""

from __future__ import annotations

from pathlib import Path

import sublime_plugin

from .core import app


class AvaloniaProjectListener(
    sublime_plugin.EventListener
):
    """
    Synchronize application services with workspace changes.
    """

    def on_load(
        self,
        view,
    ):
        """
        Ensure the workspace session exists when a file is loaded.

        Loading an ordinary file must not force a complete workspace
        rebuild. ProjectManager owns workspace caching and will create
        the session only when one does not already exist.

        AXAML files also receive an initial semantic diagnostic scan.
        """

        window = view.window()

        if window is None:
            return

        session = app.projects.ensure_session(
            window
        )

        if session is None:
            return

        self._sync_axaml(
            window,
            view,
        )

    def on_post_save(
        self,
        view,
    ):
        """
        Synchronize workspace state after a file is saved.

        Solution and project files invalidate the cached workspace
        lazily. The expensive rebuild is deferred until the next
        feature actually needs the updated workspace.

        AXAML files are scanned for semantic diagnostics directly
        without rebuilding the workspace.
        """

        window = view.window()

        if window is None:
            return

        filename = view.file_name()

        if filename is None:
            return

        lower_filename = filename.lower()

        #
        # ------------------------------------------------------------------
        # Workspace Structure Changes
        # ------------------------------------------------------------------
        #
        # Saving a solution or project can change the filesystem/project
        # model. Do not rebuild immediately. Mark the cached workspace
        # dirty and let the next feature request rebuild it if necessary.
        #

        if (
            lower_filename.endswith(".sln")
            or lower_filename.endswith(".csproj")
        ):
            app.projects.mark_dirty(
                window
            )

            return

        #
        # ------------------------------------------------------------------
        # AXAML Changes
        # ------------------------------------------------------------------
        #

        if lower_filename.endswith(
            (
                ".axaml",
                ".xaml",
            )
        ):
            self._sync_axaml(
                window,
                view,
            )

    @staticmethod
    def _sync_axaml(
        window,
        view,
    ):
        """
        Synchronize semantic diagnostics for the current AXAML view.

        The existing cached workspace resource index is reused.

        No project refresh is performed for ordinary AXAML edits.
        """

        filename = view.file_name()

        if filename is None:
            return

        lower_filename = filename.lower()

        if not lower_filename.endswith(
            (
                ".axaml",
                ".xaml",
            )
        ):
            return

        app.projects.update_axaml(
            window,
            Path(filename),
        )

        diagnostics = app.projects.diagnostics(
            window
        )

        if diagnostics is None:
            return

        resources = app.projects.resources(
            window
        )

        if resources is None:
            return

        csharp_index = app.projects.csharp_index(
            window
        )

        diagnostics.sync_axaml(
            Path(filename),
            resources,
            csharp_index=csharp_index,
        )
