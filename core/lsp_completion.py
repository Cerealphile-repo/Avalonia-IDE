"""
Avalonia LSP Completion Provider

Adapter between Sublime LSP and Avalonia completion.

This module does not communicate with the
language server directly.

Sublime LSP owns:
    - server lifecycle
    - JSON-RPC
    - request transport

This adapter only:
    - requests completion
    - converts results
    - normalizes completion items
"""

from __future__ import annotations

from .completion import CompletionItem
from .log import log


class LspCompletionProvider:
    """
    Provides completion through Sublime LSP.
    """

    def __init__(self):

        self._last_items = []


    #
    # Public completion API
    #

    def complete_controls(
        self,
        window,
        prefix="",
    ):

        return self._request(
            window,
            prefix,
            "control",
        )


    def complete_properties(
        self,
        window,
        control,
        prefix="",
    ):

        return self._request(
            window,
            prefix,
            "property",
        )


    def complete_attached_properties(
        self,
        window,
        owner,
        prefix="",
    ):

        return self._request(
            window,
            prefix,
            "attached_property",
        )


    def complete_events(
        self,
        window,
        control,
        prefix="",
    ):

        return self._request(
            window,
            prefix,
            "event",
        )


    #
    # LSP request
    #

    def _request(
        self,
        window,
        prefix,
        kind,
    ) -> list[CompletionItem]:

        view = window.active_view()

        if view is None:
            return []


        log.info(
            f"LSP completion request kind={kind} prefix={prefix}"
        )


        try:

            result = view.run_command(
                "lsp_completion"
            )

        except Exception as ex:

            log.error(
                f"LSP completion error: {ex}"
            )

            return []


        if not result:
            return []


        items = self._convert(
            result,
            kind,
        )

        self._last_items = items

        return items



    #
    # Conversion
    #

    def _convert(
        self,
        items,
        requested_kind,
    ) -> list[CompletionItem]:

        results = []


        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                continue


            label = item.get(
                "label"
            )

            if not label:
                continue


            insert = (
                item.get("insertText")
                or label
            )


            detail = item.get(
                "detail"
            )


            results.append(
                CompletionItem(
                    label=label,
                    insert_text=insert,
                    kind=self._map_kind(
                        item,
                        requested_kind,
                    ),
                    detail=detail,
                )
            )


        return results



    def _map_kind(
        self,
        item,
        requested_kind,
    ) -> str:
        """
        Convert LSP completion kinds into
        Avalonia completion categories.
        """

        kind = item.get(
            "kind"
        )


        mapping = {

            # LSP CompletionItemKind
            7: "property",
            10: "event",
            14: "value",
            21: "control",
        }


        return mapping.get(
            kind,
            requested_kind,
        )
