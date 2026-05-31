"""`cbor2`-backed codec. Requires `pip install ruststream[cbor]`."""

from typing import Any, ClassVar

from ruststream.codecs._base import Codec, CodecError, MissingDependencyError


class CborCodec(Codec):
    """CBOR codec backed by the `cbor2` package."""

    name: ClassVar[str] = "cbor"
    content_type: ClassVar[str] = "application/cbor"

    def __init__(self) -> None:
        try:
            import cbor2
        except ImportError as exc:
            raise MissingDependencyError("cbor", "cbor2", "cbor") from exc
        self._cbor2 = cbor2

    def encode(self, value: Any) -> bytes:
        try:
            return bytes(self._cbor2.dumps(value))
        except (TypeError, ValueError, self._cbor2.CBOREncodeError) as exc:
            raise CodecError(f"cbor encode failed: {exc}") from exc

    def decode(self, raw: bytes) -> Any:
        try:
            return self._cbor2.loads(raw)
        except (ValueError, self._cbor2.CBORDecodeError) as exc:
            raise CodecError(f"cbor decode failed: {exc}") from exc


def register(registry: Any) -> None:
    registry.register(CborCodec())


__all__: tuple[str, ...] = ("CborCodec", "register")
