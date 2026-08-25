"""
Avalonia Application

Owns the long-lived services used by the plugin.
"""

from __future__ import annotations

from .indexer_service import IndexerService
from .language_manager import LanguageManager
from .log import Logger
from .lsp_completion import LspCompletionProvider
from .manager import ProjectManager
from .process import ProcessManager
from .process_status import ProcessStatusService


class Application:
    """
    Long-lived Avalonia plugin application.

    The application owns the services that must survive across
    Sublime Text commands and event callbacks.
    """

    def __init__(self):

        self.logger = Logger()

        self.indexer = IndexerService()

        self.projects = ProjectManager(
            self.indexer
        )

        self.processes = ProcessManager(
            self.projects
        )

        self.process_status = ProcessStatusService(
            self.processes
        )

        self.language = LanguageManager()

        provider = LspCompletionProvider()

        self._configure_language(
            provider
        )


    def _configure_language(
        self,
        provider,
    ):
        """
        Configure and initialize the language service.

        Compatibility checks are intentionally kept here so that
        optional LanguageManager capabilities do not prevent the
        rest of the plugin from loading.
        """

        try:

            self.language.set_lsp_completion_provider(
                provider
            )

        except AttributeError:

            self.logger.warning(
                "LanguageManager has no "
                "set_lsp_completion_provider()"
            )


        try:

            self.language.initialize()

        except AttributeError:

            self.logger.warning(
                "LanguageManager has no initialize()"
            )


    def refresh(
        self,
        window,
    ):
        """
        Refresh project and workspace state.
        """

        return self.projects.refresh(
            window
        )


    def shutdown(self):
        """
        Shutdown background services.
        """

        self.indexer.shutdown()



app = Application()
