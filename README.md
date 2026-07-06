# muscles-documents

Framework-level document ingestion and chunking package for the Muscles ecosystem.

## Purpose

- Define contracts for documents, chunking, parsing and metadata.
- Provide an initial pipeline for local files + markdown/text content ingestion.
- Expose `Muscles` actions to drive ingestion/diagnostics through any transport.

## Ecosystem Position

`muscles-documents` is a framework extension for document flows. It owns source
loading, parsing, chunking, metadata and sync planning; it does not own AI model
calls or protocol routing.

Related repositories:

- [`muscles`](https://github.com/butkoden/muscles) - core action contracts, dispatcher, inspect contract and canonical documentation.
- [`muscles-ai`](https://github.com/butkoden/muscles-ai) - AI/RAG actions that can consume document contracts.
- [`muscles-sql`](https://github.com/butkoden/muscles-sql) - SQL persistence for projects that store document metadata or ingestion state.
- [`muscles-mcp`](https://github.com/butkoden/muscles-mcp) - MCP projection for document actions when exposed to AI tools.
- [`muscles-benchmarks`](https://github.com/butkoden/muscles-benchmarks) - regression coverage for document extension contracts.

## Installation

```bash
pip install git+https://github.com/butkoden/muscles-documents.git
```

The canonical ecosystem install matrix lives in
[`muscles/docs/installation.md`](https://github.com/butkoden/muscles/blob/master/docs/installation.md).

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
Google Drive, HTML and richer storage adapters are extension points for later
package iterations; the current package keeps parser/source contracts stable
for those additions.

## Telemetry

`muscles-documents` resolves telemetry through the neutral Muscles
`TelemetryProvider`; it does not import `muscles-otel` directly.

When a project registers a provider, document actions emit safe spans:

- `muscles.documents.source.list`
- `muscles.documents.load`
- `muscles.documents.parse`
- `muscles.documents.normalize`
- `muscles.documents.chunk`
- `muscles.documents.sync.plan`
- `muscles.documents.sync.execute`

Allowed attributes include source name/type, MIME, parser and chunker metadata.
Raw document text, HTML body, extracted text, file content, source credentials
and tokens must not be stored in span attributes.

## Examples

### Local source smoke

Run a full `documents.*` action flow on temporary files:

```bash
PYTHONPATH=src python examples/run_documents_pipeline.py
```

### Sync plan and request

Build and inspect a sync plan for configured sources:

```bash
PYTHONPATH=src python examples/run_documents_sync.py
```

Both examples:

- initialize package via `init_package(app, config)`;
- use `ActionDispatcher` for actions;
- demonstrate `load`, `parse`, `chunk`, `sync.plan`, and `sync.request` flows;
- show neutral telemetry provider usage without requiring `muscles-otel`.
