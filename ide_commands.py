from __future__ import annotations

from pathlib import Path
import re
import subprocess
import threading
import sublime
import sublime_plugin

from .core.app import app
from .core.binding import resolve_data_type, find_viewmodel_type
from .core.ide_features import (
    analyze_bindings, rename_resource_text, related_files, scaffold_view,
    scaffold_viewmodel, resource_scope_candidates, infer_namespace,
)


def _view_text(view):
    return view.substr(sublime.Region(0, view.size()))


def _axaml_view(window):
    view = window.active_view()
    if view and (view.file_name() or '').lower().endswith(('.axaml', '.xaml')):
        return view
    return None


class AvaloniaBindingDiagnosticsCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _axaml_view(self.window)
        if not view or not view.file_name():
            return
        path = Path(view.file_name()).resolve()
        project = app.projects.project_for_file(self.window, path)
        if not project:
            sublime.status_message('Avalonia: Project not found.')
            return
        index = getattr(project.index, 'csharp_index', None)
        if not index:
            sublime.status_message('Avalonia: C# index is not ready; wait for indexing to finish.')
            return
        root = resolve_data_type(_view_text(view), path, csharp_index=index,
                                 viewmodel_fallback=find_viewmodel_type(path, index))
        if not root:
            sublime.status_message('Avalonia: Could not determine the DataContext/ViewModel type.')
            return
        issues = analyze_bindings(_view_text(view), path, root, index)
        if not issues:
            sublime.status_message('Avalonia: No binding errors found.')
            return
        items = [f'{i.line}:{i.column}  {i.message}' for i in issues]
        self.window.show_quick_panel(items, lambda n: self._jump(view, issues[n]) if n >= 0 else None)

    @staticmethod
    def _jump(view, issue):
        point = view.text_point(issue.line - 1, issue.column - 1)
        view.sel().clear(); view.sel().add(sublime.Region(point, point)); view.show(point)


class AvaloniaRenameBindingCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _axaml_view(self.window)
        if not view:
            return
        self.window.show_input_panel('Avalonia binding property name:', '', self._new_name, None, None)
    def _new_name(self, new):
        view = _axaml_view(self.window)
        if not view or not new:
            return
        region = view.sel()[0]
        text = _view_text(view)
        old = view.substr(view.word(region.begin()))
        changed, count = rename_resource_text(text, old, new)
        if count:
            view.run_command('avalonia_replace_text', {'text': changed})
            sublime.status_message(f'Avalonia: renamed {count} resource reference(s).')


class AvaloniaRelatedFilesCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view or not view.file_name(): return
        project = app.projects.project_for_file(self.window, Path(view.file_name()).resolve())
        files = related_files(Path(view.file_name()), project.root if project else None)
        if not files:
            sublime.status_message('Avalonia: No related files found.')
            return
        self.window.show_quick_panel([str(p.name) for p in files], lambda i: self.window.open_file(str(files[i])) if i >= 0 else None)


class AvaloniaCreateViewCommand(sublime_plugin.WindowCommand):
    def run(self): self._prompt('UserControl')
    def _prompt(self, kind):
        self.kind = kind
        self.window.show_input_panel(f'Avalonia {kind} name:', '', self._create, None, None)
    def _create(self, name):
        if not name: return
        project = app.projects.project(self.window)
        if not project: return
        try:
            namespace = infer_namespace(project, Path(project.root) / f'{name}.axaml')
            target_root = Path(project.root)
            if self.kind == 'UserControl' and (Path(project.root) / 'Views').is_dir():
                target_root = Path(project.root) / 'Views'
            elif self.kind == 'Window' and (Path(project.root) / 'Views').is_dir():
                target_root = Path(project.root) / 'Views'
            files = scaffold_view(target_root, name, namespace, self.kind)
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
        except (OSError, ValueError) as exc:
            sublime.error_message(f'Avalonia: Could not create {self.kind}: {exc}')
            return
        self.window.open_file(str(next(iter(files))))


class AvaloniaCreateWindowCommand(AvaloniaCreateViewCommand):
    def run(self): self._prompt('Window')


class AvaloniaCreateResourceDictionaryCommand(AvaloniaCreateViewCommand):
    def run(self): self._prompt('ResourceDictionary')


