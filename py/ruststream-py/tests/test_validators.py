"""Pytest suite for `ruststream.validators`."""

import dataclasses
import importlib.util

import pytest
from ruststream.validators import (
    DataclassValidator,
    RawBytesValidator,
    Validator,
    ValidatorError,
    ValidatorRegistry,
)


def _is_installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


class TestRawBytesValidator:
    def test_supports_bytes_like_only(self) -> None:
        v = RawBytesValidator()
        assert v.supports(bytes)
        assert v.supports(bytearray)
        assert v.supports(memoryview)
        assert not v.supports(str)
        assert not v.supports(int)

    def test_decode_returns_bytes(self) -> None:
        v = RawBytesValidator()
        assert v.decode(b"hi", bytes) == b"hi"

    def test_decode_non_bytes_rejected(self) -> None:
        v = RawBytesValidator()
        with pytest.raises(ValidatorError, match="bytes-like"):
            v.decode("hi", bytes)

    def test_json_schema_is_none(self) -> None:
        assert RawBytesValidator().json_schema(bytes) is None


class TestDataclassValidator:
    def test_supports_dataclass_type(self) -> None:
        @dataclasses.dataclass
        class Order:
            id: int
            total: float

        v = DataclassValidator()
        assert v.supports(Order)
        assert not v.supports(dict)

    def test_decode_dict_into_dataclass(self) -> None:
        @dataclasses.dataclass
        class Order:
            id: int
            name: str

        v = DataclassValidator()
        result = v.decode({"id": 1, "name": "a"}, Order)
        assert result == Order(id=1, name="a")

    def test_decode_missing_required_field_raises(self) -> None:
        @dataclasses.dataclass
        class Order:
            id: int
            name: str

        with pytest.raises(ValidatorError, match="missing required field"):
            DataclassValidator().decode({"id": 1}, Order)

    def test_decode_handles_nested_dataclass(self) -> None:
        @dataclasses.dataclass
        class Address:
            city: str

        @dataclasses.dataclass
        class Person:
            name: str
            address: Address

        result = DataclassValidator().decode(
            {"name": "x", "address": {"city": "y"}},
            Person,
        )
        assert result == Person(name="x", address=Address(city="y"))

    def test_encode_dataclass_to_dict(self) -> None:
        @dataclasses.dataclass
        class Order:
            id: int
            name: str

        result = DataclassValidator().encode(Order(id=2, name="b"))
        assert result == {"id": 2, "name": "b"}

    def test_encode_non_dataclass_rejected(self) -> None:
        with pytest.raises(ValidatorError, match="dataclass instance"):
            DataclassValidator().encode({"id": 1})

    def test_json_schema_emits_required_and_properties(self) -> None:
        @dataclasses.dataclass
        class Order:
            id: int
            name: str
            note: str = ""

        schema = DataclassValidator().json_schema(Order)
        assert schema is not None
        assert schema["type"] == "object"
        assert schema["title"] == "Order"
        assert schema["properties"]["id"] == {"type": "integer"}
        assert schema["properties"]["name"] == {"type": "string"}
        assert sorted(schema["required"]) == ["id", "name"]


class TestValidatorRegistry:
    def test_builtins_register_by_default(self) -> None:
        @dataclasses.dataclass
        class Item:
            x: int

        registry = ValidatorRegistry()
        assert isinstance(registry.resolve(bytes), RawBytesValidator)
        assert isinstance(registry.resolve(Item), DataclassValidator)

    def test_unknown_type_returns_none(self) -> None:
        class Custom:
            pass

        # When no ecosystem adapters are installed the lookup ends in None.
        registry = ValidatorRegistry()
        # Lazy loading attempts will fail silently if extras are missing; we still expect
        # None when no validator claims the type.
        assert registry.resolve(Custom) is None

    def test_custom_validator_takes_precedence(self) -> None:
        class CustomMarker:
            pass

        class CustomValidator(Validator):
            name = "custom"

            def supports(self, target_type: type) -> bool:
                return target_type is CustomMarker

            def decode(self, data: object, target_type: type) -> object:
                return CustomMarker()

            def encode(self, value: object) -> object:
                return {}

            def json_schema(self, target_type: type) -> dict[str, object] | None:
                return None

        registry = ValidatorRegistry()
        registry.register(CustomValidator())
        assert isinstance(registry.resolve(CustomMarker), CustomValidator)


class TestPydanticValidator:
    @pytest.mark.skipif(not _is_installed("pydantic"), reason="pydantic not installed")
    def test_decode_pydantic_model(self) -> None:
        from pydantic import BaseModel
        from ruststream.validators._pydantic import PydanticValidator

        class Order(BaseModel):
            id: int
            name: str

        v = PydanticValidator()
        result = v.decode({"id": 7, "name": "ok"}, Order)
        assert result == Order(id=7, name="ok")

    @pytest.mark.skipif(not _is_installed("pydantic"), reason="pydantic not installed")
    def test_supports_basemodel_only(self) -> None:
        from pydantic import BaseModel
        from ruststream.validators._pydantic import PydanticValidator

        class M(BaseModel):
            x: int

        v = PydanticValidator()
        assert v.supports(M)
        assert not v.supports(dict)

    @pytest.mark.skipif(not _is_installed("pydantic"), reason="pydantic not installed")
    def test_json_schema_produces_object_schema(self) -> None:
        from pydantic import BaseModel
        from ruststream.validators._pydantic import PydanticValidator

        class M(BaseModel):
            x: int

        schema = PydanticValidator().json_schema(M)
        assert schema is not None
        assert schema["type"] == "object"


class TestMsgspecValidator:
    @pytest.mark.skipif(not _is_installed("msgspec"), reason="msgspec not installed")
    def test_decode_struct(self) -> None:
        import msgspec
        from ruststream.validators._msgspec import MsgspecValidator

        class Order(msgspec.Struct):
            id: int
            name: str

        v = MsgspecValidator()
        result = v.decode({"id": 7, "name": "ok"}, Order)
        assert result == Order(id=7, name="ok")

    @pytest.mark.skipif(not _is_installed("msgspec"), reason="msgspec not installed")
    def test_registry_picks_msgspec_for_struct(self) -> None:
        import msgspec

        class Order(msgspec.Struct):
            id: int

        registry = ValidatorRegistry()
        v = registry.resolve(Order)
        assert v is not None
        assert v.name == "msgspec"


class TestAttrsValidator:
    @pytest.mark.skipif(not _is_installed("attrs"), reason="attrs not installed")
    def test_decode_attrs_class(self) -> None:
        import attrs
        from ruststream.validators._attrs import AttrsValidator

        @attrs.define
        class Order:
            id: int
            name: str

        v = AttrsValidator()
        result = v.decode({"id": 7, "name": "ok"}, Order)
        assert result == Order(id=7, name="ok")
