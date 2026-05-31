"""`msgpack`-backed codec. Requires `pip install ruststream[msgpack]`."""

from typing import Any, ClassVar

from ruststream.codecs._base import Codec, CodecError, MissingDependencyError


class MsgpackCodec(Codec):
    """MessagePack codec backed by the `msgpack` package."""

    name: ClassVar[str] = "msgpack"
    content_type: ClassVar[str] = "application/msgpack"

    def __init__(self) -> None:
        try:
            import msgpack
        except ImportError as exc:
            raise MissingDependencyError("msgpack", "msgpack", "msgpack") from exc
        self._msgpack = msgpack

    def encode(self, value: Any) -> bytes:
        try:
            packed = self._msgpack.packb(value, use_bin_type=True)
        except (TypeError, ValueError, self._msgpack.PackException) as exc:
            raise CodecError(f"msgpack encode failed: {exc}") from exc
        if packed is None:
            raise CodecError("msgpack.packb returned None")
        return bytes(packed)

    def decode(self, raw: bytes) -> Any:
        try:
            return self._msgpack.unpackb(raw, raw=False)
        except (ValueError, self._msgpack.UnpackException) as exc:
            raise CodecError(f"msgpack decode failed: {exc}") from exc


def register(registry: Any) -> None:
    registry.register(MsgpackCodec())


__all__: tuple[str, ...] = ("MsgpackCodec", "register")
