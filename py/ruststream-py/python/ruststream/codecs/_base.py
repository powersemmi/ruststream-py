"""Codec protocol + shared error types."""

from typing import Any, ClassVar, Protocol, runtime_checkable


class CodecError(Exception):
    """Raised when a codec fails to encode or decode."""


class MissingDependencyError(CodecError):
    """A codec adapter is unavailable because its backing PyPI package is not installed.

    The message includes the exact `pip install` hint the user should run.
    """

    def __init__(self, codec_name: str, package: str, extra: str) -> None:
        super().__init__(
            f"codec {codec_name!r} requires the {package!r} package "
            f"(install via `pip install ruststream[{extra}]`)",
        )
        self.codec_name = codec_name
        self.package = package
        self.extra = extra


@runtime_checkable
class Codec(Protocol):
    """Wire-format codec used by `Broker` to encode publishes and decode deliveries.

    Implementations are stateless and cheap to construct. `name` identifies the codec in
    `@subscriber(..., codec="json")` lookups; `content_type` is the MIME-style identifier
    surfaced in generated schema metadata.
    """

    name: ClassVar[str]
    content_type: ClassVar[str]

    def encode(self, value: Any) -> bytes:
        """Serialize `value` into bytes for the wire."""
        ...

    def decode(self, raw: bytes) -> Any:
        """Deserialize `raw` bytes back into a Python value (typically a `dict` for
        structural codecs, raw `bytes` for `RawBytesCodec`)."""
        ...


__all__: tuple[str, ...] = ("Codec", "CodecError", "MissingDependencyError")
