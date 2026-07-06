from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import DocumentsConfig, SourceConfig
    from .package import DocumentsPackage
    from .runtime import DocumentPipeline, DocumentSource
    from .schemas import (
        DocumentBlob,
        DocumentBlock,
        DocumentChunk,
        DocumentError,
        DocumentMetadata,
        DocumentRef,
        DocumentSection,
        DocumentSyncOperation,
        DocumentSyncPlan,
        DocumentSyncResult,
        ParsedDocument,
    )


__all__ = [
    "DocumentsPackage",
    "DocumentPipeline",
    "DocumentSource",
    "DocumentBlob",
    "DocumentBlock",
    "DocumentChunk",
    "DocumentError",
    "DocumentMetadata",
    "DocumentRef",
    "DocumentSection",
    "DocumentSyncOperation",
    "DocumentSyncPlan",
    "DocumentSyncResult",
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
    if name == "DocumentBlob":
        from .schemas import DocumentBlob

        return DocumentBlob
    if name == "DocumentBlock":
        from .schemas import DocumentBlock

        return DocumentBlock
    if name == "DocumentChunk":
        from .schemas import DocumentChunk

        return DocumentChunk
    if name == "DocumentError":
        from .schemas import DocumentError

        return DocumentError
    if name == "DocumentMetadata":
        from .schemas import DocumentMetadata

        return DocumentMetadata
    if name == "DocumentRef":
        from .schemas import DocumentRef

        return DocumentRef
    if name == "DocumentSection":
        from .schemas import DocumentSection

        return DocumentSection
    if name == "DocumentSyncOperation":
        from .schemas import DocumentSyncOperation

        return DocumentSyncOperation
    if name == "DocumentSyncPlan":
        from .schemas import DocumentSyncPlan

        return DocumentSyncPlan
    if name == "DocumentSyncResult":
        from .schemas import DocumentSyncResult

        return DocumentSyncResult
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
