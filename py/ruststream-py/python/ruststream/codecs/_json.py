"""JSON codec backed by the standard-library `json` module."""

import json
from typing import Any, ClassVar

from ruststream.codecs._base import Codec, CodecError


class JsonCodec(Codec):
    """JSON codec using the standard library `json` module.

    Available without extras. For higher throughput install `ruststream[orjson]` and use
    `codec="orjson"` instead; the wire format is identical (UTF-8 JSON).
    """

    name: ClassVar[str] = "json"
    content_type: ClassVar[str] = "application/json"

    def encode(self, value: Any) -> bytes:
        try:
            return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CodecError(f"json encode failed: {exc}") from exc

    def decode(self, raw: bytes) -> Any:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CodecError(f"json decode failed: {exc}") from exc


__all__: tuple[str, ...] = ("JsonCodec",)
