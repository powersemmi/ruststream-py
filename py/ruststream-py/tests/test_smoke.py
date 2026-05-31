"""Smoke tests for the ruststream native extension."""

import ruststream


def test_version_exported() -> None:
    assert isinstance(ruststream.__version__, str)
    assert ruststream.__version__ != ""
