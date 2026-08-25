"""
Avalonia Background Indexer Service

Runs expensive workspace indexing outside the Sublime UI thread.

Sublime API access is kept on the main thread. The worker thread operates
only on plain Python/domain objects and the completed Solution.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, Optional
from threading import Event

import sublime

from .domain import ProjectLocation, Solution
from .log import log
from .solution import build_solution


@dataclass(frozen=True, slots=True)
class IndexResult:
    """
    Result produced by a background workspace indexing operation.
    """

    window_id: int
    generation: int
    solution: Optional[Solution]
    error: Optional[Exception] = None
    cancelled: bool = False


class IndexerService:
    """
    Runs workspace indexing on a background worker.

    A single worker is intentional. Workspace indexing is a heavyweight
    operation, and allowing multiple complete workspace builds at once
    would waste resources and could cause stale results to overwrite newer
    ones.

    The worker never accesses the Sublime API.

    Completion callbacks are always dispatched back to Sublime's main
    thread using sublime.set_timeout().
    """

    def __init__(self):

        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="AvaloniaIndexer",
        )
        self._generation = 0
        self._futures: Dict[int, object] = {}
        self._cancel_events: Dict[int, Event] = {}


    def submit(
        self,
        window_id: int,
        location: ProjectLocation,
        callback: Callable[[IndexResult], None],
    ) -> int:
        """
        Queue a workspace indexing operation.

        `location` must already have been obtained on the Sublime main
        thread. The worker receives only the plain ProjectLocation object.
        Generation numbers are assigned here so callers cannot accidentally
        submit a stale or mismatched generation.
        """

        self._generation += 1
        generation = self._generation

        cancel_event = Event()
        future = self._executor.submit(
            self._build,
            window_id,
            generation,
            location,
            callback,
            cancel_event,
        )

        self._futures[window_id] = future
        self._cancel_events[window_id] = cancel_event
        return generation


    def cancel(self, window_id: int) -> bool:
        """Cancel queued indexing work for a window when possible."""
        future = self._futures.get(window_id)
        cancel_event = self._cancel_events.get(window_id)
        if future is None or cancel_event is None:
            return False

        cancel_event.set()

        # Do not rely on Future.cancel(): a running worker cannot be
        # forcibly stopped, and a queued future cancelled before it starts
        # would never deliver the normal completion callback. The worker
        # observes the event and delivers a cancelled IndexResult instead.
        return True


    def _build(
        self,
        window_id: int,
        generation: int,
        location: ProjectLocation,
        callback: Callable[[IndexResult], None],
        cancel_event: Event,
    ) -> None:
        """
        Execute the expensive workspace build on the worker thread.
        """

        try:

            log.info(
                "Background indexing started."
            )

            solution = build_solution(
                location,
                cancel_event=cancel_event,
            )

            if cancel_event.is_set():
                raise IndexingCancelled()

            result = IndexResult(
                window_id=window_id,
                generation=generation,
                solution=solution,
            )

            log.info(
                "Background indexing completed."
            )

        except IndexingCancelled:

            log.info("Background indexing cancelled.")

            result = IndexResult(
                window_id=window_id,
                generation=generation,
                solution=None,
                cancelled=True,
            )

        except Exception as exc:

            log.error(
                f"Background indexing failed: {exc}"
            )

            result = IndexResult(
                window_id=window_id,
                generation=generation,
                solution=None,
                error=exc,
            )

        self._futures.pop(window_id, None)
        self._cancel_events.pop(window_id, None)
        self._dispatch_result(
            callback,
            result,
        )


    @staticmethod
    def _dispatch_result(
        callback: Callable[[IndexResult], None],
        result: IndexResult,
    ) -> None:
        """
        Dispatch the completed result back to Sublime's main thread.

        ProjectManager will eventually install the resulting Session, and
        that operation must not occur on the worker thread.
        """

        def deliver():
            try:

                callback(
                    result
                )

            except Exception as exc:

                log.error(
                    f"Background indexing callback failed: {exc}"
                )

        try:

            sublime.set_timeout(
                deliver,
                0,
            )

        except Exception as exc:

            log.error(
                f"Unable to dispatch indexing result: {exc}"
            )


    def shutdown(self) -> None:
        """
        Shut down the background worker.

        Pending work is cancelled where supported. A currently executing
        indexing operation is not forcibly terminated.
        """

        self._executor.shutdown(
            wait=False,
            cancel_futures=True,
        )
