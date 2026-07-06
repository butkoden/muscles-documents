from __future__ import annotations

import inspect
from typing import Any

from .actions import register_document_actions
from .config import DocumentsConfig
from .runtime import DocumentPipeline


class DocumentsPackage:
    namespace = "documents"

    def build_runtime(self, app, config):
        del app
        return self._build_runtime(_normalize_config(config or {}))

    def services(self, app, runtime: DocumentPipeline):
        del app
        return [_package_service(DocumentPipeline, lambda: runtime)]

    def actions(self, app, runtime: DocumentPipeline, *, config):
        del runtime
        package_config = config if isinstance(config, DocumentsConfig) else _normalize_config(config or {})
        register_document_actions(app, transports=config_options_transports(package_config))
        return []

    def inspection_provider(self, app, runtime: DocumentPipeline, config=None):
        del app, config
        return runtime.inspect

    def doctor_provider(self, app, runtime: DocumentPipeline, config=None):
        del app, config

        def doctor_documents() -> dict[str, Any]:
            return {
                "status": "ok",
                "checks": [
                    {
                        "name": "documents.runtime.exists",
                        "status": "ok" if runtime is not None else "failed",
                    }
                ],
            }

        return doctor_documents

    def init(self, app, config):
        package_config = _normalize_config(config or {})
        runtime = self.build_runtime(app, package_config)
        _apply_services(app, self.services(app, runtime))
        self.actions(app, runtime, config=package_config)
        return runtime

    def _build_runtime(self, config: DocumentsConfig) -> DocumentPipeline:
        return DocumentPipeline(
            key=config.key,
            sources=config.sources,
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            include_hidden=config.include_hidden,
        )

    def _register_services(self, app, runtime: DocumentPipeline) -> None:
        _apply_services(app, self.services(app, runtime))

    def _register_actions(self, app, config: DocumentsConfig):
        register_document_actions(app, transports=config_options_transports(config))


def init_package(app, config):
    package = DocumentsPackage()
    installable = _resolve_install_hook()
    if installable is not None:
        try:
            return installable(app=app, config=config, package=package)  # type: ignore[call-arg]
        except Exception:
            pass
    return package.init(app, config or {})


def _normalize_config(config) -> DocumentsConfig:
    if isinstance(config, DocumentsConfig):
        return config
    if not isinstance(config, dict):
        if hasattr(config, "_object"):
            raw = getattr(config, "_object")
            if isinstance(raw, dict):
                config = raw
        elif hasattr(config, "__dict__"):
            config = dict(config.__dict__)
        else:
            config = dict(config) if config is not None else {}
    return DocumentsConfig.from_raw(config or {}, init_key="documents")


def config_options_transports(config: DocumentsConfig) -> list[str]:
    if len(config.sources) > 0:
        return ["http", "mcp", "cli"]
    return ["cli"]


def _package_service(interface: type, provider: Any):
    try:
        from muscles import PackageService  # type: ignore[import-not-found]

        return PackageService(interface=interface, provider=provider)
    except Exception:
        return {"interface": interface, "provider": provider}


def _apply_services(app, services: Any) -> None:
    container = getattr(app, "container", None)
    if container is None:
        container = _dependency_container()
        setattr(app, "container", container)
    for service in services or []:
        if isinstance(service, dict):
            container.register(
                service["interface"],
                service["provider"],
                *tuple(service.get("args", ())),
                scope=service.get("scope", getattr(container, "APP", "app")),
                **dict(service.get("kwargs", {})),
            )
            continue
        container.register(
            service.interface,
            service.provider,
            *tuple(getattr(service, "args", ())),
            scope=getattr(service, "scope", getattr(container, "APP", "app")),
            **dict(getattr(service, "kwargs", {})),
        )


def _resolve_install_hook():
    try:
        from muscles.core.lifecycle import install_package  # type: ignore[import-not-found]
        return install_package
    except Exception:
        try:
            from muscles.lifecycle import install_package  # type: ignore[import-not-found]
            return install_package
        except Exception:
            return None


def _dependency_container():
    try:
        from muscles.core import DependencyContainer  # type: ignore[import-not-found]
        return DependencyContainer()
    except Exception:  # pragma: no cover
        return _LegacyContainer()


class _LegacyContainer:
    """
    Fallback container for older Muscles versions that do not expose DependencyContainer.
    """

    def __init__(self):
        self._entries: dict[type, tuple[Any, tuple[Any, ...], dict[str, Any]]] = {}

    def register(self, interface: type, provider: Any, *args: Any, **kwargs: Any):
        self._entries[interface] = (provider, args, kwargs)

    def resolve(self, interface: type):
        if interface not in self._entries:
            raise KeyError(f"Dependency {interface.__name__} not registered")
        provider, args, kwargs = self._entries[interface]
        if inspect.isclass(provider):
            return provider(*args, **kwargs)
        if callable(provider):
            return provider(*args, **kwargs)
        return provider
