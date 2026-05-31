"""Raw bytes codec: no transformation, used when the payload is already opaque bytes."""

from typing import Any, ClassVar

from ruststream.codecs._base import Codec, CodecError


class RawBytesCodec(Codec):
    """Identity codec. `encode` accepts any bytes-like; `decode` returns bytes unchanged.

    This is the default codec when no broker- or subscriber-level codec is configured.
    """

    name: ClassVar[str] = "raw"
    content_type: ClassVar[str] = "application/octet-stream"

    def encode(self, value: Any) -> bytes:
        if isinstance(value, bytes):
            return value
        if isinstance(value, (bytearray, memoryview)):
            return bytes(value)
        type_name = type(value).__name__
        raise CodecError(
            f"RawBytesCodec.encode expects bytes-like (bytes/bytearray/memoryview), "
            f"got {type_name}",
        )

    def decode(self, raw: bytes) -> bytes:
        return raw


__all__: tuple[str, ...] = ("RawBytesCodec",)
