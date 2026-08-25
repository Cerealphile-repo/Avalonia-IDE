"""
Simple logger wrapper for Avalonia.
"""

from __future__ import annotations

import sys


class Logger:

    LEVELS = {
        "DEBUG": 10,
        "INFO": 20,
        "WARN": 30,
        "ERROR": 40,
    }

    def __init__(
        self,
        level: str = "INFO",
    ):
        self.level = self.LEVELS.get(
            level.upper(),
            self.LEVELS["INFO"],
        )

    def _log(
        self,
        level: str,
        message: str,
    ):
        if self.LEVELS[level] < self.level:
            return

        print(
            f"[Avalonia][{level}] {message}",
            file=sys.stderr,
        )

    def debug(self, message: str):
        self._log(
            "DEBUG",
            message,
        )

    def info(self, message: str):
        self._log(
            "INFO",
            message,
        )

    def warning(self, message: str):
        self._log(
            "WARN",
            message,
        )

    def error(self, message: str):
        self._log(
            "ERROR",
            message,
        )

    def set_level(
        self,
        level: str,
    ):
        self.level = self.LEVELS.get(
            level.upper(),
            self.LEVELS["INFO"],
        )


# This is what the whole codebase expects.
log = Logger()
