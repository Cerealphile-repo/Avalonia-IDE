"""
Avalonia for Sublime Text

Package entry point.

Loads the Avalonia command and listener modules located
at the package root.
"""

from __future__ import annotations

import importlib
import pkgutil
import traceback

from .core.log import log

PACKAGE_NAME = "Avalonia"
VERSION = "2.2.15"


def _load_modules():
    """
    Load all top-level Python modules in the Avalonia package.

    Command and listener classes are registered with Sublime
    when their modules are imported.
    """

    package = importlib.import_module(
        __package__
    )

    for _, module_name, is_package in pkgutil.iter_modules(
        package.__path__
    ):

        if is_package:
            continue

        if module_name == "plugin":
            continue

        try:

            importlib.import_module(
                f".{module_name}",
                __package__,
            )

            log.info(
                f"Loaded {PACKAGE_NAME}.{module_name}"
            )

        except Exception:

            log.error(
                f"Failed to load "
                f"{PACKAGE_NAME}.{module_name}"
            )

            traceback.print_exc()


def plugin_loaded():

    log.info(
        f"{PACKAGE_NAME} v{VERSION} loaded."
    )

    _load_modules()


def plugin_unloaded():

    try:
        from .core.app import app
        app.shutdown()
    except Exception as exc:
        log.error(f"Shutdown failed: {exc}")

    log.info(
        "Package unloaded."
    )
