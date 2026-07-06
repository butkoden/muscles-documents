from __future__ import annotations

"""Simple document ingestion pipeline smoke example.

Run:
  PYTHONPATH=src python examples/run_documents_pipeline.py
"""

from contextlib import contextmanager
from tempfile import TemporaryDirectory

from types import SimpleNamespace
from pathlib import Path
from typing import Any, Iterator

from muscles import ActionDispatcher, DependencyContainer, TelemetryProvider
from muscles_documents import init_package


class MemoryTelemetry:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[None]:
        self.records.append((name, dict(attributes)))
        yield


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "guide.md").write_text(
            "# Muscles documents\n\n"
            "Simple paragraph for parsing.\n\n"
            "## Flow\n"
            "Load, parse, normalize and chunk without owning project storage.",
            encoding="utf-8",
        )
        (root / "notes.txt").write_text("Line 1\nLine 2\n", encoding="utf-8")

        telemetry = MemoryTelemetry()
        app = SimpleNamespace(container=DependencyContainer())
        app.container.register(TelemetryProvider, lambda: telemetry)

        init_package(
            app,
            {
                "key": "documents",
                "chunk_size": 12,
                "chunk_overlap": 3,
                "sources": {
                    "repo": {
                        "type": "local",
                        "path": str(root),
                    }
                },
            },
        )

        dispatcher = ActionDispatcher(app)

        sources = dispatcher.execute("documents.sources.list", {"source": "repo"})
        print("sources ->", sources.value)

        inspect_source = dispatcher.execute("documents.source.inspect", {"source": "repo"})
        print("source.inspect ->", inspect_source.value)

        inspect_runtime = dispatcher.execute("documents.inspect", {})
        print("inspect ->", inspect_runtime.value)

        doctor = dispatcher.execute("documents.doctor", {})
        print("doctor ->", doctor.value)

        loaded = dispatcher.execute("documents.load", {"source": "repo"})
        print("loaded ->", loaded.value["count"], "documents")

        first = loaded.value["documents"][0]
        parsed = dispatcher.execute(
            "documents.parse",
            {
                "source": first["source"],
                "reference": first["reference"],
                "text": first["text"],
                "parser": "auto",
            },
        )
        print("sections ->", [section["section_path"] for section in parsed.value["sections"]])

        normalized = dispatcher.execute(
            "documents.normalize",
            {
                "source": parsed.value["source"],
                "reference": parsed.value["reference"],
                "text": parsed.value["text"],
                "parser": "markdown",
            },
        )
        print("normalized text length ->", len(normalized.value["text"]))

        chunks = dispatcher.execute(
            "documents.chunk",
            {
                "source": normalized.value["source"],
                "reference": normalized.value["reference"],
                "text": normalized.value["text"],
                "strategy": "heading",
            },
        )
        print("chunks ->", len(chunks.value["chunks"]))
        print("telemetry spans:", [name for name, _ in telemetry.records])


if __name__ == "__main__":
    main()
