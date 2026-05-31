"""`orjson`-backed JSON codec. Requires `pip install ruststream[orjson]`."""

from typing import Any, ClassVar

from ruststream.codecs._base import Codec, CodecError, MissingDependencyError


class OrjsonCodec(Codec):
    """JSON codec backed by `orjson`. Wire-compatible with `JsonCodec`, faster on both
    encode and decode.

    Constructing the codec imports `orjson`; a missing package surfaces as
    `MissingDependencyError`.
    """

    name: ClassVar[str] = "orjson"
    content_type: ClassVar[str] = "application/json"

    def __init__(self) -> None:
        try:
            import orjson
        except ImportError as exc:
            raise MissingDependencyError("orjson", "orjson", "orjson") from exc
        self._orjson = orjson

    def encode(self, value: Any) -> bytes:
        try:
            return bytes(self._orjson.dumps(value))
        except (TypeError, ValueError) as exc:
            raise CodecError(f"orjson encode failed: {exc}") from exc

    def decode(self, raw: bytes) -> Any:
        try:
            return self._orjson.loads(raw)
        except (ValueError, self._orjson.JSONDecodeError) as exc:
            raise CodecError(f"orjson decode failed: {exc}") from exc


def register(registry: Any) -> None:
    """Entry point used by the lazy-loading registry. Constructs and registers the codec.

    Raises `MissingDependencyError` if the `orjson` PyPI package is not installed.
    """
    registry.register(OrjsonCodec())


__all__: tuple[str, ...] = ("OrjsonCodec", "register")