class AvaloniaCreateViewModelCommand(sublime_plugin.WindowCommand):
    def run(self): self.window.show_input_panel('Avalonia ViewModel name:', '', self._create, None, None)
    def _create(self, name):
        project = app.projects.project(self.window)
        if not project or not name: return
        try:
            namespace = infer_namespace(project)
            target_root = Path(project.root) / 'ViewModels' if (Path(project.root) / 'ViewModels').is_dir() else Path(project.root)
            files = scaffold_viewmodel(target_root, name, namespace)
            for path, content in files.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding='utf-8')
        except (OSError, ValueError) as exc:
            sublime.error_message(f'Avalonia: Could not create ViewModel: {exc}')
            return
        self.window.open_file(str(next(iter(files))))


class AvaloniaPreviewCommand(sublime_plugin.WindowCommand):
    """Restore when necessary, then build the active project and stream the result."""
    def run(self):
        view = _axaml_view(self.window)
        if not view or not view.file_name:
            sublime.status_message('Avalonia: Open an .axaml/.xaml file first.')
            return
        project = app.projects.project_for_file(self.window, Path(view.file_name()).resolve())
        if not project:
            sublime.status_message('Avalonia: Project not found.')
            return

        panel = self.window.create_output_panel('avalonia-build')
        panel.settings().set('word_wrap', False)
        self.window.run_command('show_panel', {'panel': 'output.avalonia-build'})
        panel.run_command('append', {
            'characters': f'Avalonia build: {project.project_file}\n'
        })

        project_file = Path(project.project_file)
        assets_file = project.root / 'obj' / 'project.assets.json'
        restore_needed = not assets_file.is_file()

        commands = []
        if restore_needed:
            commands.append(
                ('restore', ['dotnet', 'restore', str(project_file)])
            )
        commands.append(
            ('build', ['dotnet', 'build', str(project_file), '--no-restore'])
        )

        def run_step(step_index):
            name, command = commands[step_index]
            panel.run_command('append', {
                'characters': f'\nAvalonia: dotnet {name}...\n'
            })
            try:
                process = subprocess.Popen(
                    command,
                    cwd=str(project.root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                )
            except OSError as exc:
                def failed_start():
                    panel.run_command('append', {
                        'characters': f'Failed to start dotnet: {exc}\n'
                    })
                    sublime.error_message(
                        f'Avalonia: Could not start dotnet: {exc}'
                    )
                sublime.set_timeout(failed_start, 0)
                return

            def collect():
                output, _ = process.communicate()

                def finish():
                    panel.run_command('append', {
                        'characters': output or '(no output)\n'
                    })
                    code = process.returncode
                    if code != 0:
                        sublime.error_message(
                            f'Avalonia: {name.capitalize()} failed with '
                            f'exit code {code}. See the Avalonia Build output panel.'
                        )
                        return

                    if step_index + 1 < len(commands):
                        run_step(step_index + 1)
                    else:
                        sublime.status_message('Avalonia: Build succeeded.')

                sublime.set_timeout(finish, 0)

            threading.Thread(target=collect, daemon=True).start()

        if restore_needed:
            panel.run_command('append', {
                'characters': 'Avalonia: project.assets.json is missing; '
                              'running NuGet restore first.\n'
            })
        run_step(0)


class AvaloniaResourceScopeCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _axaml_view(self.window)
        if not view or not view.file_name():
            return

        text = _view_text(view)
        point = view.sel()[0].begin() if view.sel() else 0

        # Resource references are simple enough that this command should not
        # depend exclusively on the general hover-context parser.  In
        # particular, the cursor may be anywhere on the key, braces, or
        # resource markup.  Recognize both StaticResource and DynamicResource
        # directly and use the parsed context only as a fallback.
        match = None
        pattern = re.compile(
            r'''\{\s*(StaticResource|DynamicResource)\s+([^\s}"']+)\s*\}''',
            re.IGNORECASE,
        )
        for candidate in pattern.finditer(text):
            if candidate.start() <= point <= candidate.end():
                match = candidate
                break

        if match:
            token = match.group(2)
            resource_kind = match.group(1)
        else:
            from .core.hover_context import get_hover_context
            ctx = get_hover_context(text, point)
            if ctx.kind != 'resource' or not ctx.token:
                sublime.status_message(
                    'Avalonia: Place the cursor on a StaticResource/DynamicResource key.'
                )
                return
            token = ctx.token
            resource_kind = ctx.resource_kind or 'Resource'

        path = Path(view.file_name()).resolve()
        project = app.projects.project_for_file(self.window, path)
        if not project:
            sublime.status_message('Avalonia: Project not found.')
            return

        resource_index = getattr(project.index, 'resource_index', None)
        result = resource_scope_candidates(
            token,
            path,
            resource_index,
            text,
            point,
        )

        # The active AXAML file is authoritative for a resource declared in
        # its own Resources block.  This fallback also makes the command
        # useful immediately after editing, before the incremental index has
        # caught up.
        if not result.entry:
            local = re.search(
                r'''<[^>]*x:Key\s*=\s*[\"']'''
                + re.escape(token)
                + r'''[\"']''',
                text,
                re.IGNORECASE,
            )
            if local:
                sublime.message_dialog(
                    f'{token}\\nScope: current file\\n'
                    f'Reference: {resource_kind}\\n'
                    f'Declaration: {path}'
                )
                return

        if result.entry:
            sublime.message_dialog(
                f'{result.key}\\n'
                f'Scope: {result.scope}\\n'
                f'Reference: {resource_kind}\\n'
                f'Declaration: {result.entry.path}'
            )
        else:
            sublime.status_message(f'Avalonia: unresolved resource {token}')

def _literal_value_region_at_cursor(view, point):
    """Return the AXAML quoted attribute value containing the cursor."""
    import re
    line = view.line(point)
    line_text = view.substr(line)
    local = point - line.begin()
    pattern = re.compile(r'(?P<attr>[A-Za-z_][\w:.-]*)\s*=\s*(?P<q>["\'])(?P<value>.*?)(?P=q)')
    for match in pattern.finditer(line_text):
        if match.start('value') <= local <= match.end('value'):
            return sublime.Region(
                line.begin() + match.start('value'),
                line.begin() + match.end('value')
            )
    return None


class AvaloniaExtractResourceCommand(sublime_plugin.WindowCommand):
    """Extract the selected literal, asking only for the resource key.

    If nothing is selected, retain a convenient fallback workflow by asking
    for the literal first and then the resource key.  This keeps the command
    usable from the command palette while making the normal editor workflow
    selection-driven.
    """
    def run(self):
        view = _axaml_view(self.window)
        if not view or not view.sel():
            return
        region = view.sel()[0]
        self.view = view

        if region.empty():
            value_region = _literal_value_region_at_cursor(view, region.begin())
            if value_region is not None:
                value = view.substr(value_region)
                if value.strip() and not (value.strip().startswith('{') and value.strip().endswith('}')):
                    self.region = value_region
                    self.value = value
                    self.window.show_input_panel('Resource key:', '', self._create, None, None)
                    return

            self.region = None
            self.value = None
            self.window.show_input_panel(
                'Literal value to extract:', '', self._literal_entered, None, None
            )
            return

        value = view.substr(region)
        if not value.strip():
            sublime.status_message('Avalonia: Select a non-empty literal value to extract.')
            return

        # A selection is the source of truth.  Do not make the user retype it.
        self.region = region
        self.value = value
        self.window.show_input_panel('Resource key:', '', self._create, None, None)

    def _literal_entered(self, value):
        value = value or ''
        if not value.strip():
            return
        self.value = value
        self.region = None
        self.window.show_input_panel('Resource key:', '', self._create, None, None)

    def _create(self, key):
        if not key or not key.strip():
            return
        from .core.ide_features import extract_resource
        source = _view_text(self.view)
        target_offset = self.region.begin() if self.region is not None else None
        updated = extract_resource(source, self.value, key, target_offset=target_offset)
        if updated == source:
            sublime.status_message(
                'Avalonia: Could not extract that value. Select a literal value, not a markup extension.'
            )
            return
        self.view.run_command('avalonia_replace_axaml_text', {'text': updated})


class AvaloniaExtractStyleCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _axaml_view(self.window)
        if not view or not view.sel(): return
        region = view.sel()[0]
        if region.empty():
            sublime.status_message('Avalonia: Select a control element to extract as a style.')
            return
        self.view = view
        # Capture the selection before opening the input panel. Sublime can
        # change the active selection while the panel has focus. Re-reading
        # view.sel() in _create() can therefore return an unrelated range.
        self.selection_region = sublime.Region(region.begin(), region.end())
        self.selection = view.substr(self.selection_region)
        self.window.show_input_panel('Style key:', '', self._create, None, None)
    def _create(self, key):
        import re
        from .core.ide_features import extract_style
        if not key: return
        match = re.search(r'<([A-Za-z_][\w.:-]*)\b([^<>]*?)(?:/?)>', self.selection, re.S)
        if not match: return
        control, attrs = match.group(1), match.group(2)
        props = dict(re.findall(r'([A-Za-z_][\w.]*)\s*=\s*["\']([^"\']*)["\']', attrs))
        props.pop('x:Name', None); props.pop('x:Key', None)
        if not props:
            sublime.status_message('Avalonia: No literal properties found to extract.')
            return
        updated = extract_style(_view_text(self.view), control, key, props)
        # Replace only the selected element's literal properties with a style reference.
        # Build the replacement using the indentation of the original
        # element.  Do not use a hard-coded indentation level: the selected
        # control may be nested several levels deep.
        original_lines = self.selection.splitlines()
        first_line = original_lines[0] if original_lines else self.selection
        leading = re.match(r'[ \t]*', first_line).group(0)
        element = self.selection.strip()
        element = re.sub(r'\s+[A-Za-z_][\w.]*\s*=\s*["\'][^"\']*["\']', '', element)
        element = element.strip()
        style_attr = f'Style="{{StaticResource {key}}}"'
        if element.endswith('/>'):
            if '\n' in element:
                # Preserve the multiline shape and indent the new attribute
                # one level below the element's opening-tag indentation.
                tag = re.match(r'<([A-Za-z_][\w.:-]*)\b', element).group(1)
                replacement = (
                    f'{leading}<{tag}\n'
                    f'{leading}    {style_attr} />'
                )
            else:
                tag = re.match(r'<([A-Za-z_][\w.:-]*)\b', element).group(1)
                replacement = f'{leading}<{tag} {style_attr} />'
        elif element.endswith('>'):
            replacement = element[:-1].rstrip() + f' {style_attr}>'
            replacement = leading + replacement
        else:
            return
        source = _view_text(self.view)
        # extract_style() inserts the new Style resource before the control.
        # Locate the original selected element in that intermediate text so
        # insertion length is handled exactly, even when the Resources block
        # is far from the selection.
        start = updated.find(self.selection, self.selection_region.begin())
        if start < 0:
            sublime.status_message('Avalonia: Could not locate the selected control after extracting the style.')
            return
        end = start + len(self.selection)
        updated = updated[:start] + replacement + updated[end:]
        self.view.run_command('avalonia_replace_axaml_text', {'text': updated})

        # Replacing the entire document as one undoable edit can cause Sublime
        # to leave the inserted/replaced region selected.  That is especially
        # confusing for Extract Style because the selection can appear to
        # extend through the rest of the document.  Collapse the selection to
        # the end of the generated style reference after the replacement.
        cursor = start + len(replacement)
        view = self.view
        sublime.set_timeout(
            lambda: (
                view.sel().clear(),
                view.sel().add(sublime.Region(cursor, cursor)),
                view.show(cursor),
            ),
            0,
        )


class AvaloniaConvertPropertyElementCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = _axaml_view(self.window)
        if not view or not view.sel(): return
        from .core.hover_context import get_hover_context
        from .core.ide_features import convert_attribute_to_property_element
        source = _view_text(view)
        ctx = get_hover_context(source, view.sel()[0].begin())
        if ctx.kind != 'value' or not ctx.control or not ctx.property:
            sublime.status_message('Avalonia: Place the cursor in an attribute value first.')
            return
        updated = convert_attribute_to_property_element(source, ctx.control, ctx.property)
        view.run_command('avalonia_replace_axaml_text', {'text': updated})
