"""Pluggable wire-format codecs for RustStream.

A `Codec` turns Python values into bytes for the wire and back. Codecs are looked up by
name on the broker (`Broker(codec="json")`) or per subscriber/publisher
(`@broker.publisher("topic", codec="orjson")`).

Built-in codecs (no extras required):
    - `raw` (`RawBytesCodec`): identity, `bytes <-> bytes`.
    - `json` (`JsonCodec`): standard-library `json`.

Ecosystem adapters (install the matching extra):
    - `orjson` (`pip install ruststream[orjson]`): wraps the `orjson` package.
    - `msgpack` (`pip install ruststream[msgpack]`): wraps the `msgpack` package.
    - `cbor` (`pip install ruststream[cbor]`): wraps the `cbor2` package.

Adapters import their backing package lazily on first instantiation; a missing package
surfaces as `MissingDependencyError` with the exact install command.

External codecs register through the `ruststream.codecs` entry-point group and load on
first lookup by name.
"""

from ruststream.codecs._base import Codec, CodecError, MissingDependencyError
from ruststream.codecs._json import JsonCodec
from ruststream.codecs._raw import RawBytesCodec
from ruststream.codecs._registry import (
    DEFAULT_CODEC,
    CodecRegistry,
    get_codec,
    register_codec,
    resolve_codec,
)

__all__: tuple[str, ...] = (
    "DEFAULT_CODEC",
    "Codec",
    "CodecError",
    "CodecRegistry",
    "JsonCodec",
    "MissingDependencyError",
    "RawBytesCodec",
    "get_codec",
    "register_codec",
    "resolve_codec",
)
