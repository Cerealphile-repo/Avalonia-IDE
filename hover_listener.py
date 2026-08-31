from __future__ import annotations
from pathlib import Path
import re
import sublime
import sublime_plugin
from .core.app import app
from .core.hover_context import get_hover_context
from .core.hover import get_hover_information
from .core.axaml_context import AxamlContext
from .core.binding import resolve_data_type, find_viewmodel_type
from .core.csharp_semantic import CSharpSemanticIndex, build_csharp_index

print("[Avalonia] hover_listener loaded")

def _aggregate_csharp_index(solution):
    documents, types = {}, {}
    if not solution: return None
    for project in solution.projects:
        idx = getattr(project.index, "csharp_index", None)
        if not idx: continue
        documents.update(idx.documents)
        for name, records in idx.types.items():
            types.setdefault(name, [])
            for record in records:
                if record not in types[name]: types[name].append(record)
    if not documents and not types: return None
    return CSharpSemanticIndex(documents=documents, types={k: tuple(v) for k,v in types.items()})

def _local_resource(text, key):
    if not key: return None
    pat = re.compile(r'<(?P<type>[A-Za-z_][\w.:-]*)(?P<attrs>[^>]*?\bx:Key\s*=\s*["\'](?P<key>[^"\']+)["\'][^>]*)/?>', re.S)
    for m in pat.finditer(text):
        if m.group('key') == key:
            return {'type': m.group('type'), 'scope': 'current AXAML resource dictionary'}
    return None

def _resolve_index(window, path):
    try:
        project = app.projects.project_for_file(window, path)
        if project is not None and getattr(project.index, 'csharp_index', None):
            return project.index.csharp_index
        return _aggregate_csharp_index(app.projects.solution(window))
    except Exception as exc:
        print('[Avalonia][Hover] C# index lookup failed:', exc)
        return None

def _binding_root(text, path, point, index):
    if index is None: return None
    try:
        return resolve_data_type(text, path, csharp_index=index, viewmodel_fallback=find_viewmodel_type(path,index), point=point)
    except Exception as exc:
        print('[Avalonia][Hover] DataType resolution failed:', exc)
        return None

def _lsp_csharp_view(window):
    try:
        from LSP.plugin.core.registry import windows
    except ImportError:
        return None, None
    for candidate in window.views():
        name = candidate.file_name()
        if not name or not name.lower().endswith('.cs'): continue
        listener = windows.listener_for_view(candidate)
        if not listener: continue
        session = listener.session_async('workspaceSymbolProvider')
        if session: return candidate, session
    return None, None

def _lsp_resolve_binding(view, point, context, text):
    m = re.search(r'\bx:DataType\s*=\s*["\']([^"\']+)["\']', text)
    if not m: return False
    value = m.group(1)
    aliases = dict(re.findall(r'\bxmlns:([A-Za-z_]\w*)\s*=\s*["\']using:([^"\']+)["\']', text))
    if ':' in value:
        prefix, name = value.split(':',1)
        query = name
    else:
        query = value.split('.')[-1]
    lsp_view, session = _lsp_csharp_view(view.window())
    if not session: return False
    try:
        from LSP.plugin.core.protocol import Request
        session.send_request(Request('workspace/symbol', {'query': query}, lsp_view),
            lambda response: _on_lsp_symbols(response, view, context, text, point, query))
        return True
    except Exception as exc:
        print('[Avalonia][Hover] workspace/symbol failed:', exc)
        return False

def _on_lsp_symbols(response, view, context, text, point, query):
    if not isinstance(response, list): return
    matches = [x for x in response if isinstance(x,dict) and x.get('name','').casefold()==query.casefold() and (x.get('location') or x.get('targetLocation'))]
    if not matches: return
    try:
        from LSP.plugin.core.url import parse_uri
        loc = matches[0].get('location') or matches[0].get('targetLocation')
        uri = loc.get('uri') or loc.get('targetUri')
        scheme, source = parse_uri(uri)
        if scheme != 'file': return
        source = Path(source).resolve()
        root = source.parent
        for _ in range(8):
            if list(root.glob('*.csproj')) or list(root.glob('*.sln')): break
            if root.parent == root: break
            root = root.parent
        files = [p for p in root.rglob('*.cs') if '.git' not in p.parts and not p.name.endswith('.g.cs')]
        idx = build_csharp_index(files)
        typ = next((t for records in idx.types.values() for t in records if t.name.casefold()==query.casefold()), None)
        if not typ: return
        semantic = AxamlContext(kind=context.kind, control=context.control, property=context.property, value=context.value,
            token=context.token, resource_kind=context.resource_kind, binding_path=context.binding_path,
            binding_root_type=typ.full_name, markup_extension=context.markup_extension,
            binding_parameter=context.binding_parameter, directive=context.directive, namespace_prefix=context.namespace_prefix)
        content = get_hover_information(semantic, csharp_index=idx)
        if content:
            sublime.set_timeout(lambda: view.show_popup(content, flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=point, max_width=600), 0)
    except Exception as exc:
        print('[Avalonia][Hover] Roslyn fallback failed:', exc)

class AvaloniaHoverListener(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        if hover_zone != sublime.HOVER_TEXT: return
        filename = view.file_name()
        if not filename or not filename.lower().endswith(('.axaml','.xaml')): return
        text = view.substr(sublime.Region(0, view.size()))
        context = get_hover_context(text, point)
        print('[Avalonia] HOVER EVENT', point, 'zone=', hover_zone)
        print('[Avalonia] hover context:', context)
        if not context.kind: return
        path = Path(filename).resolve()
        resource = None; declaration = None
        if context.kind == 'resource':
            key = context.token or context.value
            declaration = _local_resource(text,key)
            if key:
                try: resource = app.projects.find_resource(view.window(), key)
                except Exception: resource = None
        idx = _resolve_index(view.window(),path) if context.kind == 'binding' else None
        root = _binding_root(text,path,point,idx) if context.kind == 'binding' else None
        semantic = AxamlContext(kind=context.kind, control=context.control, property=context.property, value=context.value,
            token=context.token, resource_kind=context.resource_kind, resource_type=getattr(resource,'kind',None) if resource else None,
            binding_path=context.binding_path, binding_root_type=root, markup_extension=context.markup_extension,
            binding_parameter=context.binding_parameter, directive=context.directive, namespace_prefix=context.namespace_prefix)
        print('[Avalonia] semantic context:', semantic)
        # Binding resolution gets one final chance through Roslyn before we
        # display the intentionally minimal 'source unavailable' fallback.
        if context.kind == 'binding' and (idx is None or root is None):
            if _lsp_resolve_binding(view, point, context, text):
                return

        content = get_hover_information(semantic, resource, csharp_index=idx, resource_declaration=declaration)
        print('[Avalonia] hover information:', content)
        if content:
            view.show_popup(content, flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, location=point, max_width=600)
