"""Codec registry: name -> Codec instance, with lazy loading of ecosystem adapters."""

import logging
from importlib.metadata import entry_points
from typing import Final

from ruststream.codecs._base import Codec, CodecError
from ruststream.codecs._json import JsonCodec
from ruststream.codecs._raw import RawBytesCodec

logger = logging.getLogger(__name__)

DEFAULT_CODEC: Final[Codec] = RawBytesCodec()


class CodecRegistry:
    """Registry mapping a short name (`"raw"`, `"json"`, `"orjson"`) to a `Codec` instance.

    Builtins (`raw`, `json`) register on construction. Ecosystem adapters (`orjson`,
    `msgpack`, `cbor`) load lazily on first lookup: the registry imports the wrapper
    module, which itself does the `import <ecosystem_pkg>` lazily and raises
    `MissingDependencyError` if the underlying package is missing.

    External codecs register via the `ruststream.codecs` entry-point group; they are loaded
    on the first `get` / `resolve` call.
    """

    _LAZY_BUILTINS: Final[dict[str, str]] = {
        "orjson": "ruststream.codecs._orjson",
        "msgpack": "ruststream.codecs._msgpack",
        "cbor": "ruststream.codecs._cbor",
    }

    def __init__(self) -> None:
        self._codecs: dict[str, Codec] = {}
        self._entry_points_loaded: bool = False
        self.register(RawBytesCodec())
        self.register(JsonCodec())

    def register(self, codec: Codec) -> None:
        """Register `codec` under its `name` attribute. Replaces any existing entry."""
        name = codec.name
        if not name:
            raise CodecError("codec.name must be non-empty")
        self._codecs[name] = codec

    def get(self, name: str) -> Codec:
        """Return the codec registered under `name`, loading lazy adapters and external
        entry-points on first lookup.

        Raises:
            CodecError: if no codec is registered (and no lazy adapter / entry-point
                provides one).
            MissingDependencyError: if the codec exists but its backing PyPI package is
                not installed.
        """
        cached = self._codecs.get(name)
        if cached is not None:
            return cached
        if name in self._LAZY_BUILTINS:
            self._load_lazy_builtin(name)
            return self._codecs[name]
        if not self._entry_points_loaded:
            self._load_entry_points()
            cached = self._codecs.get(name)
            if cached is not None:
                return cached
        raise CodecError(
            f"unknown codec {name!r}; registered: {sorted(self._codecs)}",
        )

    def _load_lazy_builtin(self, name: str) -> None:
        module_path = self._LAZY_BUILTINS[name]
        import importlib

        module = importlib.import_module(module_path)
        # Each lazy-loaded module exposes a `register(registry)` function that instantiates
        # the codec (which is where the ImportError for the missing ecosystem package
        # surfaces) and registers it.
        module.register(self)

    def _load_entry_points(self) -> None:
        self._entry_points_loaded = True
        try:
            eps = list(entry_points(group="ruststream.codecs"))
        except TypeError:
            # Older Python entry_points returned a dict; we target 3.11+ so this is
            # primarily defensive.
            eps = []
        for ep in eps:
            try:
                factory = ep.load()
            except ImportError:
                logger.debug("ruststream.codecs entry-point %s failed to import", ep.name)
                continue
            try:
                self.register(factory())
            except Exception:
                logger.exception(
                    "ruststream.codecs entry-point %s factory raised",
                    ep.name,
                )


_global_registry = CodecRegistry()


def register_codec(codec: Codec) -> None:
    """Register `codec` in the process-global registry."""
    _global_registry.register(codec)


def get_codec(name: str) -> Codec:
    """Return the codec registered under `name` from the global registry."""
    return _global_registry.get(name)


def resolve_codec(codec: Codec | str | None, fallback: Codec | None = None) -> Codec:
    """Coerce a user-supplied codec value into a `Codec` instance.

    Args:
        codec: A `Codec` instance, a name to look up, or `None` to fall back.
        fallback: Codec to use when `codec is None`. Defaults to `DEFAULT_CODEC`
            (`RawBytesCodec`) at module import time.
    """
    if codec is None:
        return fallback if fallback is not None else DEFAULT_CODEC
    if isinstance(codec, str):
        return get_codec(codec)
    return codec


__all__: tuple[str, ...] = (
    "DEFAULT_CODEC",
    "CodecRegistry",
    "get_codec",
    "register_codec",
    "resolve_codec",
)
