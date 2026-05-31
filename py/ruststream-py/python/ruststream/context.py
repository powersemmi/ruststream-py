"""Three-scope key-value repository handed to lifespan, hooks, and handlers.

Scopes:
    - **Global**: written by the lifespan / `on_startup` hooks, visible everywhere for the
      lifetime of the app. Use for connection pools, feature flags, shared caches.
    - **Session**: written by each broker on its `_open` step, visible to handlers of
      that broker for the lifetime of the broker. Use for broker-specific runtime info
      (URL, server build, queue group). Cleared on broker `_close`.
    - **Local**: per-delivery values held in a `ContextVar`, populated by the dispatch
      loop with the message metadata (topic, headers, raw payload), and reset after the
      handler returns. Use for tracing / per-message logging.
"""

import contextlib
from collections.abc import AsyncIterator, Mapping
from contextvars import ContextVar
from typing import Any


class ContextRepo:
    """Three-scope key-value store shared between lifespan, hooks, and handlers."""

    _LOCAL_VAR: ContextVar[Mapping[str, Any] | None] = ContextVar(
        "_ruststream_context_local",
        default=None,
    )

    def __init__(self) -> None:
        self._globals: dict[str, Any] = {}
        self._sessions: dict[str, Any] = {}

    def set_global(self, key: str, value: Any) -> None:
        """Store `value` under `key` in the global scope. Overwrites existing entries."""
        self._globals[key] = value

    def get_global(self, key: str, default: Any = None) -> Any:
        """Return the global value under `key`, or `default` if absent."""
        return self._globals.get(key, default)

    def reset_global(self, key: str) -> None:
        """Remove the global value under `key`. No-op if absent."""
        self._globals.pop(key, None)

    def set_session(self, key: str, value: Any) -> None:
        """Store `value` under `key` in the session scope (one per broker)."""
        self._sessions[key] = value

    def get_session(self, key: str, default: Any = None) -> Any:
        """Return the session value under `key`, or `default` if absent."""
        return self._sessions.get(key, default)

    def reset_session(self, key: str) -> None:
        """Remove the session value under `key`. No-op if absent."""
        self._sessions.pop(key, None)

    def clear_session(self) -> None:
        """Remove every session entry. Called by `Broker.stop` automatically."""
        self._sessions.clear()

    def get_local(self, key: str, default: Any = None) -> Any:
        """Return the local value under `key`, or `default` if no local scope is active."""
        bag = self._LOCAL_VAR.get()
        if bag is None:
            return default
        return bag.get(key, default)

    def local_keys(self) -> tuple[str, ...]:
        """Return the set of currently-active local keys (empty when no scope is active)."""
        bag = self._LOCAL_VAR.get()
        return tuple(bag.keys()) if bag is not None else ()

    @contextlib.asynccontextmanager
    async def enter_local(self, **values: Any) -> AsyncIterator[None]:
        """Push `values` onto the local scope for the duration of the `async with` block.

        Reset to the previous state on exit, including when an exception propagates.
        """
        merged: dict[str, Any] = {**(self._LOCAL_VAR.get() or {}), **values}
        token = self._LOCAL_VAR.set(merged)
        try:
            yield
        finally:
            self._LOCAL_VAR.reset(token)

    def __contains__(self, key: str) -> bool:
        return key in self._globals or key in self._sessions

    def __repr__(self) -> str:
        return (
            f"ContextRepo(globals={sorted(self._globals)}, "
            f"sessions={sorted(self._sessions)}, locals={list(self.local_keys())})"
        )


__all__: tuple[str, ...] = ("ContextRepo",)
