Avalonia IDE for Sublime Text
A complete Avalonia development environment for Sublime Text 4

Avalonia IDE 2.2.14 brings a full, project-aware Avalonia development workflow to Sublime Text 4.

This is more than AXAML syntax highlighting. Avalonia IDE understands the relationship between your AXAML, C# code, ViewModels, resources, projects, and solution structure, while integrating with Roslyn/LSP for C# language services.

This LSP-Roslyn will work the best with this https://github.com/Cerealphile-repo/LSP-Roslyn.

Documentation for the menu is here https://github.com/Cerealphile-repo/Avalonia-IDE/blob/main/docs/Avalonia_IDE_Menu_Guide.pdf

The result is a fast, lightweight, code-first Avalonia IDE that lets you build applications without leaving Sublime Text.

Why Avalonia IDE?

Avalonia is a powerful cross-platform UI framework for .NET, but developers who prefer Sublime Text have traditionally had to assemble their own collection of packages and tools.

Avalonia IDE brings those pieces together into one integrated development environment.

You get:

Avalonia and AXAML intelligence
C# language services through Roslyn/LSP
Project and solution awareness
C#-backed AXAML binding completion
Diagnostics
Code navigation
Refactoring and code actions
Resource and style tooling
Project Explorer
.NET build and development commands
Workspace indexing
Workspace persistence
Avalonia project scaffolding
Integrated split terminal

All while keeping the speed and responsiveness of Sublime Text.

Features
🧩 Avalonia / AXAML Intelligence

Avalonia IDE understands AXAML as an Avalonia UI language rather than treating it as ordinary XML.

Completion

Context-aware completion is available for:

Avalonia controls
Properties
Attached properties
Events
Enums
Property values
Binding expressions
Resources
Styles

The completion engine understands the Avalonia property system and the context in which a property is being used.

🔗 C#-Backed Binding Completion

One of the most important features is the connection between AXAML and C#.

When an AXAML view declares:

x:DataType="vm:MainWindowViewModel"

Avalonia IDE can resolve that C# type and use its members when providing binding completion.

For example:

<TextBox Text="{Binding Us}" />

can provide completions based on the actual ViewModel:

UserName
UserEmail
UserAddress

Nested properties are supported as well:

{Binding UserAddress.Street}

The goal is to make AXAML bindings feel much closer to writing strongly understood C# code.

🔎 Navigation

Avalonia IDE provides navigation between the different parts of an Avalonia application.

Available navigation includes:

Go To Definition
Peek Definition
Go To View
Go To Code Behind
Go To ViewModel
Go To Binding
Go To Resource
Find References
Find Resource References
Outline
Related Files

This makes it easy to move through an application without manually searching the project.

🎨 Resources and Styles

Avalonia resources receive dedicated semantic support.

The IDE can:

Find resource definitions
Find resource references
Navigate to resources
Diagnose unresolved resources
Complete StaticResource
Complete DynamicResource
Rename resources
Extract resources
Extract styles

Resource references are understood in the context of the project rather than treated as arbitrary markup.

✨ AXAML Refactoring and Code Actions

Avalonia IDE includes editing operations specifically designed for AXAML.

These include:

AXAML rename
Rename resources
Rename bindings
Extract resource
Extract style
Convert attribute to property element
AXAML code actions
AXAML formatting

For example, an AXAML attribute can be converted into a property element without manually rewriting the markup.

🚨 Diagnostics

Avalonia IDE provides diagnostics for both C# and AXAML.

AXAML diagnostics include:
Invalid bindings
Unknown properties
Unresolved resources
Binding problems
Semantic AXAML errors
C# diagnostics

C# diagnostics are provided through Roslyn/LSP.

Diagnostic commands include:

Show Diagnostics
Next Error
Previous Error
Clear Diagnostics

The goal is to surface problems directly in the editor instead of requiring a separate IDE window.

🧠 Roslyn / LSP Integration

Avalonia IDE works alongside the existing C# language-service ecosystem.

Roslyn/LSP remains responsible for C# language intelligence, while Avalonia IDE adds the Avalonia-specific semantic layer.

This provides:

C# completion
C# diagnostics
C# definitions
References
Rename
Inheritance information
C# language semantics

while Avalonia IDE handles:

AXAML semantics
Avalonia properties
Bindings
Resources
AXAML navigation
Avalonia-specific diagnostics

This separation allows each system to concentrate on what it does best.

📁 Project Explorer

Avalonia IDE includes a project-aware Explorer for navigating Avalonia solutions.

It understands:

Solutions
Projects
Project relationships
Source files
AXAML files
Code-behind files
Resources

