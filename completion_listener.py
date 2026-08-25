from __future__ import annotations

from pathlib import Path
import sublime
import sublime_plugin

from .core.completion import CompletionEngine
from .core.completion_context import get_completion_context
from .core.binding import get_binding_context, resolve_data_type, find_viewmodel_type, complete_binding
from .core.app import app

_FLAGS = sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS


def _metadata(view):
    try:
        return app.projects.completion_metadata(view.window())
    except Exception as exc:
        print("[Avalonia][Completion] metadata error:", repr(exc))
        return None


def _sublime_item(item, attached_range=None):
    if item.kind == "attached_property" and attached_range:
        start, end = attached_range
        return sublime.CompletionItem.command_completion(
            trigger=f"{item.label}\t{item.detail or 'Avalonia Attached Property'}",
            command="avalonia_insert_completion",
            args={"start": start, "end": end, "text": f'{item.label}=""'},
            annotation="Avalonia Attached Property",
        )

    if item.kind == "control":
        insert = f"{item.label}>\n\t$0\n</{item.label}>"
        fmt = sublime.COMPLETION_FORMAT_SNIPPET
    elif item.kind in {"property", "attached_owner"}:
        insert = f'{item.label}="$1"' if item.kind == "property" else item.label
        fmt = sublime.COMPLETION_FORMAT_SNIPPET
    else:
        insert = item.insert_text
        fmt = sublime.COMPLETION_FORMAT_SNIPPET

    trigger = item.label
    if item.detail:
        trigger = f"{trigger}\t{item.detail}"
    return sublime.CompletionItem(trigger=trigger, completion=insert, completion_format=fmt)


def _binding_completions(view, text, point):
    try:
        path = Path(view.file_name()).resolve()
        project = app.projects.project_for_file(view.window(), path)
        if project is None:
            return None
        index = getattr(project.index, "csharp_index", None)
        if index is None:
            return None
        root = resolve_data_type(
            text, path, csharp_index=index,
            viewmodel_fallback=find_viewmodel_type(path, index),
        )
        context = get_binding_context(text, point, root_type=root, index=index)
        if context is None or not root:
            return None
        return [
            sublime.CompletionItem(
                trigger=f"{p.name}\t{p.type_name} — {p.declaring_type}",
                completion=p.name,
                completion_format=sublime.COMPLETION_FORMAT_SNIPPET,
            )
            for p in complete_binding(context, index)
        ]
    except Exception as exc:
        print("[Avalonia][Binding] completion error:", repr(exc))
        return None


class AvaloniaInsertCompletionCommand(sublime_plugin.TextCommand):
    def run(self, edit, start, end, text):
        start, end = int(start), int(end)
        if start < 0 or end < start or end > self.view.size():
            return
        self.view.replace(edit, sublime.Region(start, end), text)
        caret = start + len(text) - 1 if text.endswith('=""') else start + len(text)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(caret, caret))


class AvaloniaBindingCompletionCommand(sublime_plugin.TextCommand):
    """Explicit, reliable binding-completion probe.

    This command is intentionally separate from Sublime's automatic
    completion trigger.  It lets us verify the semantic binding engine and
    gives users a fallback when another completion provider consumes the
    normal completion event after punctuation such as a trailing dot.
    """

    def run(self, edit):
        view = self.view
        if not (view.file_name() or "").lower().endswith((".axaml", ".xaml")):
            sublime.status_message("Avalonia: binding completion requires an AXAML file.")
            return

        point = view.sel()[0].begin() if view.sel() else view.size()
        text = view.substr(sublime.Region(0, view.size()))
        print("[Avalonia][Binding] explicit completion invoked point=", point)
        items = _binding_completions(view, text, point)
        if not items:
            sublime.status_message("Avalonia: no binding completions at cursor.")
            print("[Avalonia][Binding] explicit completion: no items")
            return

        labels = [item.trigger for item in items]
        print("[Avalonia][Binding] explicit completion items=", len(labels), labels)

        def on_done(index):
            if index < 0:
                return
            name = items[index].completion
            # Replace the current binding segment rather than the whole
            # expression.  For a trailing dot, insert directly at the caret.
            context = get_binding_context(text, point,
                                          root_type=None, index=None)
            if context is not None:
                start, end = context.expression_start, context.expression_end
                # context.expression_start/end describe the path token.
                # With a trailing dot the selected range includes the dot;
                # replacing it would remove the separator, so insert after it.
                if context.path.endswith('.') and context.prefix == '':
                    view.run_command('insert', {'characters': name})
                    return
                view.replace(edit, sublime.Region(start, end), name)
                view.sel().clear()
                view.sel().add(sublime.Region(start + len(name), start + len(name)))

        sublime.set_timeout(
            lambda: view.window().show_quick_panel(
                labels,
                on_done,
                sublime.MONOSPACE_FONT,
                -1,
            ),
            0,
        )


class AvaloniaCompletionListener(sublime_plugin.EventListener):
    def on_query_completions(self, view, prefix, locations):
        if view.settings().get("avalonia_resource_input") or not locations:
            return None
        if not (view.file_name() or "").lower().endswith((".axaml", ".xaml")):
            return None

        point = locations[0]
        full_text = view.substr(sublime.Region(0, view.size()))
        text = view.substr(sublime.Region(0, point))
        context = get_completion_context(text)

        # Binding completion is syntax-specific and project-aware.  Try it
        # before static Avalonia metadata so a metadata hiccup cannot disable
        # C# binding completion.
        binding = _binding_completions(view, full_text, point)
        if binding:
            print("[Avalonia][Binding] completion items=", len(binding), "point=", point)
            return binding, _FLAGS

        metadata = _metadata(view)
        if metadata is None:
            return None

        engine = CompletionEngine(completion_metadata=metadata)
        try:
            engine.update_resources(app.projects.resources(view.window()))
        except Exception:
            pass

        items = []
        if context.kind == "control":
            items = engine.complete_controls(context.prefix)
        elif context.kind == "value":
            items = engine.complete_property_values(
                context.control, context.property, context.prefix
            )
        elif context.kind == "attached_property":
            items = engine.complete_attached_properties(
                context.attached_owner, context.attached_prefix or ""
            )
        elif context.kind == "property":
            normal = engine.complete_properties(
                context.control, context.prefix, context.existing_properties
            )
            owners = engine.complete_attached_owners(context.prefix)
            attached = []
            for owner in owners:
                attached.extend(engine.complete_attached_properties(owner.label, ""))
            items = normal + owners + attached
        elif context.kind == "resource":
            items = engine.complete_resources(context.prefix)

        if not items:
            return None

        attached_range = None
        if (
            context.kind == "attached_property"
            and context.token_start is not None
            and context.token_end is not None
        ):
            attached_range = (context.token_start, context.token_end)

        sublime_items = [_sublime_item(item, attached_range) for item in items]
        print(
            "[Avalonia][Completion]",
            context.kind,
            "control=", repr(context.control),
            "prefix=", repr(context.prefix),
            "items=", len(sublime_items),
        )
        return sublime_items, _FLAGS
