"""Data providers. Alpaca and Schwab are built in; a plugin can register more.

    from scanner.data import make_feed
    feed = make_feed("alpaca")

Keeping construction behind a factory means adding a provider does not touch
any signal code, which is the whole point of the DataFeed ABC in interface.py.
Extra providers come from scanner.plugins.extra_feeds() as
{name: "module.path:ClassName"} and are imported only when chosen.
"""
from __future__ import annotations

import importlib

from scanner import plugins
from scanner.data.interface import DataFeed

_EXTRA = plugins.extra_feeds()
_BUILTIN = {"schwab": "scanner.data.schwab:SchwabFeed", "webull": "scanner.data.webull:WebullFeed"}
_EXTRA = {**_BUILTIN, **_EXTRA}
FEEDS = ("alpaca", *sorted(_EXTRA))


def make_feed(name: str = "alpaca", **kwargs) -> DataFeed:
    """Return a DataFeed by name. Imports lazily so a missing optional
    dependency can never break the default Alpaca path."""
    key = (name or "alpaca").strip().lower()
    if key == "alpaca":
        from scanner.data.alpaca import AlpacaFeed
        return AlpacaFeed(**kwargs)
    if key in _EXTRA:
        module, _, cls = _EXTRA[key].partition(":")
        return getattr(importlib.import_module(module), cls)(**kwargs)
    raise ValueError(f"Unknown feed {name!r}. Options: {', '.join(FEEDS)}")
