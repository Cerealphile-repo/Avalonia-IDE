# Avalonia for Sublime Text

Avalonia development tooling for Sublime Text 4, with project-aware AXAML
semantics, C# binding intelligence, diagnostics, navigation, resource tooling,
and .NET project integration.

Big shout to https://github.com/SaverinOnRails/ls-for-avalonia for the Avalonia Standalone Language Server.
To enable the language server. GOTO: prefernces:package settings:lsp: server configuration. and add:
{
    "avalonia": {
        "enabled": true,
        "command": [
            "${packages}/Avalonia/language-server/avalonia-ls"
        ],
        "selector": "source.axaml"
    }
}
save it. then ctrl+shift+p enter lsp select troubleshoot server then select Avalonia. there should not be any errors shown in the window.


## Requirements

- Sublime Text 4 (development builds are supported; tested with 4207 Linux x64)
- Python 3.14 runtime supplied by Sublime Text
- .NET 8 or newer
- Avalonia 11 or newer
- LSP and LSP-Roslyn are recommended for authoritative C# language services

## AXAML intelligence

- Avalonia control completion from bundled metadata
- Attached-property completion
- Enum and value completion
- Event metadata completion
- Binding completion from indexed C# source
- Nested binding completion through C# property types
- `x:DataType` resolution through C# namespaces and aliases
- Conservative `ViewNameViewModel` fallback when `x:DataType` is absent
- Binding hover showing resolved property/type information
- Avalonia property hover
- Resource hover and navigation
- `StaticResource` and `DynamicResource` completion and diagnostics
- AXAML-aware diagnostics for unresolved resources and unknown properties
- Go To View
- Go To Code Behind
- Go To ViewModel
- Go To Resource
- Go To Definition
- Find Resource References
- Resource Rename
- AXAML Format Document

## IDE features in 2.2

- Binding typo diagnostics with close-match suggestions
- Scope-aware resource lookup (current-file/workspace approximation)
- Related View / code-behind / ViewModel navigation
- Resource and binding-safe text refactoring helpers
- Extract-resource and extract-style core operations
- Attribute-to-property-element conversion helper
- Create View, Window, ViewModel, and ResourceDictionary scaffolding
- External preview/build command that works with normal Avalonia projects and `dotnet watch`

LSP-Roslyn remains authoritative for C# definitions, references, rename, inheritance,
and compiler diagnostics. The Avalonia package augments it with AXAML-specific semantics.

## Diagnostics

The plugin provides AXAML-aware diagnostics for common semantic problems,
including unresolved resources and binding-property issues. C# diagnostics and
full C# language semantics remain authoritative through LSP/Roslyn.

## Navigation and project tooling

- Solution and project discovery
- Project Explorer
- Symbol/outline support
- View / code-behind / ViewModel navigation
- Resource definitions and references
- Build
- Run
- Restore
- Clean
- Publish
- Test
- Watch
- Stop running process
- Diagnostic navigation and clearing
- Language status
- Output support

### Background indexing

Workspace indexing runs on a background worker so expensive filesystem and
semantic work does not block Sublime's UI thread.

Use **Tools → Avalonia → Reindex Workspace** for an explicit full rebuild.

The plugin reports indexing completion through Sublime's status area when
`indexing_show_status` is enabled.

### Cooperative cancellation

**Tools → Avalonia → Cancel Indexing** requests cancellation of an active
background index. Cancellation is cooperative: a currently executing parse is
allowed to reach a safe cancellation point rather than being forcibly killed.
The indexer checks for cancellation between project/filesystem/semantic units
and never installs a cancelled result as the current workspace session.

Because cancellation is cooperative, a very small project may finish before a
cancel request can take effect.

### Incremental AXAML indexing

Saving an AXAML document updates that document's semantic information without
rebuilding unrelated AXAML documents or the C# index. Resource declarations and
resource references contributed by the changed document are replaced in place.

Full workspace indexing remains available for structural project changes.

### Workspace persistence

Workspace metadata is stored in a versioned JSON cache outside the project
folder. The live Python `Session` is not serialized.

Persisted information includes the workspace root, solution/project paths,
startup project, and file fingerprints. The cache is written atomically and is
used to recover a known project location on a later Sublime session.

Disable it with:

```json
"workspace_persistence_enabled": false
```

### Configuration UI

Use **Tools → Avalonia → Settings** to quickly toggle:

- Show indexing status
- Index workspace on startup
- Enable workspace persistence

The same settings can be edited directly in the user's
`Avalonia.sublime-settings` file.

## Configuration

Default settings include:

```json
{
    "dotnet_path": "dotnet",
    "build_configuration": "Debug",
    "auto_restore": true,
    "hot_reload": false,
    "diagnostics_on_save": false,
    "indexing_show_status": true,
    "indexing_on_startup": true,
    "workspace_persistence_enabled": true,
    "show_output_panel": true,
    "log_level": "INFO"
}
```

## Keyboard shortcuts

No Avalonia-specific keyboard shortcuts are imposed by default. Users who want
keyboard-driven workflows can add their own bindings through Sublime Text's
normal keymap customization without risking conflicts with existing Sublime
Text or third-party package shortcuts.

## Binding intelligence

The AXAML binding engine uses the project's indexed C# source rather than a
hard-coded ViewModel list.

Given:

```xml
<Window
    xmlns:vm="using:MyApp.ViewModels"
    x:DataType="vm:MainWindowViewModel">

    <TextBox Text="{Binding Us}" />
</Window>
```

completion can resolve properties such as:

```text
UserName       string
UserEmail      string
UserAddress    AddressViewModel
```

Nested paths are resolved through the C# property type. For example:

```text
{Binding UserAddress.St
```

can complete members such as:

```text
Street         string
State          string
City           string
ZipCode        string
```

Hover follows the same type chain.

`x:DataType` is preferred. If it is absent, the plugin conservatively falls
back to a conventional `ViewNameViewModel` type when one exists in the current
project.

## Architecture

The package keeps responsibilities separated:

- `index.py` — filesystem discovery and classification
- `semantic_index.py` — AXAML/C# semantic enrichment
- `resource.py` — resource declarations and references
- `csharp_semantic.py` — lightweight source-based C# index
- `solution.py` — solution/project construction
- `indexer_service.py` — background indexing and cooperative cancellation
- `workspace_state.py` — versioned workspace persistence
- `manager.py` — cached runtime sessions and project services

The worker never accesses the Sublime API. Completed indexing results are
returned to the main thread before the live session is replaced.

## Package contents

The package contains:

- Sublime Text plugin source
- AXAML language/syntax support
- Avalonia metadata
- AXAML semantic indexing
- C# source indexing for AXAML intelligence
- embedded language-server components
- solution/project tooling
- workspace persistence
- background indexing

## Version

Plugin version: **2.2.0**
