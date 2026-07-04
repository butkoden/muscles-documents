from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DocumentMetadata:
    source: str
    mime: str
    modified_at: str | None = None
    title: str | None = None
    author: str | None = None
    labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedDocument:
    source: str
    reference: str
    text: str
    metadata: DocumentMetadata


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    reference: str
    chunk_index: int
    text: str
    start: int
    end: int
    token_hint: int | None = None


@dataclass(frozen=True)
class DocumentSyncPlan:
    source: str
    operations: list[dict[str, Any]]


@dataclass(frozen=True)
class SourceCursor:
    source: str
    reference: str
    etag: str | None = None
    modified_at: datetime | None = None
