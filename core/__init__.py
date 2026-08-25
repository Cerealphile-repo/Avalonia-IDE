"""
Avalonia Core

Public API for the core package.
"""

from .app import app

from .command import (
    AvaloniaApplicationCommand,
    AvaloniaTextCommand,
    AvaloniaWindowCommand,
)

__all__ = [
    "app",
    "AvaloniaApplicationCommand",
    "AvaloniaTextCommand",
    "AvaloniaWindowCommand",
]
