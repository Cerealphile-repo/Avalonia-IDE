import sublime_plugin

from .core import app
from .core.dotnet import run_dotnet


#
# Build
#

class AvaloniaBuildCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            ["build"]
        )


#
# Run
#

class AvaloniaRunCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            ["run"]
        )


#
# Restore
#

class AvaloniaRestoreCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            ["restore"]
        )


#
# Clean
#

class AvaloniaCleanCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            ["clean"]
        )


#
# Publish
#

class AvaloniaPublishCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            ["publish"]
        )


#
# Test
#

class AvaloniaTestCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            ["test"]
        )


#
# Watch
#

class AvaloniaWatchCommand(sublime_plugin.WindowCommand):

    def run(self):

        run_dotnet(
            self.window,
            [
                "watch",
                "run"
            ]
        )


#
# Stop
#

class AvaloniaStopCommand(sublime_plugin.WindowCommand):

    def run(self):

        app.processes.runner(
            self.window
        ).stop()
