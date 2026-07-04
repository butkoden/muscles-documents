from __future__ import annotations

"""Simple document ingestion pipeline smoke example.

Run:
  PYTHONPATH=src python examples/run_documents_pipeline.py
"""

from tempfile import TemporaryDirectory

from types import SimpleNamespace
from pathlib import Path

from muscles import ActionDispatcher
from muscles_documents import init_package


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "guide.md").write_text("<h1>Muscles documents</h1>\n\nSimple paragraph for parsing.", encoding="utf-8")
        (root / "notes.txt").write_text("Line 1\nLine 2\n", encoding="utf-8")

        app = SimpleNamespace()
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

        loaded = dispatcher.execute("documents.load", {"source": "repo"})
        print("loaded ->", loaded.value["count"], "documents")

        first = loaded.value["documents"][0]
        parsed = dispatcher.execute(
            "documents.parse",
            {
                "source": first["source"],
                "reference": first["reference"],
                "text": first["text"],
                "parser": "html",
            },
        )
        print("parsed text length ->", len(parsed.value["text"]))

        chunks = dispatcher.execute(
            "documents.chunk",
            {
                "source": first["source"],
                "reference": first["reference"],
                "text": first["text"],
            },
        )
        print("chunks ->", len(chunks.value["chunks"]))


if __name__ == "__main__":
    main()

