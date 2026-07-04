from __future__ import annotations

from typing import Any

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
    },
    "required": ["source", "reference", "text"],
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
            description="Load raw text documents for a source.",
            input_schema=LOAD_SCHEMA,
            handler=_load,
            transports=transports,
        )
        _register_action(
            app,
            name="documents.parse",
            description="Parse text into normalized document.",
            input_schema=PARSE_SCHEMA,
            handler=_parse,
            transports=transports,
        )
        _register_action(
            app,
            name="documents.chunk",
            description="Split text into chunks.",
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
            description="Execute ingestion sync plan for source(s).",
            input_schema=LIST_SCHEMA,
        handler=_sync_request,
        transports=["cli", "http", "mcp"],
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
    return {"sources": pipeline.list_sources()}


def _source_inspect(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    return pipeline.inspect_source(source_name=payload.get("source"))


def _load(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    documents = pipeline.load(source=payload["source"], reference=payload.get("reference"))
    return {
        "count": len(documents),
        "documents": [
            {"source": item.source, "reference": item.reference, "text": item.text[:250], "metadata": item.metadata.__dict__}
            for item in documents
        ],
    }


def _parse(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    from .schemas import ParsedDocument, DocumentMetadata

    pipeline = _pipeline(context)
    parser = payload.get("parser", "text")
    parsed = pipeline.parse(
        ParsedDocument(
            source=payload["source"],
            reference=payload["reference"],
            text=payload["text"],
            metadata=DocumentMetadata(source=payload["source"], mime="text/plain"),
        ),
        parser=parser,
    )
    return {"source": parsed.source, "reference": parsed.reference, "text": parsed.text}


def _chunk(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    from .schemas import ParsedDocument, DocumentMetadata

    pipeline = _pipeline(context)
    parsed = ParsedDocument(
        source=payload["source"],
        reference=payload["reference"],
        text=payload["text"],
        metadata=DocumentMetadata(source=payload["source"], mime="text/plain"),
    )
    chunks = pipeline.chunk(parsed)
    return {
        "source": payload["source"],
        "reference": payload["reference"],
        "chunks": [chunk.__dict__ for chunk in chunks],
    }


def _sync_plan(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    plans = pipeline.sync_plan(source=payload.get("source"))
    return {"plans": [{"source": item.source, "operations": item.operations} for item in plans]}


def _sync_request(payload: dict[str, Any], context: ActionContext) -> dict[str, Any]:
    pipeline = _pipeline(context)
    return pipeline.sync_request(source=payload.get("source"))
