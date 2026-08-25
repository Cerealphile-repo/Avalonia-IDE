"""
Avalonia process status integration.

Consumes ProcessManager state changes and presents
user-facing process lifecycle information.
"""

from __future__ import annotations

import sublime

from .process import ProcessState, ProcessStatus
from .log import log


class ProcessStatusService:
    """
    Observes process lifecycle events.

    This service does not manage processes.
    It only consumes ProcessManager notifications.
    """

    def __init__(
        self,
        processes,
    ):
        self.processes = processes
        self.last_state = None

        self.processes.add_listener(
            self._process_changed
        )

        log.info(
            "Process status service initialized."
        )

    def _process_changed(
        self,
        window,
        state: ProcessState,
    ):
        self.last_state = state

        log.info(
            "Process state changed: "
            f"{state.status.value}"
        )

        message = self._message(
            state
        )

        if message is None:
            return

        sublime.set_timeout(
            lambda message=message:
                sublime.status_message(
                    message
                ),
            0,
        )

    def _message(
        self,
        state,
    ):
        command = self._command_name(
            state
        )

        if state.status == ProcessStatus.RUNNING:
            return (
                f"Avalonia: {command} running"
            )

        if state.status == ProcessStatus.SUCCEEDED:

            if state.elapsed is not None:
                return (
                    "Avalonia: "
                    f"{command} succeeded "
                    f"({state.elapsed:.2f}s)"
                )

            return (
                f"Avalonia: {command} succeeded"
            )

        if state.status == ProcessStatus.FAILED:
            return (
                f"Avalonia: {command} failed"
            )

        if state.status == ProcessStatus.STOPPED:
            return (
                f"Avalonia: {command} stopped"
            )

        return None

    def _command_name(
        self,
        state,
    ):
        if not state.command:
            return "process"

        known = {
            "build",
            "run",
            "restore",
            "clean",
            "test",
            "publish",
        }

        for part in state.command:
            value = str(
                part
            ).lower()

            if value in known:
                return value

        return "process"
