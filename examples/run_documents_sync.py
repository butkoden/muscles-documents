from __future__ import annotations

"""Sync plan example for documents package.

Run:
  PYTHONPATH=src python examples/run_documents_sync.py
"""

from tempfile import TemporaryDirectory

from types import SimpleNamespace
from pathlib import Path

from muscles import ActionDispatcher
from muscles_documents import init_package


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "policy.txt").write_text("Policy statement for one source", encoding="utf-8")

        app = SimpleNamespace()
        init_package(
            app,
            {
                "key": "documents",
                "sources": {
                    "policy": {
                        "type": "local",
                        "path": str(root),
                    },
                },
            },
        )

        dispatcher = ActionDispatcher(app)
        inspect_runtime = dispatcher.execute("documents.inspect", {})
        print("inspect ->", inspect_runtime.value)

        plan = dispatcher.execute("documents.sync.plan", {"source": "policy"})
        print("sync plan ->", plan.value)

        requested = dispatcher.execute("documents.sync.request", {})
        print("sync request ->", requested.value)

        targeted = dispatcher.execute("documents.sync.request", {"source": "policy"})
        print("targeted sync ->", targeted.value)

        doctor = dispatcher.execute("documents.doctor", {})
        print("doctor ->", doctor.value)


if __name__ == "__main__":
    main()
