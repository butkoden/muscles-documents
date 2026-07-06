from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from muscles import ActionDispatcher, inspect_application

from muscles_documents import DocumentsPackage
from muscles_documents.config import SourceConfig
from muscles_documents.runtime import DocumentPipeline
from muscles_documents.schemas import (
    DocumentBlob,
    DocumentBlock,
    DocumentRef,
    DocumentSection,
    DocumentSyncResult,
)


def _pipeline(source_dir: Path, **options: Any) -> DocumentPipeline:
    return DocumentPipeline(
        key="documents",
        sources={
            "docs": SourceConfig(
                name="docs",
                type="local",
                path=os.fspath(source_dir),
                options=dict(options),
            )
        },
        chunk_size=64,
        chunk_overlap=8,
    )


def test_public_contracts_are_json_serializable_and_extensible():
    ref = DocumentRef(
        source="docs",
        reference="resume/flowwow.md",
        source_type="local",
        metadata={"project_field": "kept"},
    )
    blob = DocumentBlob(
        source="docs",
        reference=ref.reference,
        mime="text/markdown",
        text="# Flowwow\nBackend work",
        checksum="sha256:abc",
        metadata={"project_field": "kept"},
    )
    section = DocumentSection(
        section_id="s-1",
        title="Flowwow",
        section_path="Resume / Flowwow",
        level=2,
        start=0,
        end=22,
        metadata={"project_field": "kept"},
    )
    block = DocumentBlock(
        block_id="b-1",
        block_type="paragraph",
        text="Backend work",
        section_id=section.section_id,
        section_path=section.section_path,
        start=10,
        end=22,
        metadata={"project_field": "kept"},
    )
    result = DocumentSyncResult(
        source="docs",
        status="planned",
        operations_total=1,
        operations_completed=0,
        request_id="request-41",
    )

    assert asdict(ref)["metadata"]["project_field"] == "kept"
    assert asdict(blob)["checksum"] == "sha256:abc"
    assert asdict(section)["section_path"] == "Resume / Flowwow"
    assert asdict(block)["block_type"] == "paragraph"
    assert asdict(result)["status"] == "planned"


def test_local_ingestion_flow_preserves_provenance_and_stable_chunks(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "resume.md").write_text(
        "# Resume\n"
        "\n"
        "Intro paragraph.\n"
        "\n"
        "## Flowwow\n"
        "Kafka PostgreSQL architecture.\n"
        "\n"
        "```python\n"
        "print('keep code')\n"
        "```\n",
        encoding="utf-8",
    )

    pipeline = _pipeline(docs)

    refs = pipeline.list_refs("docs")
    assert [ref.reference for ref in refs] == ["resume.md"]
    assert refs[0].source_type == "local"
    assert refs[0].checksum.startswith("sha256:")

    blob = pipeline.load_blob("docs", "resume.md")
    assert isinstance(blob, DocumentBlob)
    assert blob.reference == "resume.md"
    assert blob.mime == "text/markdown"
    assert blob.text.startswith("# Resume")

    parsed = pipeline.parse_blob(blob)
    assert parsed.text is not None
    assert [section.title for section in parsed.sections] == ["Resume", "Flowwow"]
    assert parsed.sections[1].section_path == "Resume / Flowwow"
    assert any(block.section_path == "Resume / Flowwow" for block in parsed.blocks)

    normalized = pipeline.normalize(parsed)
    assert "```python\nprint('keep code')\n```" in normalized.text
    assert "Kafka PostgreSQL architecture." in normalized.text

    chunks = pipeline.chunk(normalized, strategy="heading")
    same_chunks = pipeline.chunk(pipeline.normalize(pipeline.parse_blob(blob)), strategy="heading")

    assert chunks
    assert [chunk.chunk_id for chunk in chunks] == [chunk.chunk_id for chunk in same_chunks]
    assert all(chunk.text.strip() for chunk in chunks)
    assert all(chunk.source == "docs" and chunk.reference == "resume.md" for chunk in chunks)
    assert any(chunk.section_path == "Resume / Flowwow" for chunk in chunks)
    assert all(chunk.metadata.get("checksum") == blob.checksum for chunk in chunks)


