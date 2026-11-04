from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from typing import Any, Iterator

try:
    from muscles import ActionContext
except Exception:  # pragma: no cover
    from muscles.core.core import ActionContext

try:
    from muscles import register_action  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    register_action = None


def _register_action(app, **kwargs):
    if register_action is not None:
        return register_action(app, **kwargs)
    from muscles.core.core import ActionContract, get_application_registry

    return get_application_registry(app).add_action(
        ActionContract(
            name=kwargs["name"],
            description=kwargs.get("description", ""),
            input_schema=kwargs.get("input_schema", None),
            output_schema=kwargs.get("output_schema", None),
            rules=kwargs.get("rules", []),
            handler_ref=kwargs.get("handler_ref", None),
            transports=kwargs.get("transports", []),
            stream_output=kwargs.get("stream_output", False),
            stream_metadata=kwargs.get("stream_metadata", None) or {},
            metadata=kwargs.get("metadata", None) or {},
            handler=kwargs.get("handler"),
        )
    )


LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
    },
    "additionalProperties": False,
}


LOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "reference": {"type": "string"},
        "parser": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1},
    },
    "required": ["source"],
    "additionalProperties": False,
}


PARSE_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "source": {"type": "string"},
        "reference": {"type": "string"},
        "parser": {"type": "string"},
        "mime": {"type": "string"},
        "metadata": {"type": "object"},
    },
    "required": ["text", "source", "reference"],
    "additionalProperties": False,
}


NORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "source": {"type": "string"},
        "reference": {"type": "string"},
        "parser": {"type": "string"},
        "mime": {"type": "string"},
        "metadata": {"type": "object"},
    },
    "required": ["text", "source", "reference"],
    "additionalProperties": False,
}


CHUNK_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "reference": {"type": "string"},
        "text": {"type": "string"},
        "parser": {"type": "string"},
        "mime": {"type": "string"},
        "strategy": {"type": "string", "enum": ["fixed", "heading"]},
        "metadata": {"type": "object"},
    },
    "required": ["source", "reference", "text"],
    "additionalProperties": False,
}


EMPTY_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def register_document_actions(app, *, transports: list[str]):
    _register_action(
        app,
        name="documents.sources.list",
        description="List declared sources.",
        input_schema=LIST_SCHEMA,
        handler=_list_sources,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.source.inspect",
        description="Inspect one source or all declared sources.",
        input_schema=LIST_SCHEMA,
        handler=_source_inspect,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.load",
        description="Load raw document blobs for a source.",
        input_schema=LOAD_SCHEMA,
        handler=_load,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.parse",
        description="Parse text into a structured document.",
        input_schema=PARSE_SCHEMA,
        handler=_parse,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.normalize",
        description="Normalize parsed or raw document text.",
        input_schema=NORMALIZE_SCHEMA,
        handler=_normalize,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.chunk",
        description="Split structured text into chunks.",
        input_schema=CHUNK_SCHEMA,
        handler=_chunk,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.sync.plan",
        description="Build ingestion plan for source(s).",
        input_schema=LIST_SCHEMA,
        handler=_sync_plan,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.sync.request",
        description="Request execution of an ingestion sync plan.",
        input_schema=LIST_SCHEMA,
        handler=_sync_request,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.inspect",
        description="Inspect document ingestion runtime capabilities.",
        input_schema=EMPTY_SCHEMA,
        handler=_inspect,
        transports=transports,
    )
    _register_action(
        app,
        name="documents.doctor",
        description="Run safe document ingestion diagnostics.",
        input_schema=EMPTY_SCHEMA,
        handler=_doctor,
        transports=transports,
    )


def _pipeline(context: ActionContext):
    container = getattr(context.application, "container", None)
    if container is None:
        raise RuntimeError("documents runtime is not initialized")
    from .runtime import DocumentPipeline

    try:
        return container.resolve(DocumentPipeline)
    except KeyError as exc:
        raise RuntimeError("documents runtime is not registered") from exc


