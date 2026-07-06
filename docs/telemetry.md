# muscles-documents telemetry

`muscles-documents` uses the neutral Muscles telemetry contract:

```python
from muscles import resolve_telemetry

telemetry = resolve_telemetry(app)
with telemetry.span("muscles.documents.load"):
    ...
```

The package never imports `muscles_otel`. A project may install any provider
that implements `span(name, **attributes)`, including `muscles-otel`.

## Spans

- `muscles.documents.source.list`
- `muscles.documents.source.inspect`
- `muscles.documents.load`
- `muscles.documents.parse`
- `muscles.documents.normalize`
- `muscles.documents.chunk`
- `muscles.documents.sync.plan`
- `muscles.documents.sync.execute`
- `muscles.documents.inspect`
- `muscles.documents.doctor`

## Safe attributes

- `documents.source`
- `documents.source.type`
- `documents.mime`
- `documents.parser`
- `documents.chunker`

Do not add raw document text, HTML body, extracted text, file content, document
chunks, source credentials or tokens to span attributes.

`documents.inspect` and `documents.doctor` are designed for CLI/CI diagnostics.
They report source names, source types, parser/chunker availability and local
path readiness, but they must not expose raw content, credentials or private
connection details.
