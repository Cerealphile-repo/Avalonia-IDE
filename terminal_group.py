import sublime
import sublime_plugin


TERMINAL_GROUP = 1
TERMINAL_TITLE = "Avalonia Terminal"
TERMINAL_TAG = "avalonia_terminal"


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
            if view.settings().get("avalonia_terminal"):
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

        for view in window.views_in_group(self.GROUP):

            if view.name() == self.TITLE:

                view.settings().set(
                    "avalonia_terminal",
                    True
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

        # Never allow an ordinary view to be placed in Group 2.
        if view.settings().get("avalonia_terminal"):
            return

        window.set_view_index(
            view,
            0,
            len(window.views_in_group(0))
        )

        window.focus_view(view)
