"""
Avalonia Path Utilities

Centralized path handling for the plugin.
"""

from __future__ import annotations

from pathlib import Path


class PathResolver:
    """Resolve and normalize project paths."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def resolve(self, filename: str | Path) -> Path:
        path = Path(filename)

        if path.is_absolute():
            return path.resolve()

        return (self.root / path).resolve()

    def relative(self, filename: str | Path) -> str:
        path = self.resolve(filename)

        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)

    def exists(self, filename: str | Path) -> bool:
        return self.resolve(filename).exists()

    def is_project_file(self, filename: str | Path) -> bool:
        return self.resolve(filename).suffix.lower() == ".csproj"

    def is_solution_file(self, filename: str | Path) -> bool:
        return self.resolve(filename).suffix.lower() == ".sln"
