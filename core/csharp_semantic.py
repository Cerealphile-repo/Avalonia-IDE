"""
Lightweight C# semantic index for AXAML tooling.

This is deliberately source-based rather than compiler-based. It extracts
the information AXAML needs most often:

    namespace
    class/interface names
    base types
    public properties and their declared types

It is not a C# parser. Roslyn/LSP remains authoritative for full C#
semantics; this index gives AXAML responsive editor intelligence even
when the C# language server does not understand AXAML.

Parsed C# documents are cached by filesystem modification state so that
workspace rebuilds do not repeatedly parse unchanged C# source files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from threading import Event

from typing import Iterable

from .indexing import IndexingCancelled


@dataclass(frozen=True, slots=True)
class CSharpProperty:
    name: str
    type_name: str
    declaring_type: str


@dataclass(frozen=True, slots=True)
class CSharpType:
    name: str
    full_name: str
    namespace: str
    base_type: str | None
    properties: tuple[CSharpProperty, ...] = ()


@dataclass(frozen=True, slots=True)
class CSharpDocument:
    path: Path
    namespace: str
    types: tuple[CSharpType, ...]


@dataclass(frozen=True, slots=True)
class _CachedDocument:
    """
    Cached parsed C# document.

    The filesystem state is kept alongside the parsed document so an
    unchanged source file can be reused without reading it again.
    """

    mtime_ns: int
    size: int
    document: CSharpDocument


#
# ----------------------------------------------------------------------
# Parsed Document Cache
# ----------------------------------------------------------------------
#

_DOCUMENT_CACHE: dict[
    Path,
    _CachedDocument,
] = {}


def _file_state(
    path: Path,
) -> tuple[int, int] | None:

    """
    Return the filesystem state used to validate a cached document.

    Modification time and file size together provide a lightweight
    invalidation check without reading the file contents.
    """

    try:

        stat = path.stat()

    except OSError:

        return None

    return (
        stat.st_mtime_ns,
        stat.st_size,
    )


def _cached_document(
    path: Path,
) -> CSharpDocument | None:

    """
    Return a cached parsed document when the source file is unchanged.
    """

    resolved = path.resolve()

    state = _file_state(
        resolved
    )

    if state is None:

        _DOCUMENT_CACHE.pop(
            resolved,
            None,
        )

        return None

    cached = _DOCUMENT_CACHE.get(
        resolved
    )

    if cached is None:
        return None

    if (
        cached.mtime_ns != state[0]
        or cached.size != state[1]
    ):
        return None

    return cached.document


def _store_cached_document(
    path: Path,
    document: CSharpDocument,
) -> CSharpDocument:

    """
    Store a successfully parsed document in the source cache.
    """

    resolved = path.resolve()

    state = _file_state(
        resolved
    )

    if state is not None:

        _DOCUMENT_CACHE[
            resolved
        ] = _CachedDocument(
            mtime_ns=state[0],
            size=state[1],
            document=document,
        )

    return document


@dataclass(frozen=True, slots=True)
class CSharpSemanticIndex:
    documents: dict[Path, CSharpDocument]
    types: dict[str, tuple[CSharpType, ...]]

    def find_type(
        self,
        name: str,
        namespace: str | None = None,
    ) -> CSharpType | None:

        if not name:
            return None

        clean = _strip_type_syntax(
            name
        )

        clean = (
            clean.split(".")[-1]
            if ":" not in clean
            else clean
        )

        candidates = list(
            self.types.get(
                clean,
                (),
            )
        )

        if not candidates:

            # Full-name lookup.

            for values in self.types.values():

                for item in values:

                    if (
                        item.full_name
                        == _strip_type_syntax(
                            name
                        )
                    ):
                        return item

        if namespace:

            for item in candidates:

                if item.namespace == namespace:
                    return item

        return (
            candidates[0]
            if candidates
            else None
        )

    def properties_for(
        self,
        type_name: str,
        namespace: str | None = None,
    ) -> tuple[CSharpProperty, ...]:

        root = self.find_type(
            type_name,
            namespace,
        )

        if root is None:
            return ()

        result: list[
            CSharpProperty
        ] = []

        seen: set[str] = set()

        current = root

        visited: set[str] = set()

        while (
            current is not None
            and current.full_name
            not in visited
        ):

            visited.add(
                current.full_name
            )

            for prop in current.properties:

                key = prop.name.casefold()

                if key in seen:
                    continue

                seen.add(key)

                result.append(
                    prop
                )

            if not current.base_type:
                break

            current = self.find_type(
                current.base_type,
                current.namespace,
            )

        return tuple(
            result
        )


_NAMESPACE_RE = re.compile(
    r"\bnamespace\s+([A-Za-z_][\w.]*)"
)

_TYPE_RE = re.compile(
    r"\b(?:public|internal|private|protected|static|abstract|sealed|partial|file|new|\s)*"
    r"\b(class|record|struct|interface)\s+([A-Za-z_]\w*)"
    r"(?:\s*<[^>{}]+>)?"
    r"(?:\s*:\s*([^{]+))?"
    r"\s*\{",
    re.MULTILINE,
)

_PROPERTY_RE = re.compile(
    r"\b(?:public|protected|internal|private)\s+"
    r"(?:static\s+|virtual\s+|override\s+|abstract\s+|new\s+|sealed\s+|partial\s+)*"
    r"(?P<type>[A-Za-z_][\w.<>,?\[\]]*(?:\s*\?)?)\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*\{\s*"
    r"(?:get\b[^{};]*;|init\b[^{};]*;)"
    r"(?:\s*set\b[^{};]*;)?",
    re.MULTILINE,
)


def _strip_type_syntax(
    type_name: str,
) -> str:

    value = re.sub(
        r"\s+",
        "",
        type_name or "",
    )

    value = value.replace(
        "global::",
        "",
    )

    value = re.sub(
        r"<.*>",
        "",
        value,
    )

    value = value.rstrip(
        "?"
    )

    return value


def _namespace_for(
    text: str,
    offset: int,
) -> str:

    match = None

    for item in _NAMESPACE_RE.finditer(
        text,
        0,
        offset,
    ):
        match = item

    return (
        match.group(1)
        if match
        else ""
    )


def _base_name(
    raw: str,
) -> str | None:

    if not raw:
        return None

    first = raw.split(
        ",",
        1,
    )[0].strip()

    # For "IThing, IFoo" or "BaseClass", the first base is what matters.

    return _strip_type_syntax(
        first
    )


def parse_csharp(
    path: Path,
) -> CSharpDocument:

    try:

        text = path.read_text(
            encoding="utf-8"
        )

    except (
        OSError,
        UnicodeError,
    ):

        return CSharpDocument(
            path=path.resolve(),
            namespace="",
            types=(),
        )

    types: list[
        CSharpType
    ] = []

    matches = list(
        _TYPE_RE.finditer(
            text
        )
    )

    for match in matches:

        kind, name, raw_bases = (
            match.groups()
        )

        namespace = _namespace_for(
            text,
            match.start(),
        )

        base_type = _base_name(
            raw_bases
        )

        #
        # Limit property scanning to the type's brace block when possible.
        #

        start = match.end()

        depth = 1
        i = start

        while (
            i < len(text)
            and depth
        ):

            if text[i] == "{":

                depth += 1

            elif text[i] == "}":

                depth -= 1

            i += 1

        body = text[
            start:max(
                start,
                i - 1,
            )
        ]

        properties: list[
            CSharpProperty
        ] = []

        for prop in _PROPERTY_RE.finditer(
            body
        ):

            properties.append(
                CSharpProperty(
                    name=prop.group(
                        "name"
                    ),
                    type_name=_strip_type_syntax(
                        prop.group(
                            "type"
                        )
                    ),
                    declaring_type=name,
                )
            )

        full_name = (
            f"{namespace}.{name}"
            if namespace
            else name
        )

        types.append(
            CSharpType(
                name=name,
                full_name=full_name,
                namespace=namespace,
                base_type=base_type,
                properties=tuple(
                    properties
                ),
            )
        )

    return CSharpDocument(
        path=path.resolve(),
        namespace=_namespace_for(
            text,
            len(text),
        ),
        types=tuple(
            types
        ),
    )


def _parse_or_get_cached(
    path: Path,
) -> CSharpDocument:

    """
    Parse a C# file unless an unchanged parsed document is cached.
    """

    resolved = path.resolve()

    cached = _cached_document(
        resolved
    )

    if cached is not None:
        return cached

    document = parse_csharp(
        resolved
    )

    return _store_cached_document(
        resolved,
        document,
    )


def build_csharp_index(
    paths: Iterable[Path],
    cancel_event: Event | None = None,
) -> CSharpSemanticIndex:

    """
    Build the C# semantic index.

    Individual source documents are reused when their filesystem
    modification state has not changed. The aggregate type index is
    rebuilt so the resulting CSharpSemanticIndex remains deterministic
    and reflects the exact set of paths supplied by the caller.
    """

    documents: dict[
        Path,
        CSharpDocument,
    ] = {}

    types: dict[
        str,
        list[CSharpType],
    ] = {}

    current_paths: set[
        Path
    ] = set()

    for path in sorted(
        paths,
        key=lambda p: str(p).lower(),
    ):

        if cancel_event is not None and cancel_event.is_set():
            raise IndexingCancelled()

        resolved = path.resolve()

        current_paths.add(
            resolved
        )

        document = _parse_or_get_cached(
            resolved
        )

        documents[
            document.path
        ] = document

        for item in document.types:

            types.setdefault(
                item.name,
                [],
            ).append(
                item
            )

    #
    # Remove cached entries for files that no longer belong to the
    # current project index.
    #
    # This prevents the cache from retaining an ever-growing collection
    # when projects are renamed, removed, or switched.
    #

    stale_paths = (
        set(
            _DOCUMENT_CACHE
        )
        - current_paths
    )

    for path in stale_paths:

        _DOCUMENT_CACHE.pop(
            path,
            None,
        )

    return CSharpSemanticIndex(
        documents=documents,
        types={
            key: tuple(value)
            for key, value in types.items()
        },
    )
