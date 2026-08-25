"""Shared cancellation primitives for background workspace indexing."""


class IndexingCancelled(Exception):
    """Raised when a background indexing operation is cooperatively cancelled."""