def test_html_parser_sanitizes_scripts_and_extracts_text(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "page.html").write_text(
        "<h1>Title</h1><script>alert('secret')</script><p>Hello <b>world</b></p>",
        encoding="utf-8",
    )

    pipeline = _pipeline(docs)
    blob = pipeline.load_blob("docs", "page.html")
    parsed = pipeline.parse_blob(blob)

    assert parsed.metadata.mime == "text/html"
    assert "alert" not in parsed.text
    assert "Title" in parsed.text
    assert "Hello world" in parsed.text
    assert parsed.sections[0].title == "Title"


def test_local_loader_rejects_path_traversal(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "secret.txt").write_text("do not read", encoding="utf-8")

    pipeline = _pipeline(docs)

    with pytest.raises(ValueError, match="outside source root"):
        pipeline.load_blob("docs", "../secret.txt")


def test_sync_plan_is_deterministic_and_read_only(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("A", encoding="utf-8")
    (docs / "b.txt").write_text("B", encoding="utf-8")

    pipeline = _pipeline(docs)
    first = pipeline.sync_plan("docs")[0]
    second = pipeline.sync_plan("docs")[0]

    assert first.operations == second.operations
    assert [operation["name"] for operation in first.operations] == ["add", "add"]
    assert [operation["reference"] for operation in first.operations] == ["a.txt", "b.txt"]
    assert all(operation["checksum"].startswith("sha256:") for operation in first.operations)

    result = pipeline.sync_request("docs")
    assert isinstance(result, DocumentSyncResult)
    assert result.status == "planned"
    assert result.operations_total == 2
    assert result.operations_completed == 0


def test_actions_expose_ingestion_toolkit_without_leaking_secrets(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "resume.md").write_text("# Resume\n\nBody", encoding="utf-8")
    app = SimpleNamespace()
    DocumentsPackage().init(
        app,
        {
            "key": "documents",
            "sources": {
                "docs": {
                    "type": "local",
                    "path": os.fspath(docs),
                    "api_key": "super-secret-token",
                }
            },
            "chunk_size": 32,
            "chunk_overlap": 4,
        },
    )

    action_names = {action["name"] for action in inspect_application(app)["actions"]}
    assert {
        "documents.sources.list",
        "documents.source.inspect",
        "documents.load",
        "documents.parse",
        "documents.normalize",
        "documents.chunk",
        "documents.sync.plan",
        "documents.sync.request",
        "documents.inspect",
        "documents.doctor",
    } <= action_names

    dispatcher = ActionDispatcher(app)
    loaded = dispatcher.execute("documents.load", {"source": "docs"}).value
    first = loaded["documents"][0]
    parsed = dispatcher.execute(
        "documents.parse",
        {
            "source": first["source"],
            "reference": first["reference"],
            "text": first["text"],
            "parser": "markdown",
        },
    ).value
    normalized = dispatcher.execute(
        "documents.normalize",
        {
            "source": parsed["source"],
            "reference": parsed["reference"],
            "text": parsed["text"],
        },
    ).value
    chunks = dispatcher.execute(
        "documents.chunk",
        {
            "source": normalized["source"],
            "reference": normalized["reference"],
            "text": normalized["text"],
            "strategy": "heading",
        },
    ).value
    inspect = dispatcher.execute("documents.inspect", {}).value
    doctor = dispatcher.execute("documents.doctor", {}).value

    assert parsed["sections"][0]["title"] == "Resume"
    assert normalized["text"] == "# Resume\n\nBody"
    assert chunks["chunks"][0]["chunk_id"]
    assert inspect["namespace"] == "documents"
    assert inspect["sources"] == [{"name": "docs", "type": "local", "enabled": True}]
    assert doctor["status"] == "ok"
    assert "super-secret-token" not in repr(inspect)
    assert "super-secret-token" not in repr(doctor)


def test_documents_source_does_not_import_storage_or_ai_vendors():
    source_root = Path(__file__).resolve().parents[1] / "src" / "muscles_documents"
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))

    forbidden = [
        "muscles_ai",
        "sqlalchemy",
        "qdrant",
        "elasticsearch",
        "opensearch",
        "redis",
        "pymongo",
    ]
    for marker in forbidden:
        assert marker not in source_text
