"""
Avalonia Resource Navigation

Provides navigation helpers for Avalonia semantic resources.

This module does not interact with Sublime Text.
It does not parse AXAML.
It does not walk the filesystem.

It operates only on semantic resource indexes.
"""

from __future__ import annotations

from typing import Optional

from .resource import (
    ResourceEntry,
    ResourceIndex,
)


#
# ----------------------------------------------------------------------
# Resource Lookup
# ----------------------------------------------------------------------
#


def find_resource(
    index: ResourceIndex,
    key: str,
) -> Optional[ResourceEntry]:

    """
    Find the semantic resource entry for a keyed Avalonia resource.

    If multiple resources share the same key, the first deterministic
    match from the resource index is returned.

    Resource scope and precedence are intentionally not resolved here.
    """

    resources = index.by_key.get(
        key
    )

    if not resources:
        return None

    return resources[0]
