# muscles-documents

Framework-level document ingestion and chunking package for the Muscles ecosystem.

## Purpose

- Define contracts for documents, chunking, parsing and metadata.
- Provide an initial pipeline for local files + markdown/text content ingestion.
- Expose `Muscles` actions to drive ingestion/diagnostics through any transport.

## Installation

```bash
pip install muscles-documents
```

Configured as a standard module package:

```yaml
modules:
  documents:
    package: muscles_documents
    sources:
      docs:
        type: local
        path: ./docs
```

## Actions

- `documents.sources.list`
- `documents.source.inspect`
- `documents.load`
- `documents.parse`
- `documents.chunk`
- `documents.sync.plan`
- `documents.sync.request`

## Scope

MVP is read-only: no writes to external systems are performed.
