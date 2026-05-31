"""Mount RustStream export endpoints onto a FastAPI app.

Each helper adds two routes -- one for the export payload, one optional for the
viewer HTML -- through `app.add_api_route`, so they respect the same middleware,
authentication, and OpenAPI documentation as any other FastAPI route. Paths and
operation IDs are configurable for cases where the defaults clash with existing
routes.
"""

from typing import TYPE_CHECKING, Any

from ruststream._broker import Broker
from ruststream.app import RustStream
from ruststream.asyncapi import build_spec, render_viewer_html
from ruststream.fastapi._errors import MissingDependencyError

try:
    import fastapi as _fastapi
except ImportError as exc:
    raise MissingDependencyError() from exc


if TYPE_CHECKING:
    from fastapi import FastAPI


def mount_asyncapi(
    app: "FastAPI",
    target: Broker | RustStream,
    *,
    spec_path: str = "/asyncapi.json",
    viewer_path: str | None = "/docs/asyncapi",
    title: str = "RustStream service",
    version: str = "0.0.1",
    description: str | None = None,
) -> None:
    """Add `spec_path` (AsyncAPI JSON) and optionally `viewer_path` (HTML viewer).

    The spec is built lazily on each request through :func:`ruststream.asyncapi.build_spec`,
    so router/broker changes that happen after `mount_asyncapi` is called still appear
    in subsequent responses. Pass `viewer_path=None` to skip the HTML viewer route
    (useful when serving the spec into a separate AsyncAPI documentation site).
    """

    async def asyncapi_spec() -> dict[str, Any]:
        return build_spec(target, title=title, version=version, description=description)

    app.add_api_route(
        spec_path,
        asyncapi_spec,
        methods=["GET"],
        response_class=_fastapi.responses.JSONResponse,
        include_in_schema=False,
    )

    if viewer_path is not None:
        viewer_html = render_viewer_html(spec_path, title=title)

        async def asyncapi_viewer() -> _fastapi.responses.HTMLResponse:
            return _fastapi.responses.HTMLResponse(viewer_html)

        app.add_api_route(
            viewer_path,
            asyncapi_viewer,
            methods=["GET"],
            response_class=_fastapi.responses.HTMLResponse,
            include_in_schema=False,
        )


def mount_metrics(
    app: "FastAPI",
    metrics: Any,
    *,
    path: str = "/metrics",
) -> None:
    """Add `path` returning the Prometheus exposition snapshot from `metrics.export()`.

    `metrics` is any object with an `export() -> bytes` method (matching
    :class:`ruststream.metrics.PrometheusMetrics`). The endpoint sets the standard
    `text/plain; version=0.0.4; charset=utf-8` Content-Type so Prometheus scrapers
    accept it without configuration.
    """

    async def metrics_endpoint() -> _fastapi.responses.Response:
        body: bytes = metrics.export()
        return _fastapi.responses.Response(
            content=body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    app.add_api_route(
        path,
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
    )


__all__: tuple[str, ...] = ("mount_asyncapi", "mount_metrics")
