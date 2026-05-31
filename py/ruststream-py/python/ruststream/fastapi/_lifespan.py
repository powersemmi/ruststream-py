"""FastAPI lifespan factory that runs a RustStream broker alongside the ASGI app.

`lifespan_for(target)` returns an async context manager usable as the `lifespan=`
argument to `fastapi.FastAPI(...)`. It starts the broker(s) when the ASGI app
starts and stops them when it shuts down, so one ASGI process serves HTTP and
broker traffic without separate management code.

Example::

    from fastapi import FastAPI
    from ruststream import MemoryBroker
    from ruststream.fastapi import lifespan_for

    broker = MemoryBroker(codec="json")
    app = FastAPI(lifespan=lifespan_for(broker))
"""

import contextlib
from collections.abc import AsyncGenerator, Callable
from typing import Any

from ruststream._broker import Broker
from ruststream.app import RustStream
from ruststream.fastapi._errors import MissingDependencyError

try:
    import fastapi as _fastapi  # noqa: F401
except ImportError as exc:
    raise MissingDependencyError() from exc


LifespanCallable = Callable[[Any], contextlib.AbstractAsyncContextManager[None]]


def _wrap(target: Broker | RustStream) -> RustStream:
    if isinstance(target, RustStream):
        return target
    return RustStream(target, title=getattr(target, "title", "RustStream"))


def lifespan_for(target: Broker | RustStream) -> LifespanCallable:
    """Return a FastAPI lifespan factory that drives `target`'s lifecycle.

    The returned async context manager yields after the broker(s) reached the
    `after_startup` phase (subscriptions are live), so request handlers running
    inside FastAPI can publish from the moment `lifespan` yields. On exit the
    broker stops cleanly before FastAPI tears the ASGI server down.
    """
    app = _wrap(target)

    @contextlib.asynccontextmanager
    async def lifespan(_fastapi_app: Any) -> AsyncGenerator[None, None]:
        async with app:
            yield

    return lifespan


__all__: tuple[str, ...] = ("LifespanCallable", "lifespan_for")
