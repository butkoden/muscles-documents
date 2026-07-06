from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


SyncOperationName = Literal[
    "add",
    "update",
    "delete",
    "unchanged",
    "skip",
    "source_not_found",
    "unsupported_source_type",
    "error",
]

SyncStatus = Literal["accepted", "planned", "completed", "partial", "failed", "not_supported"]


@dataclass(frozen=True)
class DocumentError:
    code: str
    message: str
    reference: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentRef:
    source: str
    reference: str
    source_type: str
    mime: str | None = None
    title: str | None = None
    checksum: str | None = None
    modified_at: str | None = None
    size: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentBlob:
    source: str
    reference: str
    mime: str
    text: str
    checksum: str
    source_type: str = "unknown"
    modified_at: str | None = None
    title: str | None = None
    size: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentMetadata:
    source: str
    mime: str
    reference: str | None = None
    source_type: str | None = None
    checksum: str | None = None
    modified_at: str | None = None
    title: str | None = None
    author: str | None = None
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSection:
    section_id: str
    title: str
    section_path: str
    level: int
    start: int
    end: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentBlock:
    block_id: str
    block_type: str
    text: str
    section_id: str | None = None
    section_path: str | None = None
    start: int = 0
    end: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    source: str
    reference: str
    text: str
    metadata: DocumentMetadata
    sections: list[DocumentSection] = field(default_factory=list)
    blocks: list[DocumentBlock] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    reference: str
    chunk_index: int
    text: str
    start: int
    end: int
    chunk_id: str = ""
    token_hint: int | None = None
    section_id: str | None = None
    section_path: str | None = None
    block_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSyncOperation:
    name: SyncOperationName
    reference: str | None = None
    checksum: str | None = None
    previous_checksum: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentSyncPlan:
    source: str
    operations: list[dict[str, Any]]
    errors: list[DocumentError] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentSyncResult:
    source: str
    status: SyncStatus
    operations_total: int
    operations_completed: int
    errors: list[DocumentError] = field(default_factory=list)
    request_id: str | None = None


@dataclass(frozen=True)
class SourceCursor:
    source: str
    reference: str
    etag: str | None = None
    modified_at: datetime | None = None
