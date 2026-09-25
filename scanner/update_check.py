"""Is there a newer release on GitHub? One anonymous request at startup.

The scanner has no server and phones nowhere, so a user who downloaded a
release has no way of hearing about the next one (GitHub only notifies people
who Watch releases). This asks GitHub's public releases endpoint once, on a
background thread, and remembers the answer for the dashboard and the terminal.

What goes out: one GET to api.github.com for the latest release of the public
repo. GitHub sees your IP and nothing else: no key, no symbols, no settings.
Turn it off with UPDATE_CHECK=0 in .env. It never downloads or installs
anything; the banner links to the release notes and the update is `git pull`.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from scanner import __version__

log = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/simonro/edge-scanner/releases/latest"
RELEASES_PAGE = "https://github.com/simonro/edge-scanner/releases"
_TIMEOUT = 6.0


def parse_version(v: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Anything unparsable is (0,), older than everything."""
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else (0,)


def enabled() -> bool:
    return os.environ.get("UPDATE_CHECK", "1").strip().lower() not in ("0", "false", "no", "off")


@dataclass
class UpdateInfo:
    current: str = __version__
    latest: Optional[str] = None          # None until the check has answered
    url: str = RELEASES_PAGE
    title: str = ""
    checked: bool = False
    error: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.latest is not None and parse_version(self.latest) > parse_version(self.current)

    def as_dict(self) -> dict:
        return {"current": self.current, "latest": self.latest, "available": self.available,
                "url": self.url, "title": self.title, "checked": self.checked}


_info = UpdateInfo()
_lock = threading.Lock()


def info() -> UpdateInfo:
    with _lock:
        return UpdateInfo(**vars(_info))


def check_once(fetch=None) -> UpdateInfo:
    """Ask GitHub now, synchronously. `fetch` is injectable for tests."""
    global _info
    result = UpdateInfo()
    try:
        if fetch is None:
            def fetch() -> dict:
                req = urllib.request.Request(RELEASES_API, headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"edge-scanner/{__version__}",
                })
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                    return json.loads(r.read().decode("utf-8"))
        data = fetch()
        result.latest = str(data.get("tag_name") or "")
        result.url = str(data.get("html_url") or RELEASES_PAGE)
        result.title = str(data.get("name") or "")
    except Exception as exc:                  # offline, rate limited, GitHub down: all fine
        result.error = str(exc)[:200]
        log.debug("update check failed: %s", exc)
    result.checked = True
    with _lock:
        _info = result
    if result.available:
        print(f"\n       A newer release is available: {result.latest} (you run v{result.current}).\n"
              f"       Notes and update steps: {result.url}\n", flush=True)
    return result


def start_background_check() -> None:
    """Run the check on a daemon thread. No-op when UPDATE_CHECK=0."""
    if not enabled():
        log.info("update check disabled (UPDATE_CHECK=0)")
        return
    threading.Thread(target=check_once, daemon=True, name="update-check").start()
