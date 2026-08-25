"""
Avalonia Hover Listener

Provides IDE-style hover information
for AXAML files.

This module only connects Sublime Text
events to the semantic hover engine.
"""

from __future__ import annotations

from pathlib import Path

import sublime
import sublime_plugin

from .core.app import app

from .core.hover_context import (
    get_hover_context,
)

from .core.hover import (
    get_hover_information,
)

from .core.axaml_context import (
    AxamlContext,
)
from .core.binding import resolve_data_type, find_viewmodel_type


print("[Avalonia] hover_listener loaded")


class AvaloniaHoverListener(
    sublime_plugin.EventListener
):
    """
    Sublime hover bridge.
    """

    def on_hover(
        self,
        view,
        point,
        hover_zone,
    ):
        print(
            "[Avalonia] HOVER EVENT",
            point,
            "zone=",
            hover_zone,
        )

        if hover_zone != sublime.HOVER_TEXT:
            print(
                "[Avalonia] ignored hover zone"
            )
            return

        file_name = view.file_name()

        print(
            "[Avalonia] file:",
            file_name,
        )

        if not file_name:
            return

        if not file_name.lower().endswith(
            (
                ".axaml",
                ".xaml",
            )
        ):
            print(
                "[Avalonia] not AXAML"
            )
            return

        text = view.substr(
            sublime.Region(
                0,
                view.size(),
            )
        )

        context = get_hover_context(
            text,
            point,
        )

        print(
            "[Avalonia] hover context:",
            context,
        )

        if not context.kind:
            print(
                "[Avalonia] no context"
            )
            return

        # --------------------------------------------------
        # RESOURCE LOOKUP
        # --------------------------------------------------

        resource = None
        resource_type = getattr(
            context,
            "resource_type",
            None,
        )

        if context.kind == "resource":

            key = (
                context.token
                or context.value
            )

            if key:

                resource = app.projects.find_resource(
                    view.window(),
                    key,
                )

                print(
                    "[Avalonia] hover resource:",
                    resource,
                )

                if resource is not None:

                    resource_type = getattr(
                        resource,
                        "kind",
                        None,
                    )

                    print(
                        "[Avalonia] resource type:",
                        resource_type,
                    )

        # --------------------------------------------------
        # SEMANTIC CONTEXT
        # --------------------------------------------------

        binding_root_type = None
        csharp_index = None
        if context.kind == "binding":
            try:
                project = app.projects.project_for_file(
                    view.window(),
                    Path(file_name).resolve(),
                )
                csharp_index = getattr(
                    getattr(project, "index", None),
                    "csharp_index",
                    None,
                )
                if csharp_index is not None:
                    binding_root_type = resolve_data_type(
                        text,
                        Path(file_name).resolve(),
                        csharp_index=csharp_index,
                        viewmodel_fallback=find_viewmodel_type(
                            Path(file_name).resolve(),
                            csharp_index,
                        ),
                    )
            except Exception:
                csharp_index = None

        semantic_context = AxamlContext(
            kind=context.kind,
            control=context.control,
            property=context.property,
            value=context.value,
            token=context.token,
            resource_kind=context.resource_kind,
            resource_type=resource_type,
            binding_path=getattr(context, "binding_path", None),
            binding_root_type=binding_root_type,
        )

        print(
            "[Avalonia] semantic context:",
            semantic_context,
        )

        # --------------------------------------------------
        # HOVER INFORMATION
        # --------------------------------------------------

        content = get_hover_information(
            semantic_context,
            resource,
            csharp_index=csharp_index,
        )

        print(
            "[Avalonia] hover information:",
            content,
        )

        if not content:
            print(
                "[Avalonia] empty hover result"
            )
            return

        view.show_popup(
            content,
            flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY,
            location=point,
            max_width=500,
        )
