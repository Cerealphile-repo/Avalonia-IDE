"""
Execute dotnet commands.
"""

from __future__ import annotations

import sublime

from .app import app


def run_dotnet(
    window,
    arguments,
):
    """
    Execute a dotnet command for the current Avalonia project.

    Workspace state is reused when already available.  A complete
    workspace rebuild is only performed when the project manager has
    marked the workspace dirty.
    """

    project = app.projects.project(
        window
    )

    if project is None:
        sublime.status_message(
            "Avalonia: No project found."
        )
        return

    settings = sublime.load_settings(
        "Avalonia.sublime-settings"
    )

    executable = settings.get(
        "dotnet_path",
        "dotnet",
    )

    command = [
        executable,
        *arguments,
    ]

    runner = app.processes.runner(
        window
    )

    runner.run(
        command,
        cwd=str(
            project.root
        ),
    )
