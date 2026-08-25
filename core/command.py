"""
Avalonia Command Base Classes

Provides common functionality for Sublime Text commands.
"""

from pathlib import Path
from typing import Optional

import sublime
import sublime_plugin

from .app import app


class AvaloniaCommandMixin:
    """
    Shared helpers for all Avalonia commands.
    """

    #
    # ------------------------------------------------------------
    # Services
    # ------------------------------------------------------------
    #

    @property
    def logger(self):
        return app.logger

    @property
    def projects(self):
        return app.projects

    @property
    def processes(self):
        return app.processes

    #
    # ------------------------------------------------------------
    # Domain Objects
    # ------------------------------------------------------------
    #

    @property
    def session(self):

        if hasattr(self, "window"):
            return app.projects.session(self.window)

        return None

    @property
    def solution(self):

        if hasattr(self, "window"):
            return app.projects.solution(self.window)

        return None

    @property
    def project(self):

        if hasattr(self, "window"):
            return app.projects.project(self.window)

        return None

    @property
    def diagnostics(self):

        if hasattr(self, "window"):
            return app.projects.diagnostics(self.window)

        return None

    #
    # ------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------
    #

    @property
    def project_root(self) -> Optional[Path]:

        project = self.project

        if project is None:
            return None

        return project.root

    def require_project(self):

        project = self.project

        if project is None:

            self.status("No Avalonia project found.")

            return None

        return project

    def status(self, message: str):

        sublime.status_message("Avalonia: {}".format(message))

    def message(self, message: str):

        sublime.message_dialog(message)

    def error(self, message: str):

        sublime.error_message(message)


class AvaloniaWindowCommand(
    AvaloniaCommandMixin,
    sublime_plugin.WindowCommand,
):
    """
    Base class for window commands.
    """

    pass


class AvaloniaTextCommand(
    AvaloniaCommandMixin,
    sublime_plugin.TextCommand,
):
    """
    Base class for text commands.
    """

    @property
    def window(self):

        return self.view.window()


class AvaloniaApplicationCommand(
    AvaloniaCommandMixin,
    sublime_plugin.ApplicationCommand,
):
    """
    Base class for application commands.
    """

    @property
    def window(self):

        return sublime.active_window()
