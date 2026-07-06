from __future__ import annotations

import hashlib
import html
import mimetypes
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

from .config import SourceConfig
from .schemas import (
    DocumentBlob,
    DocumentBlock,
    DocumentChunk,
    DocumentError,
    DocumentMetadata,
    DocumentRef,
    DocumentSection,
    DocumentSyncPlan,
    DocumentSyncResult,
    ParsedDocument,
)


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
        self.parsers = ("text", "markdown", "html")
        self.chunkers = ("fixed", "heading")

    def list_sources(self) -> list[str]:
        return sorted(self.sources.keys())

    def list_refs(self, source: str, *, limit: int | None = None) -> list[DocumentRef]:
        source_config = self._require_source(source)
        if source_config.type != "local":
            return []
        refs = [self._ref_from_path(source_config, path) for path in self._iter_local_files(source_config)]
        return refs if limit is None else refs[: max(0, limit)]

    def inspect_source(self, source_name: str | None = None) -> dict[str, Any]:
        if source_name is None:
            return {"sources": self.list_sources(), "status": "ok"}
        source = self._require_source(source_name)
        if source.type != "local":
            return {
                "name": source.name,
                "type": source.type,
                "exists": False,
                "readable": False,
                "status": "not_supported",
                "capabilities": ["inspect"],
            }
        exists = bool(source.path and source.path.exists())
        readable = bool(source.path and os.access(source.path, os.R_OK)) if exists else False
        return {
            "name": source.name,
            "type": source.type,
            "exists": exists,
            "readable": readable,
            "path_type": "file" if source.path and source.path.is_file() else "directory" if exists else None,
            "status": "ready" if exists and readable else "not_ready",
            "capabilities": ["list_refs", "load"],
        }

    def load(self, source: str, reference: str | None = None, *, limit: int | None = None) -> list[ParsedDocument]:
        return [self.parse_blob(blob) for blob in self.load_blobs(source, reference=reference, limit=limit)]

    def load_blobs(
        self,
        source: str,
        reference: str | None = None,
        *,
        limit: int | None = None,
    ) -> list[DocumentBlob]:
        source_config = self._require_source(source)
        if source_config.type != "local":
            return []
        if reference is not None:
            return [self.load_blob(source, reference)]
        blobs = [self._blob_from_path(source_config, path) for path in self._iter_local_files(source_config)]
        return blobs if limit is None else blobs[: max(0, limit)]

    def load_blob(self, source: str, reference: str) -> DocumentBlob:
        source_config = self._require_source(source)
        if source_config.type != "local":
            raise ValueError(f"Source '{source}' type '{source_config.type}' is not supported by local loader")
        path = self._resolve_local_reference(source_config, reference)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(reference)
        return self._blob_from_path(source_config, path)

    def parse(self, document: ParsedDocument, parser: str = "text") -> ParsedDocument:
        return self.parse_text(
            source=document.source,
            reference=document.reference,
            text=document.text,
            parser=parser,
            mime=document.metadata.mime,
            metadata=document.metadata.metadata,
        )

    def parse_text(
        self,
        *,
        source: str,
        reference: str,
        text: str,
        parser: str = "auto",
        mime: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ParsedDocument:
        selected_mime = mime or self._mime_for_reference(reference)
        blob = DocumentBlob(
            source=source,
            reference=reference,
            mime=selected_mime,
            text=text,
            checksum=self._checksum_text(text),
            source_type=self.sources.get(source, DocumentSource(source, "unknown")).type,
            title=Path(reference).name,
            size=len(text.encode("utf-8")),
            metadata=dict(metadata or {}),
        )
        return self.parse_blob(blob, parser=parser)

    def parse_blob(self, blob: DocumentBlob, parser: str = "auto") -> ParsedDocument:
        selected = self._select_parser(parser, blob.mime, blob.reference)
        text = blob.text
        if selected == "html":
            text = self._html_to_markdown_text(text)
        metadata = DocumentMetadata(
            source=blob.source,
            reference=blob.reference,
            source_type=blob.source_type,
            mime=blob.mime,
            checksum=blob.checksum,
            modified_at=blob.modified_at,
            title=blob.title,
            metadata=dict(blob.metadata),
        )
        sections, blocks = self._extract_structure(
            text,
            source=blob.source,
            reference=blob.reference,
            metadata=metadata,
        )
        return ParsedDocument(
            source=blob.source,
            reference=blob.reference,
            text=text,
            metadata=metadata,
            sections=sections,
            blocks=blocks,
        )

    def normalize(self, document: ParsedDocument) -> ParsedDocument:
        text = self._normalize_text(document.text)
        sections, blocks = self._extract_structure(
            text,
            source=document.source,
            reference=document.reference,
            metadata=document.metadata,
        )
        return ParsedDocument(
            source=document.source,
            reference=document.reference,
            text=text,
            metadata=document.metadata,
            sections=sections,
            blocks=blocks,
        )

    def chunk(self, document: ParsedDocument, *, strategy: str = "fixed") -> list[DocumentChunk]:
        strategy = strategy if strategy in self.chunkers else "fixed"
        segments = self._heading_segments(document) if strategy == "heading" else []
        if not segments:
            segments = [(None, None, 0, len(document.text), document.text)]

        chunks: list[DocumentChunk] = []
        for section_id, section_path, segment_start, _segment_end, segment_text in segments:
            for chunk_text, relative_start, relative_end in self._chunk_text(segment_text):
                absolute_start = segment_start + relative_start
                absolute_end = segment_start + relative_end
                chunk_id = self._stable_id(
                    "chunk",
                    document.source,
                    document.reference,
                    section_id or "",
                    str(len(chunks)),
                    str(absolute_start),
                    str(absolute_end),
                    document.metadata.checksum or "",
                )
                chunks.append(
                    DocumentChunk(
                        source=document.source,
                        reference=document.reference,
                        chunk_index=len(chunks),
                        text=chunk_text,
                        start=absolute_start,
                        end=absolute_end,
                        chunk_id=chunk_id,
                        token_hint=max(1, len(chunk_text) // 4),
                        section_id=section_id,
                        section_path=section_path,
                        metadata={
                            "checksum": document.metadata.checksum,
                            "mime": document.metadata.mime,
                            "title": document.metadata.title,
                        },
                    )
                )
        return chunks

    def sync_plan(self, source: str | None = None) -> list[DocumentSyncPlan]:
        sources = [self._require_source(source)] if source else [self.sources[name] for name in self.list_sources()]
        return [
            DocumentSyncPlan(
                source=item.name,
                operations=self._collect_sync_operations(item),
            )
            for item in sources
        ]

    def sync_request(self, source: str | None = None, *, request_id: str | None = None) -> DocumentSyncResult:
        plans = self.sync_plan(source)
        operations = [operation for plan in plans for operation in plan.operations]
        unsupported = [operation for operation in operations if operation["name"] == "unsupported_source_type"]
        failures = [operation for operation in operations if operation["name"] in {"source_not_found", "error"}]
        if operations and len(unsupported) == len(operations):
            status = "not_supported"
        elif failures:
            status = "partial" if len(failures) < len(operations) else "failed"
        else:
            status = "planned"
        return DocumentSyncResult(
            source=source or "*",
            status=status,
            operations_total=len(operations),
            operations_completed=0,
            errors=[
                DocumentError(code=operation["name"], message=operation.get("reason", operation["name"]))
                for operation in failures
            ],
            request_id=request_id,
        )

    def inspect(self) -> dict[str, Any]:
        return {
            "namespace": self.key,
            "version": "0.1.0",
            "sources": [
                {"name": source.name, "type": source.type, "enabled": True}
                for source in (self.sources[name] for name in self.list_sources())
            ],
            "source_count": len(self.sources),
            "loaders": ["local"],
            "parsers": list(self.parsers),
            "chunkers": list(self.chunkers),
            "chunk_policy": {
                "size": self.chunk_size,
                "overlap": self.chunk_overlap,
                "include_hidden": self.include_hidden,
            },
            "stores": {
                "state": False,
                "blob": False,
                "text": False,
                "chunk": False,
            },
            "executor": {"configured": False},
        }

    def doctor(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = [
            {"name": "documents.runtime.exists", "status": "ok"},
            {"name": "documents.parsers.available", "status": "ok", "parsers": list(self.parsers)},
            {"name": "documents.chunkers.available", "status": "ok", "chunkers": list(self.chunkers)},
        ]
        for source in (self.sources[name] for name in self.list_sources()):
            if source.type != "local":
                checks.append(
                    {
                        "name": f"documents.source.{source.name}",
                        "source": source.name,
                        "type": source.type,
                        "status": "warning",
                        "reason": "unsupported_source_type",
                    }
                )
                continue
            exists = bool(source.path and source.path.exists())
            readable = bool(source.path and os.access(source.path, os.R_OK)) if exists else False
            checks.append(
                {
                    "name": f"documents.source.{source.name}",
                    "source": source.name,
                    "type": source.type,
                    "status": "ok" if exists and readable else "failed",
                    "exists": exists,
                    "readable": readable,
                }
            )
        statuses = {check["status"] for check in checks}
        status = "failed" if "failed" in statuses else "warning" if "warning" in statuses else "ok"
        return {"status": status, "checks": checks}

    def _collect_sync_operations(self, source: DocumentSource) -> list[dict[str, Any]]:
        if source.type != "local":
            return [{"name": "unsupported_source_type", "type": source.type}]
        if source.path is None or not source.path.exists():
            return [{"name": "source_not_found", "reference": None, "reason": "local source path does not exist"}]
        return [
            {
                "name": "add",
                "reference": ref.reference,
                "checksum": ref.checksum,
                "mime": ref.mime,
                "modified_at": ref.modified_at,
                "size": ref.size,
            }
            for ref in self.list_refs(source.name)
        ]

    def _blob_from_path(self, source: DocumentSource, path: Path) -> DocumentBlob:
        raw = path.read_bytes()
        reference = self._reference_for_path(source, path)
        return DocumentBlob(
            source=source.name,
            reference=reference,
            source_type=source.type,
            mime=self._mime_for_reference(reference),
            text=raw.decode("utf-8", errors="replace"),
            checksum=self._checksum_bytes(raw),
            modified_at=str(path.stat().st_mtime),
            title=path.name,
            size=len(raw),
        )

    def _ref_from_path(self, source: DocumentSource, path: Path) -> DocumentRef:
        raw = path.read_bytes()
        reference = self._reference_for_path(source, path)
        return DocumentRef(
            source=source.name,
            reference=reference,
            source_type=source.type,
            mime=self._mime_for_reference(reference),
            title=path.name,
            checksum=self._checksum_bytes(raw),
            modified_at=str(path.stat().st_mtime),
            size=len(raw),
        )

    def _iter_local_files(self, source: DocumentSource) -> Iterable[Path]:
        if source.path is None or not source.path.exists():
            return []
        if source.path.is_file():
            return [source.path]
        return [
            entry
            for entry in sorted(source.path.rglob("*"), key=lambda item: item.as_posix())
            if entry.is_file() and (self.include_hidden or not self._is_hidden(source.path, entry))
        ]

    def _resolve_local_reference(self, source: DocumentSource, reference: str) -> Path:
        if source.path is None:
            raise FileNotFoundError(reference)
        root = source.path.resolve()
        raw_reference = unquote(reference)
        if source.path.is_file():
            allowed = {source.path.name, source.path.as_posix(), source.path.resolve().as_posix()}
            if raw_reference in allowed:
                return source.path
            raise FileNotFoundError(reference)
        candidate = Path(raw_reference)
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Reference '{reference}' is outside source root") from exc
        return resolved

    def _reference_for_path(self, source: DocumentSource, path: Path) -> str:
        if source.path is None:
            return path.name
        if source.path.is_file():
            return path.name
        return path.resolve().relative_to(source.path.resolve()).as_posix()

    def _heading_segments(self, document: ParsedDocument) -> list[tuple[str | None, str | None, int, int, str]]:
        sections = sorted(document.sections, key=lambda item: item.start)
        segments: list[tuple[str | None, str | None, int, int, str]] = []
        for index, section in enumerate(sections):
            next_start = sections[index + 1].start if index + 1 < len(sections) else len(document.text)
            end = max(section.start, min(section.end, next_start))
            text = document.text[section.start:end]
            if text.strip():
                segments.append((section.section_id, section.section_path, section.start, end, text))
        return segments

    def _chunk_text(self, text: str) -> Iterable[tuple[str, int, int]]:
        start = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            raw_chunk = text[start:end]
            stripped = raw_chunk.strip()
            if stripped:
                leading = len(raw_chunk) - len(raw_chunk.lstrip())
                trailing = len(raw_chunk.rstrip())
                yield stripped, start + leading, start + trailing
            if end == len(text):
                break
            start = max(0, end - self.chunk_overlap)

    def _extract_structure(
        self,
        text: str,
        *,
        source: str,
        reference: str,
        metadata: DocumentMetadata,
    ) -> tuple[list[DocumentSection], list[DocumentBlock]]:
        sections: list[DocumentSection] = []
        blocks: list[DocumentBlock] = []
        open_sections: list[tuple[int, int]] = []
        current_section_id: str | None = None
        current_section_path: str | None = None
        block_lines: list[str] = []
        block_start = 0
        block_type = "paragraph"
        in_code = False
        offset = 0

        def close_sections(until_level: int, end: int) -> None:
            while open_sections and open_sections[-1][0] >= until_level:
                _level, section_index = open_sections.pop()
                sections[section_index] = replace(sections[section_index], end=end)

        def flush_block(end: int) -> None:
            nonlocal block_lines, block_start, block_type
            block_text = "".join(block_lines).strip("\n")
            if block_text.strip():
                blocks.append(
                    DocumentBlock(
                        block_id=self._stable_id("block", source, reference, str(block_start), block_type),
                        block_type=block_type,
                        text=block_text,
                        section_id=current_section_id,
                        section_path=current_section_path,
                        start=block_start,
                        end=end,
                        metadata={"checksum": metadata.checksum},
                    )
                )
            block_lines = []
            block_type = "paragraph"

        for line in text.splitlines(keepends=True):
            line_start = offset
            line_end = offset + len(line)
            stripped = line.strip()
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
            if heading and not in_code:
                flush_block(line_start)
                level = len(heading.group(1))
                title = heading.group(2).strip()
                close_sections(level, line_start)
                parent_titles = [sections[index].title for _level, index in open_sections if _level < level]
                section_path = " / ".join([*parent_titles, title])
                section_id = self._stable_id("section", source, reference, str(line_start), title)
                sections.append(
                    DocumentSection(
                        section_id=section_id,
                        title=title,
                        section_path=section_path,
                        level=level,
                        start=line_start,
                        end=len(text),
                        metadata={"checksum": metadata.checksum},
                    )
                )
                open_sections.append((level, len(sections) - 1))
                current_section_id = section_id
                current_section_path = section_path
                blocks.append(
                    DocumentBlock(
                        block_id=self._stable_id("block", source, reference, str(line_start), "heading"),
                        block_type="heading",
                        text=title,
                        section_id=current_section_id,
                        section_path=current_section_path,
                        start=line_start,
                        end=line_end,
                        metadata={"level": level, "checksum": metadata.checksum},
                    )
                )
            elif stripped.startswith("```"):
                if not in_code:
                    flush_block(line_start)
                    in_code = True
                    block_start = line_start
                    block_type = "code"
                    block_lines = [line]
                else:
                    block_lines.append(line)
                    flush_block(line_end)
                    in_code = False
            elif not stripped and not in_code:
                flush_block(line_start)
            else:
                if not block_lines:
                    block_start = line_start
                    block_type = "code" if in_code else "paragraph"
                block_lines.append(line)
            offset = line_end

        flush_block(len(text))
        close_sections(1, len(text))
        return sections, blocks

    def _select_parser(self, parser: str, mime: str, reference: str) -> str:
        if parser != "auto":
            return parser
        if mime == "text/html":
            return "html"
        if mime == "text/markdown":
            return "markdown"
        if reference.lower().endswith((".md", ".markdown")):
            return "markdown"
        if reference.lower().endswith((".html", ".htm")):
            return "html"
        return "text"

    def _mime_for_reference(self, reference: str) -> str:
        lower = reference.lower()
        if lower.endswith((".md", ".markdown")):
            return "text/markdown"
        if lower.endswith((".html", ".htm")):
            return "text/html"
        guessed, _encoding = mimetypes.guess_type(reference)
        return guessed or "text/plain"

    def _html_to_markdown_text(self, value: str) -> str:
        cleaned = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.IGNORECASE | re.DOTALL)

        def heading(match: re.Match[str]) -> str:
            level = int(match.group(1))
            body = re.sub(r"<[^>]+>", "", match.group(2))
            title = html.unescape(body).strip()
            return f"\n{'#' * level} {title}\n"

        cleaned = re.sub(r"<h([1-6])\b[^>]*>(.*?)</h\1>", heading, cleaned, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</(p|div|li|tr|table|section|article)>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        cleaned = html.unescape(cleaned)
        return self._normalize_text(cleaned)

    def _require_source(self, source_name: str) -> DocumentSource:
        if source_name not in self.sources:
            raise KeyError(f"Source '{source_name}' not found")
        return self.sources[source_name]

    def _is_hidden(self, root: Path, path: Path) -> bool:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = path.parts
        return any(part.startswith(".") for part in parts)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized_parts: list[str] = []
        parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        for part in parts:
            if not part:
                continue
            if part.startswith("```") and part.endswith("```"):
                normalized_parts.append(part.strip("\n"))
                continue
            safe = "".join(char for char in part if char == "\n" or char == "\t" or ord(char) >= 32)
            lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in safe.splitlines()]
            prose = "\n".join(lines)
            prose = re.sub(r"\n{3,}", "\n\n", prose)
            normalized_parts.append(prose.strip("\n"))
        return "\n".join(part for part in normalized_parts if part).strip()

    @staticmethod
    def _checksum_bytes(value: bytes) -> str:
        return "sha256:" + hashlib.sha256(value).hexdigest()

    @classmethod
    def _checksum_text(cls, value: str) -> str:
        return cls._checksum_bytes(value.encode("utf-8"))

    @staticmethod
    def _stable_id(*parts: str) -> str:
        digest = hashlib.sha1("\0".join(parts).encode("utf-8")).hexdigest()
        return digest[:20]
