"""Python-side delivery wrapper exposed to handlers as :class:`Message`.

A `Message` proxies the native PyO3 delivery and adds codec-aware decode helpers
(`value` property, `decode(target_type=None)` method) that route through the
subscriber-level codec and the validator registry. Wrapping happens once per delivery
in the broker dispatch loop, so handler signatures stay codec-agnostic:

    @broker.subscriber("orders", codec="json")
    async def handle(msg: Message) -> None:
        data = msg.value            # decoded via "json" codec, cached
        order = msg.decode(Order)   # codec + validator pipeline

Handlers with a typed first parameter (`async def handle(order: Order)`) still receive
the validated model directly; the wrapper is only used when the handler's first
positional parameter is annotated as :class:`Message` or left unannotated.
"""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ruststream.codecs import Codec
from ruststream.validators import resolve_validator

if TYPE_CHECKING:
    from ruststream._native import Message as _NativeMessage


_UNSET: Any = object()


class Message:
    """Codec-aware view onto one broker delivery.

    Users do not instantiate this class directly; brokers wrap each native delivery
    before invoking the handler. The wrapper holds a reference to the active codec
    so `.value` and `.decode()` work without the caller having to pass the codec in
    each time.
    """

    __slots__ = ("_codec", "_decoded", "_raw")

    def __init__(self, raw: "_NativeMessage", codec: Codec) -> None:
        self._raw = raw
        self._codec = codec
        self._decoded: Any = _UNSET

    @property
    def payload(self) -> bytes:
        """Raw delivery bytes as snapshotted by the native layer."""
        payload: bytes = self._raw.payload
        return payload

    @property
    def headers(self) -> Mapping[str, bytes]:
        """Delivery headers, keys lower-cased to match the broker contract."""
        headers: Mapping[str, bytes] = self._raw.headers
        return headers

    @property
    def value(self) -> Any:
        """Payload decoded once via the subscriber codec; subsequent reads are cached."""
        if self._decoded is _UNSET:
            self._decoded = self._codec.decode(bytes(self._raw.payload))
        return self._decoded

    def decode(self, target_type: type | None = None) -> Any:
        """Decode the payload and (optionally) route the result through a validator.

        Without `target_type`, returns the codec's decoded value (same as `.value`,
        but without caching the result on the message). With `target_type`, looks up
        the registered validator for that type and feeds the codec output through it,
        raising `TypeError` when no validator claims the type.
        """
        decoded = self._codec.decode(bytes(self._raw.payload))
        if target_type is None:
            return decoded
        validator = resolve_validator(target_type)
        if validator is None:
            type_name = getattr(target_type, "__name__", repr(target_type))
            raise TypeError(
                f"no validator registered for {type_name!r}; "
                "register one via `register_validator` or install the matching extra",
            )
        return validator.decode(decoded, target_type)

    async def ack(self) -> None:
        """Forward to the native delivery's ack."""
        await self._raw.ack()

    async def nack(self, requeue: bool = False) -> None:
        """Forward to the native delivery's nack."""
        await self._raw.nack(requeue)

    def __repr__(self) -> str:
        return f"Message(codec={self._codec.name!r}, payload_len={len(self._raw.payload)})"


__all__: tuple[str, ...] = ("Message",)
