"""
Compiler, language-service, and AXAML diagnostics.

Stores diagnostic messages from:

- dotnet compiler output
- LSP/Roslyn language services
- semantic AXAML analysis

and provides navigation support.

AXAML diagnostics are produced by the dedicated semantic AXAML
diagnostic module and are stored alongside compiler and LSP
diagnostics without changing their existing behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from urllib.parse import unquote, urlparse

from .axaml import parse_axaml
from .axaml_diagnostics import build_axaml_diagnostics


_DIAGNOSTIC_RE = re.compile(
    r"^(?P<file>.+?)"
    r"\((?P<line>\d+),(?P<column>\d+)\)"
    r":\s*"
    r"(?P<severity>error|warning)\s+"
    r"(?P<code>[A-Za-z0-9]+)"
    r":\s*"
    r"(?P<message>.*)$"
)


_LSP_SEVERITIES = {
    1: "error",
    2: "warning",
    3: "info",
    4: "hint",
}


@dataclass(slots=True)
class Diagnostic:
    file: str
    line: int
    column: int
    severity: str
    code: str
    message: str
    source: str = "compiler"


class Diagnostics:

    def __init__(self):
        self.clear()

    def clear(self):
        self.items: list[Diagnostic] = []
        self.position = -1

    #
    # --------------------------------------------------------------
    # dotnet compiler diagnostics
    # --------------------------------------------------------------
    #

    def parse(
        self,
        text: str,
    ):
        """
        Parse one line of dotnet compiler output.

        Example:

            MainWindow.cs(10,5): error CS1002: message

        Also accepts absolute paths:

            /home/user/project/MainWindow.cs(10,5): error CS1002: message
        """

        if not text:
            return None

        line = text.strip()

        if not line:
            return None

        match = _DIAGNOSTIC_RE.match(line)

        if match is None:
            return None

        diagnostic = Diagnostic(
            file=match.group("file").strip(),
            line=int(match.group("line")),
            column=int(match.group("column")),
            severity=match.group("severity").lower(),
            code=match.group("code"),
            message=match.group("message").strip(),
            source="compiler",
        )

        self.items.append(diagnostic)

        return diagnostic

    #
    # --------------------------------------------------------------
    # LSP / Roslyn diagnostics
    # --------------------------------------------------------------
    #

    @staticmethod
    def _uri_to_path(
        uri: str,
    ) -> str | None:
        """
        Convert a file URI into a normalized local filesystem path.
        """

        if not uri:
            return None

        parsed = urlparse(uri)

        if parsed.scheme != "file":
            return None

        path = unquote(parsed.path)

        if parsed.netloc and parsed.netloc not in (
            "",
            "localhost",
        ):
            path = f"//{parsed.netloc}{path}"

        if not path:
            return None

        return str(
            Path(path).resolve()
        )

    @staticmethod
    def _lsp_severity(
        severity,
    ) -> str:
        """
        Convert an LSP severity value into the internal severity name.
        """

        if isinstance(
            severity,
            int,
        ):
            return _LSP_SEVERITIES.get(
                severity,
                "info",
            )

        if severity is None:
            return "info"

        return str(
            severity
        ).lower()

    def parse_lsp(
        self,
        uri: str,
        severity: str | int | None,
        message: str,
        line: int,
        column: int,
        code: str = "",
    ):
        """
        Add a diagnostic received from an LSP server.

        LSP uses zero-based line/column positions. Internally we store
        one-based line/column positions for Sublime's encoded positions.
        """

        file_path = self._uri_to_path(
            uri
        )

        if file_path is None:
            return None

        diagnostic = Diagnostic(
            file=file_path,
            line=int(line) + 1,
            column=int(column) + 1,
            severity=self._lsp_severity(
                severity
            ),
            code=(
                str(code)
                if code is not None
                else ""
            ),
            message=str(
                message or ""
            ).strip(),
            source="lsp",
        )

        self.items.append(
            diagnostic
        )

        return diagnostic

    def sync_lsp(
        self,
        window,
    ) -> int:
        """
        Synchronize the diagnostics stored by Sublime LSP into this
        service.

        Sublime LSP owns the language-server lifecycle and receives
        ``textDocument/publishDiagnostics`` notifications. Its
        diagnostics storage is therefore the authoritative source for
        live LSP/Roslyn diagnostics.

        This method copies that state into the Avalonia diagnostic list
        without starting another language server.
        """

        self.items = [
            diagnostic
            for diagnostic in self.items
            if diagnostic.source != "lsp"
        ]

        try:
            from LSP.plugin.core.registry import (
                windows as lsp_windows,
            )
        except Exception:
            return 0

        try:
            manager = lsp_windows.lookup(
                window
            )
        except Exception:
            return 0

        if manager is None:
            return 0

        seen = set()
        count = 0

        try:
            sessions = list(
                manager.get_sessions()
            )
        except Exception:
            return 0

        for session in sessions:

            try:
                diagnostics_by_uri = (
                    session.diagnostics.get_diagnostics()
                )
            except Exception:
                continue

            for uri, diagnostics in (
                diagnostics_by_uri.items()
            ):

                for diagnostic in diagnostics:

                    try:
                        start = diagnostic[
                            "range"
                        ][
                            "start"
                        ]

                        line = int(
                            start["line"]
                        )

                        column = int(
                            start["character"]
                        )

                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                    ):
                        continue

                    severity = diagnostic.get(
                        "severity"
                    )

                    code = diagnostic.get(
                        "code",
                        "",
                    )

                    message = diagnostic.get(
                        "message",
                        "",
                    )

                    file_path = self._uri_to_path(
                        uri
                    )

                    if file_path is None:
                        continue

                    severity_name = (
                        self._lsp_severity(
                            severity
                        )
                    )

                    key = (
                        file_path,
                        line,
                        column,
                        severity_name,
                        (
                            str(code)
                            if code is not None
                            else ""
                        ),
                        str(
                            message or ""
                        ),
                    )

                    if key in seen:
                        continue

                    seen.add(
                        key
                    )

                    self.parse_lsp(
                        uri=str(uri),
                        severity=severity,
                        message=str(
                            message or ""
                        ),
                        line=line,
                        column=column,
                        code=(
                            str(code)
                            if code is not None
                            else ""
                        ),
                    )

                    count += 1

        self.position = -1

        return count

    #
    # --------------------------------------------------------------
    # AXAML semantic diagnostics
    # --------------------------------------------------------------
    #

    @staticmethod
    def _resource_entries(
        resources,
    ) -> list:
        """
        Extract ResourceEntry objects from the project's ResourceIndex.

        ResourceIndex stores entries as:

            by_key: dict[str, tuple[ResourceEntry, ...]]

        The AXAML diagnostic builder operates on the resource entries
        themselves rather than depending on the ResourceIndex
        implementation.
        """

        if resources is None:
            return []

        by_key = getattr(
            resources,
            "by_key",
            None,
        )

        if not isinstance(
            by_key,
            dict,
        ):
            return []

        entries = []

        for values in by_key.values():

            if values is None:
                continue

            for entry in values:

                if entry is None:
                    continue

                entries.append(
                    entry
                )

        return entries

    def sync_axaml(
        self,
        path: Path,
        resources,
        csharp_index=None,
    ) -> int:
        """
        Synchronize semantic AXAML diagnostics for one document.

        Existing AXAML diagnostics for the supplied path are replaced.

        Compiler and LSP diagnostics are left untouched.

        Returns the number of AXAML diagnostics produced.
        """

        if path is None:
            return 0

        try:
            path = Path(
                path
            ).resolve()
        except (
            TypeError,
            ValueError,
            OSError,
        ):
            return 0

        self.items = [
            diagnostic
            for diagnostic in self.items
            if not (
                diagnostic.source == "axaml"
                and Path(
                    diagnostic.file
                ).resolve() == path
            )
        ]

        try:
            document = parse_axaml(
                path
            )
        except Exception:
            self.position = -1
            return 0

        resource_entries = (
            self._resource_entries(
                resources
            )
        )

        # Always include resources declared by the current document.
        # The workspace ResourceIndex can legitimately be stale while an
        # AXAML document has just been edited or renamed. Semantic
        # diagnostics must not report a resource declared in the current
        # document as unresolved merely because the cached workspace index
        # has not caught up yet.
        resource_entries.extend(
            document.resources
        )

        axaml_diagnostics = (
            build_axaml_diagnostics(
                document,
                resource_entries,
                csharp_index=csharp_index,
            )
        )

        for diagnostic in axaml_diagnostics:

            self.items.append(
                Diagnostic(
                    file=str(
                        diagnostic.path
                    ),
                    line=diagnostic.line,
                    column=diagnostic.column,
                    severity=diagnostic.severity,
                    code=diagnostic.code,
                    message=diagnostic.message,
                    source=diagnostic.source,
                )
            )

        self.items.sort(
            key=lambda diagnostic: (
                str(
                    diagnostic.file
                ).lower(),
                diagnostic.line,
                diagnostic.column,
                diagnostic.severity,
                diagnostic.code,
                diagnostic.message,
                diagnostic.source,
            )
        )

        self.position = -1

        return len(
            axaml_diagnostics
        )

    #
    # --------------------------------------------------------------
    # Queries
    # --------------------------------------------------------------
    #

    @property
    def errors(self):

        return [
            diagnostic
            for diagnostic in self.items
            if diagnostic.severity == "error"
        ]

    @property
    def warnings(self):

        return [
            diagnostic
            for diagnostic in self.items
            if diagnostic.severity == "warning"
        ]

    def summary(self):

        return (
            len(self.errors),
            len(self.warnings),
        )

    def current(self):

        if not self.items:
            return None

        if self.position < 0:
            self.position = 0

        return self.items[
            self.position
        ]

    def next(self):

        if not self.items:
            return None

        self.position = (
            self.position + 1
        ) % len(self.items)

        return self.items[
            self.position
        ]

    def previous(self):

        if not self.items:
            return None

        self.position = (
            self.position - 1
        ) % len(self.items)

        return self.items[
            self.position
        ]
