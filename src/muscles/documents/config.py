from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class SourceConfig:
    name: str
    type: str
    path: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentsConfig:
    key: str
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    chunk_size: int = 1000
    chunk_overlap: int = 80
    include_hidden: bool = False

    @classmethod
    def from_raw(cls, value: Mapping[str, Any], *, init_key: str = "documents") -> "DocumentsConfig":
        data = dict(value or {})
        if "key" not in data and "name" in data:
            data["key"] = data["name"]
        data.setdefault("key", init_key)

        raw_sources = data.get("sources", {}) or {}
        sources: dict[str, SourceConfig] = {}
        for source_key, source_value in dict(raw_sources).items():
            normalized = dict(source_value or {})
            source_type = str(normalized.get("type", "local"))
            path = normalized.get("path")
            if source_type == "local" and not path:
                raise ValueError(f"local source '{source_key}' requires path")
            sources[str(source_key)] = SourceConfig(
                name=str(source_key),
                type=source_type,
                path=str(path) if path is not None else None,
                options=dict(normalized),
            )

        return cls(
            key=str(data["key"]),
            sources=sources,
            chunk_size=int(data.get("chunk_size", 1000)),
            chunk_overlap=int(data.get("chunk_overlap", 80)),
            include_hidden=bool(data.get("include_hidden", False)),
        )
