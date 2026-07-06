from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from muscles import ActionDispatcher, DependencyContainer, TelemetryProvider

from muscles_documents import DocumentsPackage
from muscles_documents.package import init_package


class RecordingTelemetry:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[None]:
        self.records.append({"name": name, "attributes": dict(attributes)})
        yield


def _app_with_telemetry() -> tuple[SimpleNamespace, RecordingTelemetry]:
    app = SimpleNamespace(container=DependencyContainer())
    telemetry = RecordingTelemetry()
    app.container.register(TelemetryProvider, lambda: telemetry)
    return app, telemetry


def _config(source_dir: Path) -> dict[str, Any]:
    return {
        "key": "documents",
        "chunk_size": 8,
        "chunk_overlap": 0,
        "sources": {
            "docs": {"type": "local", "path": os.fspath(source_dir)},
        },
    }


def test_document_actions_emit_safe_framework_spans(tmp_path: Path):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    (source_dir / "a.html").write_text("<h1>Secret title</h1>\nRaw document body", encoding="utf-8")
    app, telemetry = _app_with_telemetry()
    DocumentsPackage().init(app, _config(source_dir))
    dispatcher = ActionDispatcher(app)

    dispatcher.execute("documents.sources.list", {"source": "docs"})
    loaded = dispatcher.execute("documents.load", {"source": "docs"})
    first = loaded.value["documents"][0]
    dispatcher.execute(
        "documents.parse",
        {
            "source": first["source"],
            "reference": first["reference"],
            "text": first["text"],
            "parser": "html",
        },
    )
    dispatcher.execute(
        "documents.chunk",
        {
            "source": first["source"],
            "reference": first["reference"],
            "text": first["text"],
        },
    )
    dispatcher.execute("documents.sync.plan", {"source": "docs"})
    dispatcher.execute("documents.sync.request", {"source": "docs"})

    assert {record["name"] for record in telemetry.records} >= {
        "muscles.documents.source.list",
        "muscles.documents.load",
        "muscles.documents.parse",
        "muscles.documents.normalize",
        "muscles.documents.chunk",
        "muscles.documents.sync.plan",
        "muscles.documents.sync.execute",
    }

    for record in telemetry.records:
        attributes = record["attributes"]
        assert "text" not in attributes
        assert "html" not in attributes
        assert "body" not in attributes
        assert "content" not in attributes
        assert "Secret title" not in repr(attributes)
        assert "Raw document body" not in repr(attributes)


def test_documents_init_package_uses_core_lifecycle_when_available(tmp_path: Path):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()
    app = SimpleNamespace()

    runtime = init_package(app, _config(source_dir))

    assert runtime is app.container.resolve(type(runtime))


def test_documents_source_does_not_import_muscles_otel_directly():
    source_root = Path(__file__).resolve().parents[1] / "src" / "muscles_documents"
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))

    assert "muscles_otel" not in source_text
