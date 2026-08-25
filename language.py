"""
Language integration layer for Avalonia.
"""

from __future__ import annotations

from typing import Any, List, Optional
from .core.log import log


class LanguageManager:
    def __init__(self):
        self.initialized: bool = False
        self.message: str = ""
        self._completion_provider: Optional[Any] = None

    # ---------------------------------------------------------
    # Provider
    # ---------------------------------------------------------

    def set_lsp_completion_provider(self, provider: Any) -> None:
        self._completion_provider = provider
        log.info("LSP completion provider registered")

    def _provider(self):
        return self._completion_provider

    # ---------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------

    def initialize(self) -> None:
        self.initialized = True
        self.message = "Language manager initialized"

        if self._completion_provider:
            log.info("Completion provider ready")
        else:
            log.info("Running without completion provider")

    # ---------------------------------------------------------
    # Completion API (SAFE FALLBACKS)
    # ---------------------------------------------------------

    def complete_controls(self, *args) -> List[Any]:
        if self._provider():
            return self._provider().complete_controls(*args)
        return []

    def complete_properties(self, *args) -> List[Any]:
        if self._provider():
            return self._provider().complete_properties(*args)
        return []

    def complete_events(self, *args) -> List[Any]:
        if self._provider():
            return self._provider().complete_events(*args)
        return []

    def complete_attached_properties(self, *args) -> List[Any]:
        if self._provider():
            return self._provider().complete_attached_properties(*args)
        return []

    def complete_property_values(self, *args) -> List[Any]:
        if self._provider():
            return self._provider().complete_property_values(*args)
        return []

    def complete_resources(self, *args) -> List[Any]:
        if self._provider():
            return self._provider().complete_resources(*args)
        return []

    # ---------------------------------------------------------
    # Access
    # ---------------------------------------------------------

    @property
    def completion(self) -> Optional[Any]:
        return self._completion_provider
