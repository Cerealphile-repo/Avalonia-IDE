import sublime
import sublime_plugin


TERMINAL_GROUP = 1
TERMINAL_TITLE = "Avalonia Terminal"
TERMINAL_TAG = "avalonia_terminal"


def is_terminal_view(view):
    """Return True only for the terminal view owned by this plugin."""
    if view is None:
        return False

    if view.settings().get("avalonia_terminal"):
        return True

    # Terminus gives the view its configured title before we get a chance
    # to add our own setting.  Do not let the initial creation event move it.
    return view.name() == TERMINAL_TITLE


def keep_terminal_group_clean(window):
    """
    Group 1 is reserved for the Avalonia terminal.

    Sublime's built-in commands can create/open views in the currently
    focused group.  There is no group-level "terminal only" restriction,
    so enforce that invariant whenever a view is created, loaded, or
    activated.
    """
    if window is None or window.num_groups() <= TERMINAL_GROUP:
        return

    # Keep the terminal itself in Group 1.  Terminus can create the view
    # before its focus_group hook takes effect, so do not assume that a
    # terminal view is already in the terminal group.
    terminal = None
    for view in window.views():
        if is_terminal_view(view):
            terminal = view
            break

    if terminal is not None and terminal not in window.views_in_group(TERMINAL_GROUP):
        window.set_view_index(
            terminal,
            TERMINAL_GROUP,
            len(window.views_in_group(TERMINAL_GROUP))
        )

    # Group 1 is reserved for the terminal.  Anything else that lands there
    # is an ordinary Sublime view and belongs in the IDE group.
    for view in list(window.views_in_group(TERMINAL_GROUP)):
        if is_terminal_view(view):
            continue

        window.set_view_index(
            view,
            0,
            len(window.views_in_group(0))
        )


class AvaloniaTerminalGroupListener(sublime_plugin.EventListener):
    """Prevent ordinary Sublime views from remaining in the terminal group."""

    def _enforce(self, view):
        if view is None:
            return

        window = view.window()
        if window is None or window.num_groups() <= TERMINAL_GROUP:
            return

        # Let Terminus finish creating/configuring its view first.
        sublime.set_timeout(
            lambda: keep_terminal_group_clean(window),
            50
        )

    def on_new(self, view):
        self._enforce(view)

    def on_load(self, view):
        self._enforce(view)

    def on_activated(self, view):
        self._enforce(view)


class AvaloniaTerminalCommand(sublime_plugin.WindowCommand):

    GROUP = TERMINAL_GROUP
    TITLE = TERMINAL_TITLE
    TAG = TERMINAL_TAG

    def run(self):
        window = self.window

        terminal = self.find_terminal(window)

        # If our terminal is already open, close it and
        # remove the terminal group.
        if terminal is not None and window.num_groups() > 1:
            self.hide_terminal(window)
            return

        self.open_terminal(window)

    def find_terminal(self, window):
        for view in window.views():
            if is_terminal_view(view):
                return view

        return None

    def open_terminal(self, window):

        # Create exactly two groups:
        #
        # Group 0 = IDE
        # Group 1 = terminal
        #
        window.set_layout({
            "cols": [0.0, 0.70, 1.0],
            "rows": [0.0, 1.0],
            "cells": [
                [0, 0, 1, 1],
                [1, 0, 2, 1]
            ]
        })

        cwd = window.extract_variables().get("folder", "")

        # Terminus creates the terminal while Group 2
        # is focused.
        window.run_command("terminus_open", {
            "config_name": "Default",
            "cwd": cwd,
            "title": self.TITLE,
            "tag": self.TAG,
            "focus": True,
            "pre_window_hooks": [
                ["focus_group", {"group": self.GROUP}]
            ]
        })

        sublime.set_timeout(
            lambda: self.mark_terminal(window),
            300
        )

    def mark_terminal(self, window):

        for view in window.views():

            if view.name() == self.TITLE:

                view.settings().set(
                    "avalonia_terminal",
                    True
                )

                # Explicitly place the terminal in Group 1.  This is more
                # reliable than relying on Terminus's focus_group hook.
                if view not in window.views_in_group(self.GROUP):
                    window.set_view_index(
                        view,
                        self.GROUP,
                        len(window.views_in_group(self.GROUP))
                    )

                window.focus_view(view)
                return

    def hide_terminal(self, window):

        terminal = self.find_terminal(window)

        if terminal is not None:
            window.focus_view(terminal)
            window.run_command("terminus_close")

        # Return to a single IDE group.
        window.set_layout({
            "cols": [0.0, 1.0],
            "rows": [0.0, 1.0],
            "cells": [
                [0, 0, 1, 1]
            ]
        })

        window.focus_group(0)


class AvaloniaTerminalNewFileCommand(sublime_plugin.WindowCommand):

    def run(self):
        window = self.window

        # If the terminal group isn't present, behave normally.
        if window.num_groups() <= TERMINAL_GROUP:
            window.run_command("new_file")
            return

        # Always create ordinary files in Group 0.
        window.focus_group(0)
        window.run_command("new_file")


class AvaloniaTerminalMoveToGroupCommand(sublime_plugin.WindowCommand):

    def run(self, view=None):

        window = self.window

        if view is None:
            view = window.active_view()

        if view is None:
            return

        # Never allow an ordinary view to be placed in Group 1.
        if is_terminal_view(view):
            return

        window.set_view_index(
            view,
            0,
            len(window.views_in_group(0))
        )

        window.focus_view(view)