The IDE can discover projects and solutions and use that information throughout its semantic tooling.

⚙️ .NET Integration

Common .NET development operations are available directly from Sublime Text.

Supported operations include:

Build
Run
Restore
Clean
Publish
Test
Watch
Stop

This means you can stay inside Sublime Text for the normal edit → build → run → diagnose development cycle.

🏗 Avalonia Scaffolding

Common Avalonia application components can be created directly from Sublime Text.

Scaffolding support includes:

Views
Windows
ViewModels
Resource dictionaries

This makes creating new application components much faster while maintaining the expected Avalonia project structure.

⚡ Workspace Indexing

Avalonia IDE maintains a semantic index of the workspace.

The index supports:

AXAML completion
C# binding resolution
Resource lookup
Navigation
Project relationships
Semantic operations

Indexing runs in the background so that larger projects can be processed without unnecessarily blocking the editor.

You can manually rebuild the workspace index when necessary.

🔄 Incremental Indexing

Changing one AXAML file doesn't require rebuilding the entire project.

Avalonia IDE updates the information associated with the changed document and preserves unrelated workspace information.

This makes normal editing significantly faster than repeatedly rebuilding a complete project index.

💾 Workspace Persistence

Workspace information can be persisted between Sublime Text sessions.

The workspace system can remember information such as:

Workspace root
Solution
Projects
Startup project
File information

This allows Avalonia IDE to restore project context when you return to a project.

Workspace persistence can also be disabled through the package settings.

🖥 Integrated Terminal

Avalonia IDE includes an integrated Terminus-based terminal workflow.

The terminal can be opened beside the editor:

┌───────────────────────────────┬──────────────────┐
│                               │                  │
│       Avalonia Editor         │     Terminal     │
│                               │                  │
│       C# / AXAML              │   dotnet ...     │
│                               │                  │
└───────────────────────────────┴──────────────────┘

Press:

Ctrl+Alt+T

to toggle the terminal.

This gives Sublime Text an IDE-style editor/terminal layout without requiring Origami or another layout package.

⌨️ Avalonia Commands

Avalonia IDE adds a collection of commands to Sublime Text's Command Palette.

These include project, indexing, navigation, diagnostics, resource, refactoring, scaffolding, and .NET development commands.

The package also provides its own keyboard bindings where appropriate.

🧩 Project-Aware Development

Avalonia IDE is designed around the idea that an Avalonia application is more than a collection of files.

It maintains awareness of:

Solution
   │
   ├── Project
   │    ├── C#
   │    ├── AXAML
   │    ├── Resources
   │    └── ViewModels
   │
   └── Project

That project awareness is what allows features such as C#-backed binding completion, resource navigation, View/ViewModel navigation, and semantic diagnostics to work together.

🚀 Installation
Package Control

Once Avalonia IDE is available in the Package Control default channel:

Open the Command Palette.
Select Package Control: Install Package.
Search for Avalonia.
Select Avalonia.

Package Control handles installation and future updates.


Requirements
Required
Sublime Text 4
.NET 8 or newer
Avalonia 11 or newer
Recommended
LSP
LSP-Roslyn

Development and testing for version 2.2.14 has been performed with Sublime Text 4207 on Linux x64.

What Avalonia IDE Is Not

Avalonia IDE is a code-first development environment.

It does not attempt to reproduce every feature of Visual Studio or JetBrains Rider.

No visual XAML designer

Avalonia IDE does not currently provide a live visual AXAML designer/preview surface.

Instead, it concentrates on the development features that can be integrated naturally into Sublime Text:

editing + semantic understanding + navigation + diagnostics + refactoring + project tooling + .NET tooling

The result is a lightweight alternative for developers who prefer working in Sublime Text.

Why Sublime Text?

Visual Studio, Rider, and VS Code are excellent development environments.

Avalonia IDE exists for developers who prefer Sublime Text.

If you want:

a fast editor
a minimal interface
instant startup
powerful keyboard-driven navigation
C# intelligence
Avalonia intelligence
project awareness
integrated .NET tooling

without moving to a larger IDE, Avalonia IDE is designed for that workflow.

To use the builtin Avalonia Language Server go to preferense - Package Settings - LSP - server configurations and insert

{
    "avalonia": {
        "enabled": true,
        "command": [
            "${packages}/Avalonia/language-server/avalonia-ls"
        ],
        "selector": "source.axaml"
    }
}

and save. then ctrl+shift+p type LSP and choose troubleshoot server and select avalonia to check for any errors.

A thank you to https://github.com/SaverinOnRails/ls-for-avalonia for the standalone avalonia language server.

Version

Avalonia IDE 2.2.14
