from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .schemas import DocumentChunk, DocumentMetadata, DocumentSyncPlan, ParsedDocument, SourceCursor
from .config import SourceConfig


@dataclass(frozen=True)
class DocumentSource:
    name: str
    type: str
    path: Path | None = None
    options: dict[str, Any] = field(default_factory=dict)


def _normalize_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(os.fspath(value)).resolve()


class DocumentPipeline:
    def __init__(
        self,
        *,
        key: str,
        sources: dict[str, SourceConfig],
        chunk_size: int = 1000,
        chunk_overlap: int = 80,
        include_hidden: bool = False,
    ) -> None:
        self.key = key
        self.sources = {
            name: DocumentSource(name=name, type=source.type, path=_normalize_path(source.path), options=source.options)
            for name, source in sources.items()
        }
        self.chunk_size = max(1, chunk_size)
        self.chunk_overlap = max(0, min(chunk_overlap, self.chunk_size - 1))
        self.include_hidden = include_hidden

    def list_sources(self) -> list[str]:
        return list(self.sources.keys())

    def inspect_source(self, source_name: str | None = None) -> dict[str, Any]:
        if source_name is None:
            return {"sources": list(self.sources.keys()), "status": "ok"}
        source = self._require_source(source_name)
        exists = bool(source.path and source.path.exists()) if source.path else source.type != "local"
        return {
            "name": source.name,
            "type": source.type,
            "path": str(source.path) if source.path else None,
            "exists": exists,
            "status": "ready" if exists else "not_ready",
        }

    def load(self, source: str, reference: str | None = None) -> list[ParsedDocument]:
        source_config = self._require_source(source)
        if source_config.type == "local":
            return self._load_local(source_config, reference=reference)
        return []

    def parse(self, document: ParsedDocument, parser: str = "text") -> ParsedDocument:
        if parser == "html":
            text = re.sub(r"<[^>]+>", "", document.text)
            return ParsedDocument(
                source=document.source,
                reference=document.reference,
                text=text,
                metadata=document.metadata,
            )
        return document

    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        text = self._normalize_text(document.text)
        chunks: list[DocumentChunk] = []
        start = 0
        idx = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            chunk_text = text[start:end]
            chunks.append(
                DocumentChunk(
                    source=document.source,
                    reference=document.reference,
                    chunk_index=idx,
                    text=chunk_text,
                    start=start,
                    end=end,
                    token_hint=max(1, len(chunk_text) // 4),
                )
            )
            idx += 1
            if end == len(text):
                break
            start = max(0, end - self.chunk_overlap)
        return chunks

    def sync_plan(self, source: str | None = None) -> list[DocumentSyncPlan]:
        sources = [self._require_source(source)] if source else list(self.sources.values())
        return [
            DocumentSyncPlan(
                source=item.name,
                operations=self._collect_sync_operations(item),
            )
            for item in sources
        ]

    def sync_request(self, source: str | None = None) -> dict[str, Any]:
        plans = self.sync_plan(source)
        executed = 0
        for plan in plans:
            executed += len(plan.operations)
        return {"status": "ok", "operations": executed, "plan_count": len(plans)}

    def inspect(self) -> dict[str, Any]:
        return {
            "namespace": self.key,
            "sources": self.list_sources(),
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "include_hidden": self.include_hidden,
        }

    def _collect_sync_operations(self, source: DocumentSource) -> list[dict[str, Any]]:
        if source.type == "local":
            if source.path is None or not source.path.exists():
                return [{"name": "source_not_found", "reference": None}]
            return [
                {"name": "ingest_file", "reference": str(item)}
                for item in self._iter_local_files(source.path)
            ]
        return [{"name": "unsupported_source_type", "type": source.type}]

    def _load_local(self, source: DocumentSource, reference: str | None = None) -> list[ParsedDocument]:
        if source.path is None or not source.path.exists():
            return []
        refs: list[Path] = []
        if reference:
            candidate = source.path / reference if source.path.is_dir() else source.path
            if candidate.exists():
                refs = [candidate]
        else:
            refs = list(self._iter_local_files(source.path))
        output: list[ParsedDocument] = []
        for ref in refs:
            if not self.include_hidden and ref.name.startswith("."):
                continue
            if ref.is_file():
                text = ref.read_text(encoding="utf-8", errors="replace")
                output.append(
                    ParsedDocument(
                        source=source.name,
                        reference=quote(ref.as_posix()),
                        text=text,
                        metadata=DocumentMetadata(
                            source=source.name,
                            mime="text/plain",
                            modified_at=str(
                                ref.stat().st_mtime
                            ),
                            title=ref.name,
                        ),
                    )
                )
        return output

    def _iter_local_files(self, path: Path):
        if path.is_file():
            yield path
            return
        for entry in sorted(path.rglob("*")):
            if entry.is_file():
                yield entry

    def _require_source(self, source_name: str) -> DocumentSource:
        if source_name not in self.sources:
            raise KeyError(f"Source '{source_name}' not found")
        return self.sources[source_name]

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
