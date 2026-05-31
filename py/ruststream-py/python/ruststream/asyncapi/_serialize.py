"""Serialize AsyncAPI spec dicts to JSON and YAML strings."""

import json
from typing import Any

from ruststream.asyncapi._errors import MissingDependencyError


def to_json(spec: dict[str, Any], *, indent: int | None = 2) -> str:
    """Serialize `spec` to a JSON string.

    `indent=None` produces compact output suitable for over-the-wire transport;
    the default `indent=2` yields a human-readable form.
    """
    return json.dumps(spec, indent=indent, ensure_ascii=False, sort_keys=False)


def to_yaml(spec: dict[str, Any]) -> str:
    """Serialize `spec` to YAML. Requires `pip install ruststream[asyncapi]`.

    Lazily imports PyYAML so the base install stays stdlib-only.
    """
    try:
        import yaml
    except ImportError as exc:
        raise MissingDependencyError("PyYAML", "asyncapi") from exc
    dumped: str = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)
    return dumped


__all__: tuple[str, ...] = ("to_json", "to_yaml")
