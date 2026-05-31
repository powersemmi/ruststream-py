"""Pydantic v2 validator. Requires `pip install ruststream[pydantic]`."""

from typing import TYPE_CHECKING, Any, ClassVar, cast

from ruststream.validators._base import MissingDependencyError, Validator, ValidatorError

if TYPE_CHECKING:
    import pydantic as _pydantic_module


class PydanticValidator(Validator):
    """Validator for Pydantic v2 `BaseModel` subclasses.

    Uses `Model.model_validate` for decode, `instance.model_dump(mode="json")` for encode,
    and `Model.model_json_schema()` for the JSON Schema export.
    """

    name: ClassVar[str] = "pydantic"

    def __init__(self) -> None:
        try:
            import pydantic
        except ImportError as exc:
            raise MissingDependencyError("pydantic", "pydantic", "pydantic") from exc
        self._pydantic = pydantic

    def supports(self, target_type: type) -> bool:
        return isinstance(target_type, type) and issubclass(
            target_type,
            self._pydantic.BaseModel,
        )

    def decode(self, data: Any, target_type: type) -> Any:
        model_cls = cast("type[_pydantic_module.BaseModel]", target_type)
        try:
            return model_cls.model_validate(data)
        except self._pydantic.ValidationError as exc:
            raise ValidatorError(
                f"pydantic validation failed for {target_type.__name__}: {exc}",
            ) from exc

    def encode(self, value: Any) -> Any:
        if not isinstance(value, self._pydantic.BaseModel):
            type_name = type(value).__name__
            raise ValidatorError(
                f"PydanticValidator.encode expects a BaseModel instance, got {type_name}",
            )
        dumped: Any = value.model_dump(mode="json")
        return dumped

    def json_schema(self, target_type: type) -> dict[str, Any] | None:
        if not self.supports(target_type):
            return None
        model_cls = cast("type[_pydantic_module.BaseModel]", target_type)
        schema: dict[str, Any] = model_cls.model_json_schema()
        return schema


def build() -> Validator:
    """Construct and return a `PydanticValidator`."""
    return PydanticValidator()


__all__: tuple[str, ...] = ("PydanticValidator", "build")
