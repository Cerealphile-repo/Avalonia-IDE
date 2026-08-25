"""Phase 5 workspace/indexing commands."""

from __future__ import annotations

import sublime
import sublime_plugin
from pathlib import Path

from .core import app


class AvaloniaReindexCommand(sublime_plugin.WindowCommand):
    """Explicitly start a background workspace reindex."""

    def run(self):
        app.projects.rebuild_async(self.window)

    def is_enabled(self):
        return bool(self.window and self.window.folders())


class AvaloniaCancelIndexingCommand(sublime_plugin.WindowCommand):
    """Cancel queued background workspace indexing when possible."""

    def run(self):
        if not app.projects.cancel_indexing(self.window):
            sublime.status_message("Avalonia: No cancellable indexing job")

    def is_enabled(self):
        return app.projects.is_indexing(self.window)

class AvaloniaSettingsCommand(sublime_plugin.WindowCommand):
    """Open the Avalonia configuration quick panel."""

    _OPTIONS = (
        ("indexing_show_status", "Show indexing status"),
        ("indexing_on_startup", "Index workspace on startup"),
        ("workspace_persistence_enabled", "Enable workspace persistence"),
    )

    def run(self):
        self._show_settings_panel()

    def is_enabled(self):
        return bool(self.window)

    def _show_settings_panel(self):
        settings = sublime.load_settings("Avalonia.sublime-settings")
        items = []

        for key, caption in self._OPTIONS:
            value = bool(settings.get(key, True))
            items.append(f"{'[x]' if value else '[ ]'} {caption}")

        items.append("Open full Avalonia settings file")

        self.window.show_quick_panel(
            items,
            self._on_done,
            sublime.MONOSPACE_FONT,
        )

    def _on_done(self, index):
        if index < 0:
            return

        if index == len(self._OPTIONS):
            self.window.open_file(
                str(Path(sublime.packages_path()) / "User" / "Avalonia.sublime-settings")
            )
            return

        key, _ = self._OPTIONS[index]
        settings = sublime.load_settings("Avalonia.sublime-settings")
        settings.set(key, not bool(settings.get(key, True)))
        sublime.save_settings("Avalonia.sublime-settings")
        sublime.status_message("Avalonia: Setting updated")
        self._show_settings_panel()

