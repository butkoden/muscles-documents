from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from muscles import ActionDispatcher, inspect_application

from muscles_documents import DocumentsPackage
from muscles_documents.runtime import DocumentPipeline


def test_documents_init_registers_actions_and_runtime(tmp_path: Path):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("hello world\nanother line", encoding="utf-8")

    package = DocumentsPackage()
    app = SimpleNamespace()
    runtime = package.init(
        app,
        {
            "key": "documents",
            "sources": {
                "docs": {"type": "local", "path": os.fspath(source_dir)},
            },
            "chunk_size": 4,
            "chunk_overlap": 0,
        },
    )
    assert isinstance(runtime, DocumentPipeline)
    contract = inspect_application(app)
    action_names = {action["name"] for action in contract["actions"]}
    assert "documents.sources.list" in action_names
    assert "documents.parse" in action_names

    dispatcher = ActionDispatcher(app)
    result = dispatcher.execute("documents.sources.list", {"source": "docs"})
    assert result.value["sources"] == ["docs"]


def test_documents_public_exports():
    import muscles_documents as md

    assert hasattr(md, "DocumentPipeline")
    assert hasattr(md, "DocumentsPackage")
