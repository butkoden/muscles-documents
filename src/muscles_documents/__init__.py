from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DocumentsConfig, SourceConfig
    from .package import DocumentsPackage
    from .runtime import DocumentPipeline, DocumentSource
    from .schemas import DocumentChunk, DocumentMetadata, DocumentSyncPlan, ParsedDocument


__all__ = [
    "DocumentsPackage",
    "DocumentPipeline",
    "DocumentSource",
    "DocumentChunk",
    "DocumentMetadata",
    "DocumentSyncPlan",
    "ParsedDocument",
    "SourceConfig",
    "DocumentsConfig",
    "init_package",
]


def __getattr__(name: str):
    if name == "DocumentsPackage":
        from .package import DocumentsPackage

        return DocumentsPackage
    if name == "DocumentPipeline":
        from .runtime import DocumentPipeline

        return DocumentPipeline
    if name == "DocumentSource":
        from .runtime import DocumentSource

        return DocumentSource
    if name == "DocumentChunk":
        from .schemas import DocumentChunk

        return DocumentChunk
    if name == "DocumentMetadata":
        from .schemas import DocumentMetadata

        return DocumentMetadata
    if name == "DocumentSyncPlan":
        from .schemas import DocumentSyncPlan

        return DocumentSyncPlan
    if name == "ParsedDocument":
        from .schemas import ParsedDocument

        return ParsedDocument
    if name == "SourceConfig":
        from .config import SourceConfig

        return SourceConfig
    if name == "DocumentsConfig":
        from .config import DocumentsConfig

        return DocumentsConfig
    if name == "init_package":
        from .package import init_package

        return init_package
    raise AttributeError(name)


def __dir__():
    return sorted(__all__)
