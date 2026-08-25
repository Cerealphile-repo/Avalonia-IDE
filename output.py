"""
Avalonia output panel commands.

The actual panel lifecycle and writing helpers live in ``core.output``.
This module is the Sublime command layer that exposes that existing panel
through the Avalonia command system.
"""

from __future__ import annotations

import sublime

from .core.command import AvaloniaWindowCommand
from .core.output import output_panel


_PANEL_NAME = "output.avalonia"


class AvaloniaShowOutputCommand(AvaloniaWindowCommand):
    """
    Show the Avalonia output panel.

    ``AvaloniaShowOutputCommand`` is the canonical command name for the
    menu entry.  The command deliberately does not clear the panel; output
    producers own the panel contents and this command only reveals them.
    """

    def run(self):
        output_panel(self.window)

        self.window.run_command(
            "show_panel",
            {
                "panel": _PANEL_NAME,
            },
        )

    def is_enabled(self):
        return self.window is not None


class AvaloniaOutputCommand(AvaloniaShowOutputCommand):
    """
    Compatibility alias for ``avalonia_output``.

    Older/local menu files may use the shorter command name.  Keeping the
    alias costs nothing and prevents an existing menu entry from becoming
    disabled merely because the command was renamed.
    """

    pass
