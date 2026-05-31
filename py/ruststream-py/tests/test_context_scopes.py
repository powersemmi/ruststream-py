"""Pytest suite for the three-scope `ContextRepo` (global / session / local)."""

import asyncio
import dataclasses

import pytest
from ruststream import ContextRepo, MemoryBroker, Message, RustStream

pytestmark = pytest.mark.asyncio


@dataclasses.dataclass
class Order:
    id: int
    name: str


class TestGlobalScope:
    def test_set_and_get_global(self) -> None:
        ctx = ContextRepo()
        ctx.set_global("flag", "on")
        assert ctx.get_global("flag") == "on"

    def test_get_global_default(self) -> None:
        ctx = ContextRepo()
        assert ctx.get_global("missing", default=42) == 42

    def test_reset_global_removes_key(self) -> None:
        ctx = ContextRepo()
        ctx.set_global("k", 1)
        ctx.reset_global("k")
        assert ctx.get_global("k") is None


class TestSessionScope:
    def test_set_and_get_session(self) -> None:
        ctx = ContextRepo()
        ctx.set_session("broker", "memory")
        assert ctx.get_session("broker") == "memory"

    def test_clear_session_drops_everything(self) -> None:
        ctx = ContextRepo()
        ctx.set_session("a", 1)
        ctx.set_session("b", 2)
        ctx.clear_session()
        assert ctx.get_session("a") is None
        assert ctx.get_session("b") is None

    def test_session_does_not_leak_into_global(self) -> None:
        ctx = ContextRepo()
        ctx.set_session("k", "v")
        assert ctx.get_global("k") is None


class TestLocalScope:
    async def test_local_visible_inside_block(self) -> None:
        ctx = ContextRepo()
        async with ctx.enter_local(topic="orders", attempt=1):
            assert ctx.get_local("topic") == "orders"
            assert ctx.get_local("attempt") == 1

    async def test_local_reset_after_exit(self) -> None:
        ctx = ContextRepo()
        async with ctx.enter_local(topic="orders"):
            assert ctx.get_local("topic") == "orders"
        assert ctx.get_local("topic") is None

    async def test_nested_locals_stack(self) -> None:
        ctx = ContextRepo()
        async with ctx.enter_local(a=1):
            async with ctx.enter_local(b=2):
                assert ctx.get_local("a") == 1
                assert ctx.get_local("b") == 2
            assert ctx.get_local("a") == 1
            assert ctx.get_local("b") is None

    async def test_local_reset_on_exception(self) -> None:
        ctx = ContextRepo()
        with pytest.raises(RuntimeError):
            async with ctx.enter_local(topic="x"):
                raise RuntimeError("boom")
        assert ctx.get_local("topic") is None

    async def test_local_default_on_missing_scope(self) -> None:
        ctx = ContextRepo()
        assert ctx.get_local("missing", default="fallback") == "fallback"


class TestLocalScopeInDispatch:
    async def test_handler_sees_topic_in_local_scope(
        self,
        memory_broker: MemoryBroker,
    ) -> None:
        captured: list[str] = []
        seen = asyncio.Event()

        @memory_broker.subscriber("orders")
        async def handle(msg: Message, ctx: ContextRepo) -> None:
            captured.append(ctx.get_local("topic") or "missing")
            seen.set()

        async with RustStream(memory_broker):
            await memory_broker.publish("orders", b"x")
            await asyncio.wait_for(seen.wait(), timeout=1.0)

        assert captured == ["orders"]

    async def test_handler_sees_raw_payload_in_local(
        self,
        memory_broker_json: MemoryBroker,
    ) -> None:
        captured: list[bytes] = []
        seen = asyncio.Event()

        @memory_broker_json.subscriber("orders")
        async def handle(order: Order, ctx: ContextRepo) -> None:
            captured.append(ctx.get_local("raw_payload"))
            seen.set()

        async with RustStream(memory_broker_json):
            await memory_broker_json.publish("orders", {"id": 1, "name": "n"})
            await asyncio.wait_for(seen.wait(), timeout=1.0)

        assert captured == [b'{"id":1,"name":"n"}']

    async def test_local_cleared_between_handlers(self, memory_broker: MemoryBroker) -> None:
        outside_topic: list[str | None] = []
        seen = asyncio.Event()

        @memory_broker.subscriber("orders")
        async def handle(msg: Message, ctx: ContextRepo) -> None:
            del msg
            del ctx
            seen.set()

        async with RustStream(memory_broker):
            await memory_broker.publish("orders", b"x")
            await asyncio.wait_for(seen.wait(), timeout=1.0)
            # After handler returns the local scope must be empty for the test task.
            outside_topic.append(memory_broker._context.get_local("topic"))

        assert outside_topic == [None]


class TestSessionFromBroker:
    async def test_memory_broker_populates_session(self, memory_broker: MemoryBroker) -> None:
        captured: list[str] = []
        seen = asyncio.Event()

        @memory_broker.subscriber("orders")
        async def handle(msg: Message, ctx: ContextRepo) -> None:
            del msg
            captured.append(ctx.get_session("broker") or "unset")
            seen.set()

        async with RustStream(memory_broker):
            await memory_broker.publish("orders", b"x")
            await asyncio.wait_for(seen.wait(), timeout=1.0)

        assert captured == ["memory"]

    async def test_session_cleared_on_broker_stop(self, memory_broker: MemoryBroker) -> None:
        async with RustStream(memory_broker):
            await asyncio.sleep(0)
            assert memory_broker._context.get_session("broker") == "memory"

        # After RustStream context exits, broker has been stopped → session cleared.
        assert memory_broker._context.get_session("broker") is None
