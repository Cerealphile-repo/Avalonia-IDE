"""
Avalonia Project Manager

Maintains cached runtime state for each Sublime window.

Workspace discovery and semantic indexing are cached. Normal feature
access reuses the existing session and only rebuilds when the workspace
has explicitly been marked dirty.

A forced rebuild remains available through rebuild().
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Optional, Set

from . import navigation
from .completion_metadata import (
    CompletionMetadataIndex,
    build_completion_metadata_index,
)
from .diagnostics import Diagnostics
from .domain import (
    Project,
    Solution,
    SourceFile,
)
from .log import log
from .project import find_project
from .resource import (
    ResourceEntry,
    ResourceIndex,
    merge_resource_indexes,
)
from .solution import build_solution
from .semantic_index import update_axaml_document
from .indexer_service import IndexResult, IndexerService
from .workspace_state import load_workspace_state, save_workspace_state


@dataclass
class Session:
    """
    Runtime state associated with a single Sublime window.
    """

    solution: Solution
    diagnostics: Diagnostics
    resources: ResourceIndex
    completion_metadata: CompletionMetadataIndex


class ProjectManager:
    """
    Maintains one runtime session per Sublime window.

    Workspace discovery and indexing are cached.

    A normal feature request does not rebuild the workspace. A rebuild
    occurs only when:

        - the window has no session yet
        - the workspace has explicitly been marked dirty
        - rebuild() is explicitly requested

    refresh() is intentionally cache-aware. This allows callers such as
    build/run/restore commands to safely request the current workspace
    without forcing an expensive filesystem and semantic rebuild every
    time.
    """

    def __init__(self, indexer: IndexerService | None = None):

        self._indexer = indexer

        self._indexing: Set[int] = set()
        self._generations: Dict[int, int] = {}

        self._sessions: Dict[
            int,
            Session,
        ] = {}

        #
        # Windows whose workspace model must be rebuilt.
        #

        self._dirty: Set[
            int
        ] = set()

        #
        # Completion metadata is static plugin data. There is no reason
        # to rebuild it every time a project is refreshed.
        #

        self._completion_metadata: Optional[
            CompletionMetadataIndex
        ] = None

        self._workspace_state_cache = None
        try:
            import sublime
            self._workspace_state_cache = Path(sublime.cache_path())
        except Exception:
            pass

    #
    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------
    #

    def refresh(
        self,
        window,
    ) -> Optional[Session]:

        """
        Return the current workspace session.

        This method is deliberately cache-aware.

        If a session does not exist, the workspace is built.

        If the workspace has been marked dirty, the workspace is rebuilt.

        Otherwise the existing session is returned unchanged.

        This is the normal entry point for commands that need current
        project services but do not themselves know whether a structural
        workspace change occurred.
        """

        window_id = window.id()

        session = self._sessions.get(
            window_id
        )

        if session is not None:

            if window_id not in self._dirty:

                return session

        self.rebuild_async(window)
        return self._sessions.get(window_id)

    def rebuild_async(
        self,
        window,
    ) -> None:
        """Start a non-blocking workspace rebuild."""

        if self._indexer is None:
            self.rebuild(window)
            return

        window_id = window.id()

        if window_id in self._indexing:
            return

        location = self._cached_project_location(window)
        if location is None:
            location = find_project(window)

        if location is None:
            self.clear(window)
            return

        self._indexing.add(window_id)

        log.info("Background workspace indexing queued.")
        try:
            import sublime
            if sublime.load_settings("Avalonia.sublime-settings").get("indexing_show_status", True):
                sublime.status_message("Avalonia: Indexing workspace…")
        except Exception:
            pass

        generation = self._indexer.submit(
            window_id,
            location,
            self._index_complete,
        )
        self._generations[window_id] = generation


    def _index_complete(
        self,
        result: IndexResult,
    ) -> None:
        """Install completed background index data."""

        self._indexing.discard(result.window_id)

        if result.cancelled:
            log.info("Background workspace indexing cancelled.")
            try:
                import sublime
                if sublime.load_settings("Avalonia.sublime-settings").get("indexing_show_status", True):
                    sublime.status_message("Avalonia: Workspace indexing cancelled")
            except Exception:
                pass
            return

        try:
            import sublime
            if sublime.load_settings("Avalonia.sublime-settings").get("indexing_show_status", True):
                sublime.status_message("Avalonia: Workspace indexing complete")
        except Exception:
            pass

        if self._generations.get(result.window_id) != result.generation:
            log.info("Ignoring stale workspace index result.")
            return

        if result.solution is None:
            return

        old_session = self._sessions.get(
            result.window_id
        )

        diagnostics = (
            old_session.diagnostics
            if old_session is not None
            else Diagnostics()
        )

        self._sessions[result.window_id] = Session(
            solution=result.solution,
            diagnostics=diagnostics,
            resources=self._build_resources(result.solution),
            completion_metadata=self._get_completion_metadata(),
        )

        self._dirty.discard(result.window_id)

        if self._workspace_state_cache is not None and self._workspace_persistence_enabled():
            try:
                save_workspace_state(
                    self._workspace_state_cache,
                    result.solution,
                )
                log.info("Workspace state persisted.")
            except Exception as exc:
                log.warning(f"Workspace state persistence failed: {exc}")

        log.info(
            "Background workspace index installed."
        )


    def rebuild(
        self,
        window,
    ) -> Optional[Session]:

        """
        Force a complete workspace rebuild for a window.

        Existing diagnostics are preserved across the rebuild.

        This is the explicit structural-refresh operation. Callers should
        use this when they know that the solution/project structure has
        changed or when a complete workspace reconstruction is required.
        """

        window_id = window.id()

        location = self._cached_project_location(window)
        if location is None:
            location = find_project(
                window
            )

        if location is None:

            self.clear(
                window
            )

            return None

        old_session = self._sessions.get(
            window_id
        )

        solution = build_solution(
            location
        )

        resources = self._build_resources(
            solution
        )

        completion_metadata = (
            self._get_completion_metadata()
        )

        if old_session is not None:

            diagnostics = (
                old_session.diagnostics
            )

        else:

            diagnostics = Diagnostics()

        session = Session(
            solution=solution,
            diagnostics=diagnostics,
            resources=resources,
            completion_metadata=completion_metadata,
        )

        self._sessions[
            window_id
        ] = session

        self._dirty.discard(
            window_id
        )

        if self._workspace_state_cache is not None and self._workspace_persistence_enabled():
            try:
                save_workspace_state(
                    self._workspace_state_cache,
                    solution,
                )
                log.info("Workspace state persisted.")
            except Exception as exc:
                log.warning(f"Workspace state persistence failed: {exc}")

        log.info(
            "Workspace discovered"
        )

        log.info(
            f"  Root: {solution.root}"
        )

        if solution.solution is not None:

            log.info(
                f"  Solution: {solution.solution.name}"
            )

        else:

            log.info(
                "  Solution: (standalone project)"
            )

        log.info(
            f"  Projects: {len(solution.projects)}"
        )

        if solution.startup_project is not None:

            log.info(
                f"  Startup: {solution.startup_project.name}"
            )

        log.info(
            f"  Resources: {len(resources.by_key)}"
        )

        log.info(
            f"  Completion controls: "
            f"{len(completion_metadata.controls)}"
        )

        return session

    def session(
        self,
        window,
    ) -> Optional[Session]:

        """
        Return the current workspace session.

        If the workspace has been marked dirty, rebuild it first.
        """

        window_id = window.id()

        session = self._sessions.get(
            window_id
        )

        if session is None:

            return self.rebuild(
                window
            )

        if window_id in self._dirty:

            return self.rebuild(
                window
            )

        return session

    def ensure_session(
        self,
        window,
    ) -> Optional[Session]:

        """
        Return the current workspace session.

        This is the preferred entry point for normal feature access.
        """

        return self.session(
            window
        )

    def mark_dirty(
        self,
        window,
    ) -> None:

        """
        Mark the workspace as requiring a rebuild.

        The rebuild itself is deferred until the next feature request.

        This is intentionally cheap. No filesystem traversal or semantic
        parsing occurs here.
        """

        window_id = window.id()

        if window_id not in self._sessions:

            return

        self._dirty.add(
            window_id
        )

        log.info(
            f"Workspace marked dirty: {window_id}"
        )

    def is_indexing(self, window) -> bool:
        """Return whether background indexing is active for a window."""
        return window.id() in self._indexing

    def cancel_indexing(self, window) -> bool:
        """Request cancellation of queued indexing work for a window."""
        window_id = window.id()
        if window_id not in self._indexing:
            return False
        cancelled = False
        if self._indexer is not None:
            cancelled = self._indexer.cancel(window_id)
        if cancelled:
            try:
                import sublime
                if sublime.load_settings("Avalonia.sublime-settings").get("indexing_show_status", True):
                    sublime.status_message("Avalonia: Cancelling workspace indexing…")
            except Exception:
                pass
        return cancelled

    def is_dirty(
        self,
        window,
    ) -> bool:

        """
        Return whether the cached workspace needs rebuilding.
        """

        return (
            window.id()
            in self._dirty
        )

    def clear(
        self,
        window,
    ) -> None:

        """
        Remove all cached state for a window.
        """

        window_id = window.id()

        self._sessions.pop(
            window_id,
            None,
        )

        self._dirty.discard(
            window_id
        )

    def _workspace_persistence_enabled(self) -> bool:
        """Return whether workspace-state persistence is enabled."""
        try:
            import sublime
            return bool(
                sublime.load_settings("Avalonia.sublime-settings").get(
                    "workspace_persistence_enabled",
                    True,
                )
            )
        except Exception:
            return True

    def _cached_project_location(self, window):
        """Return a persisted project location when it still exists."""
        if self._workspace_state_cache is None or not self._workspace_persistence_enabled():
            return None

        folders = window.folders()
        if not folders:
            return None

        for folder in folders:
            root = Path(folder).resolve()
            state = load_workspace_state(
                self._workspace_state_cache,
                root,
            )
            if state is None:
                continue

            solution = state.get("solution")
            project = state.get("projects", [{}])[0].get("project_file") if state.get("projects") else None

            from .domain import ProjectLocation

            if solution and Path(solution).is_file():
                log.info(f"Workspace state restored: {root}")
                return ProjectLocation(
                    root=root,
                    solution=Path(solution).resolve(),
                    project=None,
                )

            if project and Path(project).is_file():
                log.info(f"Workspace state restored: {root}")
                return ProjectLocation(
                    root=root,
                    solution=None,
                    project=Path(project).resolve(),
                )

        return None

    #
    # ------------------------------------------------------------------
    # Static Metadata
    # ------------------------------------------------------------------
    #

    def _get_completion_metadata(
        self,
    ) -> CompletionMetadataIndex:

        """
        Return the cached plugin completion metadata.

        Completion metadata is static and should only be parsed once
        during the lifetime of the plugin process.
        """

        if self._completion_metadata is None:

            metadata_root = (
                Path(__file__).resolve().parent.parent
                / "metadata"
            )

            self._completion_metadata = (
                build_completion_metadata_index(
                    metadata_root
                )
            )

        return self._completion_metadata

    #
    # ------------------------------------------------------------------
    # Resource Cache
    # ------------------------------------------------------------------
    #

    def _build_resources(
        self,
        solution: Solution,
    ) -> ResourceIndex:

        """
        Aggregate the resource indexes already built for each project.

        Project semantic indexing is responsible for parsing AXAML and
        constructing each project's ResourceIndex.

        The session-level resource index is an aggregation of those
        existing semantic indexes.
        """

        indexes = []

        for project in solution.projects:

            resource_index = (
                project.index.resource_index
            )

            if resource_index is None:

                continue

            indexes.append(
                resource_index
            )

        return merge_resource_indexes(
            indexes
        )

    #
    # ------------------------------------------------------------------
    # Convenience Accessors
    # ------------------------------------------------------------------
    #

    def solution(
        self,
        window,
    ) -> Optional[Solution]:

        session = self.ensure_session(
            window
        )

        if session is None:

            return None

        return session.solution

    def startup(
        self,
        window,
    ) -> Optional[Project]:

        solution = self.solution(
            window
        )

        if solution is None:

            return None

        return solution.startup_project

    def project(
        self,
        window,
    ) -> Optional[Project]:

        return self.startup(
            window
        )

    def resources(
        self,
        window,
    ) -> Optional[ResourceIndex]:

        session = self.ensure_session(
            window
        )

        if session is None:

            return None

        return session.resources

    def csharp_index(
        self,
        window,
    ):

        session = self.ensure_session(
            window
        )

        if session is None:

            return None

        project = self.project(
            window
        )

        if project is None:

            return None

        return getattr(
            project.index,
            "csharp_index",
            None,
        )

    def completion_metadata(
        self,
        window=None,
    ) -> Optional[CompletionMetadataIndex]:

        """
        Return the cached static completion metadata.

        Completion metadata belongs to the plugin, not to an individual
        workspace session.  It must therefore remain available even when
        no project has been discovered yet.
        """

        return self._get_completion_metadata()

    def project_for_file(
        self,
        window,
        path: Path,
    ) -> Optional[Project]:

        solution = self.solution(
            window
        )

        if solution is None:

            return None

        target = path.resolve()

        for project in solution.projects:

            try:

                target.relative_to(
                    project.root.resolve()
                )

                return project

            except ValueError:

                continue

        return None

    def update_axaml(
        self,
        window,
        path: Path,
    ) -> bool:
        """
        Incrementally update one AXAML document in the cached workspace.

        The operation parses only the requested AXAML file and preserves
        the existing C# index and unrelated project semantic documents.
        """

        session = self.ensure_session(
            window
        )

        if session is None:

            return False

        target = path.resolve()

        projects = list(
            session.solution.projects
        )

        changed_project = None

        for project in projects:

            try:
                target.relative_to(
                    project.root.resolve()
                )
            except ValueError:
                continue

            changed_project = project
            break

        if changed_project is None:

            return False

        updated_index = update_axaml_document(
            changed_project.index,
            target,
        )

        updated_project = replace(
            changed_project,
            index=updated_index,
        )

        updated_projects = tuple(
            updated_project
            if project is changed_project
            else project
            for project in projects
        )

        startup_project = session.solution.startup_project

        if startup_project is changed_project:
            startup_project = updated_project

        updated_solution = replace(
            session.solution,
            projects=updated_projects,
            startup_project=startup_project,
        )

        resources = self._build_resources(
            updated_solution
        )

        self._sessions[window.id()] = replace(
            session,
            solution=updated_solution,
            resources=resources,
        )

        if self._workspace_state_cache is not None and self._workspace_persistence_enabled():
            try:
                save_workspace_state(
                    self._workspace_state_cache,
                    updated_solution,
                )
            except Exception as exc:
                log.warning(f"Workspace state persistence failed: {exc}")

        log.info(
            f"Incremental AXAML index updated: {target}"
        )

        return True


    def diagnostics(
        self,
        window,
    ) -> Optional[Diagnostics]:

        session = self.ensure_session(
            window
        )

        if session is None:

            return None

        return session.diagnostics

    #
    # ------------------------------------------------------------------
    # Index Access
    # ------------------------------------------------------------------
    #

    def source_file(
        self,
        window,
        path: Path,
    ) -> Optional[SourceFile]:

        project = self.project_for_file(
            window,
            path,
        )

        if project is None:

            return None

        return project.index.by_path.get(
            path.resolve()
        )

    #
    # ------------------------------------------------------------------
    # Resource Access
    # ------------------------------------------------------------------
    #

    def find_resource(
        self,
        window,
        key: str,
    ) -> Optional[ResourceEntry]:

        resources = self.resources(
            window
        )

        if resources is None:

            return None

        entries = resources.by_key.get(
            key
        )

        if not entries:

            return None

        return entries[0]

    #
    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    #

    def find_viewmodel(
        self,
        window,
        path: Path,
    ) -> Optional[Path]:

        project = self.project_for_file(
            window,
            path,
        )

        if project is None:

            return None

        source = project.index.by_path.get(
            path.resolve()
        )

        if source is None:

            return None

        result = navigation.find_viewmodel(
            project.index,
            source,
        )

        if result is None:

            return None

        return result.path

    def find_view(
        self,
        window,
        path: Path,
    ) -> Optional[Path]:

        project = self.project_for_file(
            window,
            path,
        )

        if project is None:

            return None

        source = project.index.by_path.get(
            path.resolve()
        )

        if source is None:

            return None

        result = navigation.find_view(
            project.index,
            source,
        )

        if result is None:

            return None

        return result.path

    def find_code_behind(
        self,
        window,
        path: Path,
    ) -> Optional[Path]:

        project = self.project_for_file(
            window,
            path,
        )

        if project is None:

            return None

        source = project.index.by_path.get(
            path.resolve()
        )

        if source is None:

            return None

        result = navigation.find_code_behind(
            project.index,
            source,
        )

        if result is None:

            return None

        return result.path
