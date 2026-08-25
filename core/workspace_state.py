"""
Avalonia workspace persistence.

Stores small, versioned workspace metadata outside the project tree.
The live ProjectManager Session is intentionally not serialized.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional


STATE_VERSION = 1


def _state_path(cache_root: Path, root: Path) -> Path:
    key = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()
    return cache_root / "Avalonia" / "workspaces" / f"{key}.json"


def load_workspace_state(
    cache_root: Path,
    root: Path,
) -> Optional[dict[str, Any]]:
    """Load compatible persisted metadata for a workspace."""
    path = _state_path(cache_root, root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None

    if data.get("version") != STATE_VERSION:
        return None

    if Path(data.get("root", "")).resolve() != root.resolve():
        return None

    return data


def save_workspace_state(
    cache_root: Path,
    solution,
) -> None:
    """Persist lightweight workspace metadata atomically."""
    root = solution.root.resolve()
    path = _state_path(cache_root, root)
    path.parent.mkdir(parents=True, exist_ok=True)

    files: dict[str, dict[str, int]] = {}
    for project in solution.projects:
        for source_file in project.index.files:
            try:
                stat = source_file.path.stat()
            except OSError:
                continue
            files[str(source_file.path.resolve())] = {
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }

    data = {
        "version": STATE_VERSION,
        "root": str(root),
        "solution": str(solution.solution.resolve()) if solution.solution else None,
        "projects": [
            {
                "name": project.name,
                "root": str(project.root.resolve()),
                "project_file": str(project.project_file.resolve()),
            }
            for project in solution.projects
        ],
        "startup_project": (
            str(solution.startup_project.project_file.resolve())
            if solution.startup_project is not None
            else None
        ),
        "files": files,
    }

    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)
