"""
Language service integration foundation.

Provides a bridge between Avalonia project awareness
and external language tooling such as LSP/Roslyn.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sublime

from .domain import Project, SourceFile


@dataclass(frozen=True)
class LanguageStatus:
    """
    Current language service state.
    """

    available: bool
    backend: str | None = None
    message: str = ""


@dataclass(frozen=True)
class LanguageTarget:
    """
    Target workspace understood by language tooling.

    kind:
        solution
        project
    """

    kind: str
    path: Path


@dataclass(frozen=True)
class LanguageDocument:
    """
    Active document for language operations.
    """

    view: sublime.View
    path: Path
    project: Project
    source: SourceFile


class LanguageService:
    """
    Coordinates language tooling.

    This service is intentionally stateless with respect
    to the current workspace. The ProjectManager remains
    the single source of truth for workspace information.
    """

    def __init__(self):

        self._status = LanguageStatus(
            available=False,
            backend=None,
            message="Language service not initialized"
        )

    @property
    def status(self) -> LanguageStatus:

        return self._status

    def initialize(self):

        if self._roslyn_available():

            self._status = LanguageStatus(
                available=True,
                backend="Roslyn",
                message="LSP-Roslyn detected"
            )

        else:

            self._status = LanguageStatus(
                available=False,
                backend=None,
                message="LSP-Roslyn not detected"
            )

    def target(
        self,
        window,
        projects,
    ) -> LanguageTarget | None:
        """
        Return the current language target.

        Workspace information is obtained directly from the
        ProjectManager rather than cached inside the language
        service.
        """

        solution = projects.solution(window)

        if solution is None:
            return None

        if solution.solution is not None:

            return LanguageTarget(
                kind="solution",
                path=solution.solution,
            )

        project = solution.startup_project

        if project is not None:

            return LanguageTarget(
                kind="project",
                path=project.project_file,
            )

        return None

    def document(
        self,
        window,
        projects,
    ) -> LanguageDocument | None:
        """
        Return the active language document.
        """

        view = window.active_view()

        if view is None:
            return None

        filename = view.file_name()

        if filename is None:
            return None

        path = Path(filename).resolve()

        project = projects.project_for_file(
            window,
            path,
        )

        if project is None:
            return None

        source = projects.source_file(
            window,
            path,
        )

        if source is None:
            return None

        return LanguageDocument(
            view=view,
            path=path,
            project=project,
            source=source,
        )

    #
    # ------------------------------------------------------------------
    # LSP Integration
    # ------------------------------------------------------------------
    #

    def _run(
        self,
        window,
        projects,
        command: str,
        args: dict | None = None,
    ) -> bool:
        """
        Execute an LSP command on the active document.
        """

        document = self.document(
            window,
            projects,
        )

        if document is None:
            return False

        document.view.run_command(
            command,
            args or {},
        )

        return True

    def goto_definition(
        self,
        window,
        projects,
    ) -> bool:
        """
        Go to the symbol definition.
        """

        return self._run(
            window,
            projects,
            "lsp_symbol_definition",
        )

    def find_references(
        self,
        window,
        projects,
    ) -> bool:
        """
        Find references to the current symbol.
        """

        return self._run(
            window,
            projects,
            "lsp_symbol_references",
        )

    def rename_symbol(
        self,
        window,
        projects,
    ) -> bool:
        """
        Rename the current symbol.
        """

        return self._run(
            window,
            projects,
            "lsp_symbol_rename",
        )

    def hover(
        self,
        window,
        projects,
    ) -> bool:
        """
        Show hover information.
        """

        return self._run(
            window,
            projects,
            "lsp_hover",
        )

    def format_document(
        self,
        window,
        projects,
    ) -> bool:
        """
        Format the current document.
        """

        return self._run(
            window,
            projects,
            "lsp_format_document",
        )

    def code_actions(
        self,
        window,
        projects,
    ) -> bool:
        """
        Show available code actions.
        """

        return self._run(
            window,
            projects,
            "lsp_code_actions",
        )

    def _roslyn_available(self) -> bool:
        """
        Detect installed LSP-Roslyn package.

        This only checks availability.
        It does not start or control the server.
        """

        packages = Path(
            sublime.packages_path()
        )

        language_server = (
            packages
            / "LSP-Roslyn"
            / "Microsoft.CodeAnalysis.LanguageServer"
            / "content"
            / "LanguageServer"
        )

        return language_server.exists()

    def project_status(self, project):

        return {
            "project": project.name,
            "language": "C#",
            "status": self._status
        }
