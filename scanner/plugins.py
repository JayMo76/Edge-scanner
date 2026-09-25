"""Optional engine plugins.

The core scanner runs custom setups only. A plugin package at
scanner/private/ (not part of the public distribution) can add built-in
"system setups" and extra integrations. This module is the one place the core
asks what is installed, so nothing else imports the plugin directly.

What a plugin provides (all optional):
  scanner/private/meta.py     SYSTEM_SETUPS: tuple of SystemSetup records
                              CAPABILITIES: dict of feature flags (e.g. "tos")
                              check(code, state, spy_state) -> dict, for the
                              setup check window
  scanner/private/params.py   PARAMS: settings the plugin's setups read
  scanner/private/live.py     add_args(parser) / attach(ctx) for run_live.py
  scanner/private/api.py      register(app, app_state) for extra routes

meta.py must stay import-light (data only): the trigger catalog and settings
read it at import time.
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass
from types import ModuleType
from typing import Optional

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemSetup:
    code: str            # stable wire code, e.g. "A"
    name: str            # default display name
    direction: str       # long | short
    evaluator: str = "_system_evaluator"   # LiveScanner attribute that runs it


# Set SCANNER_NO_PLUGINS=1 to run the core as if no plugin were installed. It is how the
# owner's checkout reproduces the public build (for release screenshots, or to see what a
# user without the plugin sees) without deleting anything.
_DISABLED = (os.environ.get("SCANNER_NO_PLUGINS") or "").strip().lower() in ("1", "true", "yes")


def _optional(name: str) -> Optional[ModuleType]:
    if _DISABLED:
        return None
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name and (exc.name == name or name.startswith(exc.name + ".")):
            return None                     # plugin not installed
        raise                               # installed but broken: say so


_meta = _optional("scanner.private.meta")

SYSTEM_SETUPS: tuple[SystemSetup, ...] = tuple(getattr(_meta, "SYSTEM_SETUPS", ()))
SYSTEM_CODES: tuple[str, ...] = tuple(s.code for s in SYSTEM_SETUPS)
SYSTEM_DEFAULT_NAMES: dict[str, str] = {s.code: s.name for s in SYSTEM_SETUPS}


def capabilities() -> dict[str, bool]:
    caps = {"tos": False, "system_setups": bool(SYSTEM_SETUPS)}
    caps.update({k: bool(v) for k, v in (getattr(_meta, "CAPABILITIES", {}) or {}).items()})
    return caps


def extra_feeds() -> dict[str, str]:
    """Market-data providers the plugin adds, as {name: "module:Class"}."""
    return dict(getattr(_meta, "FEEDS", {}) or {})


def system_check(code: str, state, spy_state=None) -> Optional[dict]:
    """The plugin's read-only check of one system setup on one symbol, or None."""
    fn = getattr(_meta, "check", None)
    return fn(code, state, spy_state) if fn else None


def live_extension() -> Optional[ModuleType]:
    return _optional("scanner.private.live")


def api_extension() -> Optional[ModuleType]:
    return _optional("scanner.private.api")
