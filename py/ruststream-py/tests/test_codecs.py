"""Pytest suite for `ruststream.codecs`: protocol, builtins, lazy adapters, registry."""

import importlib.util

import pytest
from ruststream.codecs import (
    DEFAULT_CODEC,
    Codec,
    CodecError,
    CodecRegistry,
    JsonCodec,
    MissingDependencyError,
    RawBytesCodec,
    get_codec,
    register_codec,
    resolve_codec,
)


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


class TestRawBytesCodec:
    def test_round_trip_returns_input_bytes(self) -> None:
        codec = RawBytesCodec()
        assert codec.encode(b"hi") == b"hi"
        assert codec.decode(b"hi") == b"hi"

    def test_encode_accepts_bytes_like(self) -> None:
        codec = RawBytesCodec()
        assert codec.encode(bytearray(b"ba")) == b"ba"
        assert codec.encode(memoryview(b"mv")) == b"mv"

    def test_encode_rejects_non_bytes_like(self) -> None:
        codec = RawBytesCodec()
        with pytest.raises(CodecError, match="bytes-like"):
            codec.encode("string")

    def test_default_codec_is_raw(self) -> None:
        assert isinstance(DEFAULT_CODEC, RawBytesCodec)


class TestJsonCodec:
    def test_round_trip_dict(self) -> None:
        codec = JsonCodec()
        encoded = codec.encode({"id": 1, "name": "test"})
        assert codec.decode(encoded) == {"id": 1, "name": "test"}

    def test_encode_unicode_unescaped(self) -> None:
        codec = JsonCodec()
        assert codec.encode({"name": "Über"}) == b'{"name":"\xc3\x9cber"}'

    def test_decode_malformed_raises_codec_error(self) -> None:
        codec = JsonCodec()
        with pytest.raises(CodecError, match="json decode"):
            codec.decode(b"{ not json")

    def test_encode_non_serializable_raises(self) -> None:
        codec = JsonCodec()
        with pytest.raises(CodecError, match="json encode"):
            codec.encode({1, 2, 3})

    def test_content_type_is_application_json(self) -> None:
        assert JsonCodec.content_type == "application/json"


class TestCodecRegistry:
    def test_builtins_registered_by_default(self) -> None:
        registry = CodecRegistry()
        assert isinstance(registry.get("raw"), RawBytesCodec)
        assert isinstance(registry.get("json"), JsonCodec)

    def test_unknown_codec_raises(self) -> None:
        registry = CodecRegistry()
        with pytest.raises(CodecError, match="unknown codec"):
            registry.get("not-a-codec")

    def test_register_custom_codec(self) -> None:
        class CustomCodec(Codec):
            name = "custom"
            content_type = "application/x-custom"

            def encode(self, value: object) -> bytes:
                return repr(value).encode()

            def decode(self, raw: bytes) -> object:
                return raw.decode()

        registry = CodecRegistry()
        registry.register(CustomCodec())
        assert registry.get("custom").encode(42) == b"42"

    def test_resolve_codec_passes_through_instance(self) -> None:
        codec = JsonCodec()
        assert resolve_codec(codec) is codec

    def test_resolve_codec_looks_up_by_name(self) -> None:
        assert isinstance(resolve_codec("json"), JsonCodec)

    def test_resolve_codec_none_returns_default(self) -> None:
        assert resolve_codec(None) is DEFAULT_CODEC

    def test_resolve_codec_none_with_fallback(self) -> None:
        json_codec = JsonCodec()
        assert resolve_codec(None, fallback=json_codec) is json_codec

    def test_global_register_visible_to_get_codec(self) -> None:
        class MarkerCodec(Codec):
            name = "marker-test"
            content_type = "application/x-marker"

            def encode(self, value: object) -> bytes:
                return b""

            def decode(self, raw: bytes) -> None:
                return None

        register_codec(MarkerCodec())
        assert isinstance(get_codec("marker-test"), MarkerCodec)


class TestLazyAdapters:
    @pytest.mark.skipif(not _is_installed("orjson"), reason="orjson not installed")
    def test_orjson_lazy_loads_and_round_trips(self) -> None:
        from ruststream.codecs._orjson import OrjsonCodec

        codec = OrjsonCodec()
        assert codec.name == "orjson"
        assert codec.content_type == "application/json"
        encoded = codec.encode({"k": "v"})
        assert codec.decode(encoded) == {"k": "v"}

    @pytest.mark.skipif(not _is_installed("orjson"), reason="orjson not installed")
    def test_registry_lazy_loads_orjson_on_demand(self) -> None:
        registry = CodecRegistry()
        codec = registry.get("orjson")
        assert codec.name == "orjson"

    @pytest.mark.skipif(_is_installed("orjson"), reason="orjson is installed")
    def test_orjson_missing_raises_dependency_error(self) -> None:
        registry = CodecRegistry()
        with pytest.raises(MissingDependencyError) as excinfo:
            registry.get("orjson")
        assert excinfo.value.extra == "orjson"
        assert "pip install ruststream[orjson]" in str(excinfo.value)

    @pytest.mark.skipif(not _is_installed("msgpack"), reason="msgpack not installed")
    def test_msgpack_round_trip(self) -> None:
        registry = CodecRegistry()
        codec = registry.get("msgpack")
        encoded = codec.encode([1, 2, 3])
        assert codec.decode(encoded) == [1, 2, 3]

    @pytest.mark.skipif(not _is_installed("cbor2"), reason="cbor2 not installed")
    def test_cbor_round_trip(self) -> None:
        registry = CodecRegistry()
        codec = registry.get("cbor")
        encoded = codec.encode({"k": 1})
        assert codec.decode(encoded) == {"k": 1}
