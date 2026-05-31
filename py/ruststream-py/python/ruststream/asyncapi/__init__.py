"""AsyncAPI 3.0 spec generation from broker/router metadata.

`build_spec(target)` walks the broker's registrations and any handler-attached
`@publisher(topic)` markers, producing a dict that conforms to the AsyncAPI 3.0
schema. Payload schemas are pulled through the registered :class:`Validator` (its
optional `json_schema(target_type)` hook); types with no available schema show up
in the spec without a payload reference. `to_json` / `to_yaml` serialize the dict;
`render_viewer_html` returns a one-file HTML page that loads the AsyncAPI React
viewer from a CDN and points it at the spec URL.

Example::

    from ruststream.asyncapi import build_spec, to_json

    spec = build_spec(broker, title="Orders service", version="1.0.0")
    print(to_json(spec))

The module has no extras for `to_json`; pure stdlib. `to_yaml` lazily imports
`PyYAML` and raises `MissingDependencyError` when the `ruststream[asyncapi]`
extra is not installed.
"""

from ruststream.asyncapi._build import build_spec, build_spec_for_router
from ruststream.asyncapi._errors import AsyncAPIError, MissingDependencyError
from ruststream.asyncapi._serialize import to_json, to_yaml
from ruststream.asyncapi._viewer import render_viewer_html

__all__: tuple[str, ...] = (
    "AsyncAPIError",
    "MissingDependencyError",
    "build_spec",
    "build_spec_for_router",
    "render_viewer_html",
    "to_json",
    "to_yaml",
)
