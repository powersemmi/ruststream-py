"""FastAPI integration: DI adapter, lifespan, asyncapi + metrics mounts."""

import asyncio
import importlib.util
import json
from collections.abc import Awaitable, Callable
from typing import Annotated

import pytest

pytest.importorskip("fastapi")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from ruststream import ContextRepo, MemoryBroker, Message, RustStream
from ruststream.di import DI, DIError
from ruststream.fastapi import (
    Context,
    FastAPIDI,
    MissingDependencyError,
    lifespan_for,
    mount_asyncapi,
    mount_metrics,
)

pytestmark = pytest.mark.asyncio


def _has_prometheus() -> bool:
    return importlib.util.find_spec("prometheus_client") is not None


@pytest.fixture
def fastapi_broker(memory_broker_factory: Callable[..., MemoryBroker]) -> MemoryBroker:
    """`MemoryBroker` whose DI is a fresh `FastAPIDI`."""
    return memory_broker_factory(di=FastAPIDI())


def _get_token() -> str:
    return "fa-tok"


async def _get_token_async() -> str:
    await asyncio.sleep(0)
    return "fa-tok-async"


def _get_prefix() -> str:
    return "fa"


def _get_full(prefix: str = Depends(_get_prefix)) -> str:
    return f"{prefix}/full"


@pytest.mark.parametrize(
    ("depender", "expected"),
    [
        pytest.param(_get_token, "fa-tok", id="sync"),
        pytest.param(_get_token_async, "fa-tok-async", id="async"),
        pytest.param(_get_full, "fa/full", id="nested"),
    ],
)
async def test_fastapi_di_resolves_default_form(
    fastapi_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
    depender: Callable[..., str] | Callable[..., Awaitable[str]],
    expected: str,
) -> None:
    captured: list[str] = []
    seen = asyncio.Event()

    @fastapi_broker.subscriber("t")
    async def handle(msg: Message, value: str = Depends(depender)) -> None:
        captured.append(value)
        seen.set()

    async with RustStream(fastapi_broker):
        await fastapi_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [expected]


async def test_fastapi_di_resolves_annotated_form(
    fastapi_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    captured: list[str] = []
    seen = asyncio.Event()

    @fastapi_broker.subscriber("t")
    async def handle(msg: Message, token: Annotated[str, Depends(_get_token)]) -> None:
        captured.append(token)
        seen.set()

    async with RustStream(fastapi_broker):
        await fastapi_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == ["fa-tok"]


async def test_fastapi_di_resolves_context_via_marker(
    fastapi_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    captured: list[bool] = []
    seen = asyncio.Event()

    @fastapi_broker.subscriber("t")
    async def handle(msg: Message, ctx: ContextRepo = Depends(Context)) -> None:
        captured.append(ctx.get_global("flag") == "lit")
        seen.set()

    app = RustStream(fastapi_broker)
    app.context.set_global("flag", "lit")

    async with app:
        await fastapi_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == [True]


async def test_fastapi_di_rejects_bare_context_repo(fastapi_broker: MemoryBroker) -> None:
    @fastapi_broker.subscriber("t")
    async def handle(msg: Message, ctx: ContextRepo) -> None:
        pass

    with pytest.raises(TypeError, match="cannot resolve parameter 'ctx'"):
        async with RustStream(fastapi_broker):
            await asyncio.sleep(0)


async def test_fastapi_di_resolve_without_marker_raises_dierror() -> None:
    di = FastAPIDI()
    with pytest.raises(DIError, match="FastAPIDI cannot resolve"):
        await di.resolve(int, context=ContextRepo())


async def test_fastapi_di_caches_shared_sub_dependency_within_one_depender(
    fastapi_broker: MemoryBroker,
    wait_event: Callable[..., Awaitable[None]],
) -> None:
    """When two parameters of a depender share a sub-dependency, it resolves once."""
    calls = 0

    def shared() -> str:
        nonlocal calls
        calls += 1
        return "v"

    def combine(a: str = Depends(shared), b: str = Depends(shared)) -> str:
        return f"{a}{b}"

    captured: list[str] = []
    seen = asyncio.Event()

    @fastapi_broker.subscriber("t")
    async def handle(msg: Message, result: str = Depends(combine)) -> None:
        captured.append(result)
        seen.set()

    async with RustStream(fastapi_broker):
        await fastapi_broker.publish("t", b"x")
        await wait_event(seen)

    assert captured == ["vv"]
    assert calls == 1


def test_fastapi_di_protocol_compliance() -> None:
    assert isinstance(FastAPIDI(), DI)


def test_context_sentinel_raises_when_called_directly() -> None:
    with pytest.raises(RuntimeError, match="FastAPIDI sentinel"):
        Context()


async def test_lifespan_for_drives_broker_alongside_fastapi() -> None:
    broker = MemoryBroker(codec="json")
    received: list[bytes] = []
    seen = asyncio.Event()

    @broker.subscriber("orders")
    async def handle(msg: Message) -> None:
        received.append(bytes(msg.payload))
        seen.set()

    app = FastAPI(lifespan=lifespan_for(broker))

    @app.get("/publish")
    async def publish_endpoint() -> dict[str, str]:
        await broker.publish("orders", {"id": 1})
        await asyncio.wait_for(seen.wait(), timeout=1.0)
        return {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/publish")
        assert response.status_code == 200

    assert len(received) == 1


def test_mount_asyncapi_exposes_spec_and_viewer_routes() -> None:
    broker = MemoryBroker()

    @broker.subscriber("orders")
    async def handle(_msg: Message) -> None:
        pass

    app = FastAPI()
    mount_asyncapi(app, broker, title="t", version="9.9.9")

    with TestClient(app) as client:
        spec_resp = client.get("/asyncapi.json")
        assert spec_resp.status_code == 200
        spec = json.loads(spec_resp.content)
        assert spec["info"] == {"title": "t", "version": "9.9.9"}
        assert spec["channels"]["orders"]["address"] == "orders"

        viewer_resp = client.get("/docs/asyncapi")
        assert viewer_resp.status_code == 200
        assert "AsyncApiStandalone.render" in viewer_resp.text


def test_mount_asyncapi_can_skip_viewer() -> None:
    broker = MemoryBroker()
    app = FastAPI()
    mount_asyncapi(app, broker, viewer_path=None)
    with TestClient(app) as client:
        assert client.get("/asyncapi.json").status_code == 200
        assert client.get("/docs/asyncapi").status_code == 404


@pytest.mark.skipif(not _has_prometheus(), reason="prometheus_client not installed")
def test_mount_metrics_serves_prometheus_snapshot() -> None:
    from ruststream.metrics import PrometheusMetrics

    metrics = PrometheusMetrics()
    metrics.record_received("orders")
    app = FastAPI()
    mount_metrics(app, metrics)
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "messages_received_total" in resp.text


def test_missing_dependency_error_when_fastapi_uninstalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "fastapi", None)
    monkeypatch.delitem(sys.modules, "ruststream.fastapi._di", raising=False)
    import importlib

    with pytest.raises(MissingDependencyError):
        importlib.import_module("ruststream.fastapi._di")
