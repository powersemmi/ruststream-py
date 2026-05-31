"""HTML viewer snippet built around the AsyncAPI React component.

`render_viewer_html(spec_url)` returns a self-contained HTML page that loads the
AsyncAPI React viewer from jsDelivr by default and fetches the spec from `spec_url`.
For offline / security-sensitive deployments, pass `react_url`/`css_url` overrides
pointing at locally-hosted assets.
"""

from html import escape

DEFAULT_REACT_URL = (
    "https://cdn.jsdelivr.net/npm/@asyncapi/react-component@2.4.0/browser/standalone/index.js"
)
DEFAULT_CSS_URL = (
    "https://cdn.jsdelivr.net/npm/@asyncapi/react-component@2.4.0/styles/default.min.css"
)

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<link rel="stylesheet" href="{css_url}" />
<style>
html, body, #asyncapi {{ margin: 0; padding: 0; height: 100%; }}
</style>
</head>
<body>
<div id="asyncapi"></div>
<script src="{react_url}" defer></script>
<script>
window.addEventListener("DOMContentLoaded", function () {{
  AsyncApiStandalone.render({{
    schema: {{ url: "{spec_url}" }},
    config: {{ show: {{ sidebar: true }} }},
  }}, document.getElementById("asyncapi"));
}});
</script>
</body>
</html>
"""


def render_viewer_html(
    spec_url: str,
    *,
    title: str = "AsyncAPI Viewer",
    react_url: str = DEFAULT_REACT_URL,
    css_url: str = DEFAULT_CSS_URL,
) -> str:
    """Return a one-file HTML page that renders the AsyncAPI spec hosted at `spec_url`.

    The default CDN URLs point at a pinned `@asyncapi/react-component` release.
    Override `react_url` / `css_url` to load the assets from your own server.
    """
    return _TEMPLATE.format(
        title=escape(title),
        spec_url=escape(spec_url, quote=True),
        react_url=escape(react_url, quote=True),
        css_url=escape(css_url, quote=True),
    )


__all__: tuple[str, ...] = ("DEFAULT_CSS_URL", "DEFAULT_REACT_URL", "render_viewer_html")
