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
- `muscles.documents.load`
- `muscles.documents.parse`
- `muscles.documents.normalize`
- `muscles.documents.chunk`
- `muscles.documents.sync.plan`
- `muscles.documents.sync.execute`

## Safe attributes

- `documents.source`
- `documents.source.type`
- `documents.mime`
- `documents.parser`
- `documents.chunker`

Do not add raw document text, HTML body, extracted text, file content, document
chunks, source credentials or tokens to span attributes.
