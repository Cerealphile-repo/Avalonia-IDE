"""
Avalonia process management.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import subprocess
import threading
import time
from typing import Callable

import sublime

from . import output


class ProcessStatus(Enum):

    IDLE = "idle"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(slots=True)
class ProcessState:

    status: ProcessStatus = ProcessStatus.IDLE
    command: tuple[str, ...] = ()
    started_at: float | None = None
    finished_at: float | None = None
    elapsed: float | None = None
    exit_code: int | None = None

    @property
    def is_running(self):
        return self.status == ProcessStatus.RUNNING

    @property
    def succeeded(self):
        return self.status == ProcessStatus.SUCCEEDED

    @property
    def failed(self):
        return self.status == ProcessStatus.FAILED

    @property
    def stopped(self):
        return self.status == ProcessStatus.STOPPED


class ProcessRunner:

    def __init__(
        self,
        window,
        projects,
        on_state_changed: Callable[[ProcessState], None] | None = None,
    ):
        self.window = window
        self.projects = projects

        self.process = None
        self.state = ProcessState()
        self.on_state_changed = on_state_changed

        self._lock = threading.RLock()
        self._stop_requested = False

    def _notify_state_changed(
        self,
        state,
    ):
        callback = self.on_state_changed

        if callback is None:
            return

        def notify():
            try:
                callback(state)
            except Exception:
                pass

        sublime.set_timeout(
            notify,
            0,
        )

    def _set_state(
        self,
        state,
    ):
        with self._lock:
            self.state = state

        self._notify_state_changed(
            state
        )

    def _current_state(self):
        with self._lock:
            return self.state

    def run(
        self,
        command,
        cwd=None,
    ):
        command = tuple(
            str(part)
            for part in command
        )

        with self._lock:
            if (
                self.process is not None
                and self.process.poll() is None
            ):
                already_running = True
            else:
                already_running = False

        if already_running:
            sublime.status_message(
                "Avalonia: Process already running."
            )
            return

        output.clear(
            self.window
        )

        diagnostics = self.projects.diagnostics(
            self.window
        )

        if diagnostics is not None:
            try:
                diagnostics.clear()
            except Exception:
                pass

        start = time.perf_counter()

        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

        except Exception as error:
            finished = time.perf_counter()

            self._set_state(
                ProcessState(
                    status=ProcessStatus.FAILED,
                    command=command,
                    started_at=start,
                    finished_at=finished,
                    elapsed=finished - start,
                    exit_code=None,
                )
            )

            sublime.error_message(
                "Avalonia: Failed to start process.\n\n"
                f"{error}"
            )

            return

        with self._lock:
            self.process = process
            self._stop_requested = False

        self._set_state(
            ProcessState(
                status=ProcessStatus.RUNNING,
                command=command,
                started_at=start,
            )
        )

        threading.Thread(
            target=self._reader,
            args=(process, start, command),
            daemon=True,
            name="AvaloniaProcessReader",
        ).start()

    def _handle_output(
        self,
        text,
    ):
        def update():
            diagnostics = self.projects.diagnostics(
                self.window
            )

            if diagnostics is not None:
                try:
                    diagnostics.parse(
                        text
                    )
                except Exception as error:
                    sublime.status_message(
                        "Avalonia: Diagnostic parser failed."
                    )

            try:
                output.append(
                    self.window,
                    text + "\n",
                )
            except Exception:
                pass

        sublime.set_timeout(
            update,
            0,
        )

    def _reader(
        self,
        process,
        start,
        command,
    ):
        stdout = process.stdout

        try:
            if stdout is not None:
                for line in stdout:
                    text = line.rstrip(
                        "\r\n"
                    )

                    self._handle_output(
                        text
                    )

        except Exception as error:
            sublime.set_timeout(
                lambda error=error:
                    sublime.error_message(
                        "Avalonia: Process reader failed.\n\n"
                        f"{error}"
                    ),
                0,
            )

        finally:
            try:
                process.wait()
            except Exception:
                pass

            finished = time.perf_counter()
            elapsed = finished - start
            exit_code = process.returncode

            with self._lock:
                stop_requested = self._stop_requested

                if self.process is process:
                    self.process = None

            current_state = self._current_state()

            if (
                current_state.status
                == ProcessStatus.RUNNING
            ):
                if stop_requested:
                    status = ProcessStatus.STOPPED
                    final_exit_code = exit_code
                elif exit_code == 0:
                    status = ProcessStatus.SUCCEEDED
                    final_exit_code = exit_code
                else:
                    status = ProcessStatus.FAILED
                    final_exit_code = exit_code

                self._set_state(
                    ProcessState(
                        status=status,
                        command=command,
                        started_at=start,
                        finished_at=finished,
                        elapsed=elapsed,
                        exit_code=final_exit_code,
                    )
                )

            elif current_state.status == ProcessStatus.STOPPED:
                self._set_state(
                    ProcessState(
                        status=ProcessStatus.STOPPED,
                        command=command,
                        started_at=start,
                        finished_at=finished,
                        elapsed=elapsed,
                        exit_code=exit_code,
                    )
                )

            if stop_requested:
                message = (
                    "Avalonia stopped "
                    f"({elapsed:.2f}s, exit {exit_code})"
                )
            elif exit_code == 0:
                message = (
                    "Avalonia finished "
                    f"({elapsed:.2f}s, exit {exit_code})"
                )
            else:
                message = (
                    "Avalonia failed "
                    f"({elapsed:.2f}s, exit {exit_code})"
                )

            sublime.set_timeout(
                lambda message=message:
                    sublime.status_message(
                        message
                    ),
                0,
            )

    def stop(self):

        with self._lock:
            process = self.process

            if process is None:
                return

            if process.poll() is not None:
                return

            self._stop_requested = True
            state = self.state

        try:
            process.terminate()

        except Exception as error:
            with self._lock:
                self._stop_requested = False

            sublime.error_message(
                "Avalonia: Failed to stop process.\n\n"
                f"{error}"
            )

            return

        finished = time.perf_counter()

        elapsed = None

        if state.started_at is not None:
            elapsed = (
                finished
                - state.started_at
            )

        self._set_state(
            ProcessState(
                status=ProcessStatus.STOPPED,
                command=state.command,
                started_at=state.started_at,
                finished_at=finished,
                elapsed=elapsed,
                exit_code=None,
            )
        )

    def is_running(self):

        with self._lock:
            process = self.process

            if process is None:
                return False

            return process.poll() is None


class ProcessManager:

    def __init__(
        self,
        projects,
    ):
        self.projects = projects
        self._processes = {}
        self._listeners = []

        self._lock = threading.RLock()

    def add_listener(
        self,
        callback,
    ):
        if callback is None:
            return

        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(
                    callback
                )

    def remove_listener(
        self,
        callback,
    ):
        with self._lock:
            try:
                self._listeners.remove(
                    callback
                )
            except ValueError:
                pass

    def _state_changed(
        self,
        window,
        state,
    ):
        with self._lock:
            listeners = tuple(
                self._listeners
            )

        for callback in listeners:
            try:
                callback(
                    window,
                    state,
                )
            except Exception:
                pass

    def runner(
        self,
        window,
    ):
        wid = window.id()

        with self._lock:
            runner = self._processes.get(
                wid
            )

            if runner is not None:
                return runner

            runner = ProcessRunner(
                window,
                self.projects,
                on_state_changed=lambda state,
                    window=window:
                    self._state_changed(
                        window,
                        state,
                    ),
            )

            self._processes[wid] = runner

            return runner

    def state(
        self,
        window,
    ):
        return self.runner(
            window
        ).state

    def stop(
        self,
        window,
    ):
        with self._lock:
            runner = self._processes.get(
                window.id()
            )

        if runner is not None:
            runner.stop()

    def clear(
        self,
        window,
    ):
        with self._lock:
            self._processes.pop(
                window.id(),
                None,
            )