def _list_sources(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    del payload
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.source.list"):
        return {"sources": pipeline.list_sources()}


def _source_inspect(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.source.inspect", **_document_attributes(pipeline, payload)):
        return pipeline.inspect_source(source_name=payload.get("source"))


def _load(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.load", **_document_attributes(pipeline, payload)):
        blobs = pipeline.load_blobs(
            source=payload["source"],
            reference=payload.get("reference"),
            limit=payload.get("limit"),
        )
    return {
        "count": len(blobs),
        "documents": [
            {
                "source": blob.source,
                "reference": blob.reference,
                "mime": blob.mime,
                "text": blob.text,
                "checksum": blob.checksum,
                "metadata": _safe_metadata(blob.metadata),
            }
            for blob in blobs
        ],
    }


def _parse(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    parser = payload.get("parser", "auto")
    telemetry = _telemetry(context)
    with telemetry.span("muscles.documents.parse", **_document_attributes(pipeline, payload, parser=parser)):
        parsed = pipeline.parse_text(
            source=payload["source"],
            reference=payload["reference"],
            text=payload["text"],
            parser=parser,
            mime=payload.get("mime"),
            metadata=_safe_metadata(payload.get("metadata")),
        )
    with telemetry.span("muscles.documents.normalize", **_document_attributes(pipeline, payload, parser=parser)):
        pass
    return _serialize(parsed)


def _normalize(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    parser = payload.get("parser", "auto")
    with _telemetry(context).span("muscles.documents.normalize", **_document_attributes(pipeline, payload, parser=parser)):
        parsed = pipeline.parse_text(
            source=payload["source"],
            reference=payload["reference"],
            text=payload["text"],
            parser=parser,
            mime=payload.get("mime"),
            metadata=_safe_metadata(payload.get("metadata")),
        )
        normalized = pipeline.normalize(parsed)
    return _serialize(normalized)


def _chunk(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    parser = payload.get("parser", "auto")
    strategy = payload.get("strategy", "fixed")
    with _telemetry(context).span(
        "muscles.documents.chunk",
        **_document_attributes(pipeline, payload, parser=parser),
        **{"documents.chunker": strategy},
    ):
        parsed = pipeline.parse_text(
            source=payload["source"],
            reference=payload["reference"],
            text=payload["text"],
            parser=parser,
            mime=payload.get("mime"),
            metadata=_safe_metadata(payload.get("metadata")),
        )
        normalized = pipeline.normalize(parsed)
        chunks = pipeline.chunk(normalized, strategy=strategy)
    return {
        "source": payload["source"],
        "reference": payload["reference"],
        "chunks": [_serialize(chunk) for chunk in chunks],
    }


def _sync_plan(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.sync.plan", **_document_attributes(pipeline, payload)):
        plans = pipeline.sync_plan(source=payload.get("source"))
    return {"plans": [_serialize(plan) for plan in plans]}


def _sync_request(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.sync.execute", **_document_attributes(pipeline, payload)):
        return _serialize(pipeline.sync_request(source=payload.get("source")))


def _inspect(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    del payload
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.inspect"):
        return pipeline.inspect()


def _doctor(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    del payload
    pipeline = _pipeline(context)
    with _telemetry(context).span("muscles.documents.doctor"):
        return pipeline.doctor()


def _telemetry(context: ActionContext):
    try:
        from muscles import resolve_telemetry  # type: ignore[import-not-found]

        return resolve_telemetry(context.application)
    except Exception:
        return _NoopTelemetry()


def _document_attributes(pipeline, payload: dict[str, Any], *, parser: str | None = None) -> dict[str, Any]:
    source_name = payload.get("source")
    source = getattr(pipeline, "sources", {}).get(source_name)
    attributes: dict[str, Any] = {}
    if source_name is not None:
        attributes["documents.source"] = source_name
    if source is not None:
        attributes["documents.source.type"] = source.type
    if parser is not None:
        attributes["documents.parser"] = parser
    attributes["documents.mime"] = payload.get("mime", "text/plain")
    return attributes


def _safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    blocked = ("secret", "token", "password", "key", "credential")
    return {
        str(key): item
        for key, item in value.items()
        if not any(marker in str(key).lower() for marker in blocked)
    }


def _serialize(value: Any):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


class _NoopTelemetry:
    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[None]:
        del name, attributes
        yield
