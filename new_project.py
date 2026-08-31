"""Create a new Avalonia project without depending on the current workspace."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading

import sublime
import sublime_plugin


_TEMPLATES = [
    ("Avalonia MVVM Application", "avalonia.mvvm"),
    ("Avalonia Application", "avalonia.app"),
    ("Avalonia Cross Platform Application", "avalonia.xplat"),
]


class AvaloniaNewProjectCommand(sublime_plugin.WindowCommand):
    """Create a new Avalonia project in a user-selected directory."""

    def run(self, edit=None):
        self.window.show_input_panel(
            "Project directory (absolute path)",
            "",
            self._directory_entered,
            None,
            None,
        )

    def _directory_entered(self, value):
        raw = value.strip()
        if not raw:
            sublime.error_message(
                "Avalonia: A project directory is required."
            )
            return

        # Do not resolve relative paths against Sublime's current folder.
        # A new project is intentionally independent of the current workspace.
        if not os.path.isabs(raw):
            sublime.error_message(
                "Avalonia: Please enter an absolute project directory path."
            )
            return

        target = Path(os.path.expanduser(raw)).resolve()

        if target.exists():
            if not target.is_dir():
                sublime.error_message(
                    "Avalonia: The selected project path is not a directory."
                )
                return
            try:
                if any(target.iterdir()):
                    sublime.error_message(
                        "Avalonia: The project directory must not already contain files."
                    )
                    return
            except OSError as exc:
                sublime.error_message(
                    f"Avalonia: Cannot inspect the project directory.\n\n{exc}"
                )
                return

        self.window.show_quick_panel(
            [label for label, _ in _TEMPLATES],
            lambda index: self._template_selected(index, target),
            sublime.MONOSPACE_FONT,
            0,
            None,
        )

    def _template_selected(self, index, target):
        if index < 0:
            return

        template = _TEMPLATES[index][1]
        self._create_project(target, template)

    def _create_project(self, target, template):
        if target.exists():
            try:
                if any(target.iterdir()):
                    sublime.error_message(
                        "Avalonia: The project directory is no longer empty."
                    )
                    return
            except OSError as exc:
                sublime.error_message(
                    f"Avalonia: Cannot inspect the project directory.\n\n{exc}"
                )
                return
        else:
            try:
                target.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                sublime.error_message(
                    "Avalonia: The project directory already exists."
                )
                return
            except OSError as exc:
                sublime.error_message(
                    f"Avalonia: Cannot create the project directory.\n\n{exc}"
                )
                return

        settings = sublime.load_settings("Avalonia.sublime-settings")
        executable = settings.get("dotnet_path", "dotnet")
        project_name = target.name

        command = [
            executable,
            "new",
            template,
            "--name",
            project_name,
            "--output",
            str(target),
        ]

        sublime.status_message(
            f"Avalonia: Creating {project_name}…"
        )

        threading.Thread(
            target=self._run_creation,
            args=(command, target),
            daemon=True,
            name="AvaloniaNewProject",
        ).start()

    def _run_creation(self, command, target):
        try:
            process = subprocess.run(
                command,
                cwd=str(target.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        except Exception as exc:
            self._creation_failed(
                target,
                f"Failed to start dotnet: {exc}",
            )
            return

        if process.returncode != 0:
            self._creation_failed(
                target,
                process.stdout.strip() or "dotnet new failed.",
            )
            return

        projects = sorted(target.glob("*.csproj"))
        if not projects:
            self._creation_failed(
                target,
                "dotnet new completed but no .csproj was created.",
            )
            return

        restore = subprocess.run(
            [
                command[0],
                "restore",
                str(projects[0]),
            ],
            cwd=str(target),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

        if restore.returncode != 0:
            self._creation_failed(
                target,
                "Project was created, but dotnet restore failed:\n\n"
                + (restore.stdout.strip() or "dotnet restore failed."),
            )
            return

        sublime.set_timeout(
            lambda: self._open_project(target),
            0,
        )

    def _creation_failed(self, target, message):
        sublime.set_timeout(
            lambda: sublime.error_message(
                f"Avalonia: New project failed.\n\n{message}"
            ),
            0,
        )

    def _open_project(self, target):
        # Reuse the current Sublime window. Preserve any existing project
        # metadata while replacing its folder list with the new project.
        # Sublime's project_data/folders are what drive the Side Bar.
        window = sublime.active_window()
        if window is None:
            sublime.error_message(
                "Avalonia: Project was created, but no Sublime window is available."
            )
            return

        project_data = window.project_data() or {}
        if not isinstance(project_data, dict):
            project_data = {}

        project_data["folders"] = [
            {"path": str(target)}
        ]
        window.set_project_data(project_data)

        # set_project_data updates the project's folder list, but Sublime
        # reloads folder contents asynchronously. Explicitly run the built-in
        # refresh_folder_list command after the project data has been applied
        # so the Side Bar immediately discovers the generated files.
        def refresh():
            current = sublime.active_window()
            if current is None:
                return

            current.run_command("refresh_folder_list")

            sublime.set_timeout(
                lambda: sublime.status_message(
                    f"Avalonia: Created {target.name}."
                ),
                250,
            )

        sublime.set_timeout(refresh, 100)
