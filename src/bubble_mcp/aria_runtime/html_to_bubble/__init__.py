"""Compatibility exports for Aria's Bubble CLI runtime."""

from __future__ import annotations

from .builder import BubbleCommandBuilder
from .mapper import HTMLToBubbleMapper

try:
    from .parser import HTMLParser
except Exception:

    class HTMLParser:  # type: ignore[no-redef]
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("The vendored HTML parser source is not available in this runtime.")


__all__ = ["BubbleCommandBuilder", "HTMLParser", "HTMLToBubbleMapper"]
