"""Semantic AXAML hover rendering."""
from __future__ import annotations
from .axaml_context import AxamlContext
from .hover_metadata import get_control_info, get_property_info, get_property_values


def get_hover_information(context: AxamlContext, resource=None, csharp_index=None, resource_declaration=None) -> str | None:
    k = context.kind
    if k in {"control", "type"}: return _type_hover(context)
    if k == "property": return _property_hover(context)
    if k == "property_element": return _property_element_hover(context)
    if k == "value": return _value_hover(context)
    if k == "binding": return _binding_hover(context, csharp_index)
    if k == "binding_parameter": return _binding_parameter_hover(context)
    if k in {"markup_extension", "markup_parameter"}: return _markup_hover(context)
    if k == "resource": return _resource_hover(context, resource, resource_declaration)
    if k == "directive": return _directive_hover(context)
    if k == "namespace": return _namespace_hover(context)
    return None


def _type_hover(c):
    if not c.token: return None
    info = get_control_info(c.token) or {}
    lines = [f"# {c.token}", "Avalonia Type"]
    kind = info.get("Kind") or info.get("kind")
    base = info.get("Base") or info.get("base")
    ns = info.get("Namespace") or info.get("namespace")
    if kind: lines.append(f"Kind: {kind}")
    if base: lines.append(f"Base: {base}")
    if ns: lines.append(f"Namespace: {ns}")
    return "\n".join(lines)


def _property_hover(c):
    if not c.control or not c.property: return None
    info = get_property_info(c.control, c.property)
    if not info: return None
    name = info.get("Name") or info.get("name") or c.property
    owner = info.get("Owner") or info.get("owner")
    typ = info.get("Type") or info.get("type")
    inherited = info.get("InheritedFrom") or info.get("inherited_from")
    kind = info.get("Kind") or info.get("kind") or ""
    lines = [f"# {name}", "Avalonia Property"]
    if typ: lines.append(f"Type: {typ}")
    if "." in c.property or str(kind).casefold()=="attached":
        if owner: lines.append(f"Owner: {owner}")
        lines.append("Attached property")
    elif inherited:
        lines.extend([f"Declared on: {inherited}", f"Available on: {c.control}"])
    elif owner: lines.append(f"Owner: {owner}")
    return "\n".join(lines)


def _property_element_hover(c):
    if not c.token: return None
    owner = c.control or c.token.split('.',1)[0]
    prop = c.property or (c.token.split('.',1)[1] if '.' in c.token else c.token)
    return f"# {c.token}\nAXAML Property Element\nOwner: {owner}\nProperty: {prop}"


def _value_hover(c):
    if not c.control or not c.property or not c.token: return None
    values = get_property_values(c.property)
    if not values: return None
    token = c.token.casefold()
    for item in values:
        name = str(item.get("Name") or item.get("name") or "")
        if name.casefold() == token:
            desc = item.get("Description") or item.get("description")
            return "\n".join(x for x in [f"# {name}", f"AXAML Value for {c.property}", desc] if x)
    return None


def _binding_hover(c, index):
    if not c.binding_path: return None
    lines = [f"# {c.token or c.binding_path}", "AXAML Binding", f"Path: {c.binding_path}"]
    if c.markup_extension: lines.append(f"Binding: {c.markup_extension}")
    root = getattr(c, "binding_root_type", None)
    if root: lines.append(f"Source type: {root.split('.')[-1]}")
    if index and root:
        current = root
        parts = c.binding_path.rstrip('.').split('.')
        for part in parts:
            prop = next((p for p in index.properties_for(current) if p.name.casefold()==part.casefold()), None)
            if not prop:
                lines.append(f"Unresolved member: {part}"); break
            lines.append(f"{prop.declaring_type}.{prop.name}: {prop.type_name}")
            target = index.find_type(prop.type_name)
            if target: current = target.full_name
            else: break
    elif not root:
        lines.append("Source type: unavailable")
    return "\n".join(lines)


def _binding_parameter_hover(c):
    descriptions = {
        "path":"The source property path.", "mode":"Controls the binding direction.", "source":"Specifies the binding source object.",
        "elementname":"Uses a named element as the binding source.", "relativesource":"Uses a relative element as the binding source.",
        "stringformat":"Formats the binding result as text.", "converter":"Converts the binding value.", "converterparameter":"Parameter supplied to the converter.",
        "datatype":"Explicit compiled-binding source type.", "fallbackvalue":"Value used when the binding cannot produce a value.", "targetnullvalue":"Value used when the binding result is null.",
        "priority":"Binding priority.", "updatesourcetrigger":"Controls when a source is updated.",
    }
    d = descriptions.get((c.binding_parameter or c.token or '').casefold())
    if not d: return None
    return f"# {c.token}\nAXAML Binding Parameter\n\n{d}"


def _markup_hover(c):
    descriptions = {
        "binding":"Resolves a value from the current DataContext.", "compiledbinding":"A compile-time validated binding.",
        "reflectionbinding":"A reflection-based binding.", "staticresource":"Resolves an existing keyed resource once.",
        "dynamicresource":"Resolves a keyed resource and tracks resource changes.", "templatebinding":"A simplified binding used inside a ControlTemplate.",
        "onplatform":"Selects a value for a target platform.", "onformfactor":"Selects a value for a target form factor.",
    }
    key = (c.markup_extension or c.token or '').casefold()
    d = descriptions.get(key)
    return f"# {c.token}\nAvalonia Markup Extension\n\n{d}" if d else None


def _resource_hover(c, resource=None, declaration=None):
    key = c.token or c.value
    if not key: return None
    lines = [f"# {key}", "Avalonia Resource"]
    if c.resource_kind: lines.append(f"Reference: {c.resource_kind}")
    if declaration:
        typ = declaration.get("type") or declaration.get("kind")
        if typ: lines.append(f"Type: {typ}")
        scope = declaration.get("scope")
        if scope: lines.append(f"Scope: {scope}")
        source = declaration.get("source")
        if source: lines.append(f"Declared in: {source}")
    elif resource is not None:
        typ = getattr(resource, "kind", None)
        if typ: lines.append(f"Type: {typ}")
    return "\n".join(lines)


def _directive_hover(c):
    desc = {
        "x:class":"Identifies the CLR class generated for the AXAML root.", "x:name":"Assigns a name to an object for lookup and references.",
        "x:key":"Defines the key used when an object is stored in a resource dictionary.", "x:datatype":"Specifies the expected data type for bindings in this scope.",
        "x:compilebindings":"Enables or disables compiled bindings for the scope.", "x:type":"Produces a System.Type value for the referenced type.",
    }.get((c.directive or c.token or '').casefold())
    if not desc: return None
    return "\n".join([f"# {c.directive or c.token}", "AXAML Directive", "", desc] + ([f"Value: {c.value}"] if c.value else []))


def _namespace_hover(c):
    if not c.token: return None
    return f"# {c.namespace_prefix or 'default'}\nAXAML Namespace\n\n{c.token}"
