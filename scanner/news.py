"""News for the Dashboard V2 News window.

Two kinds of source, merged into one list:

- The Alpaca news wire (Benzinga): GET https://data.alpaca.markets/v1beta1/news
  with the same key headers the scanner's data feed uses. Market-wide and
  per-symbol.
- Keyless per-symbol RSS feeds (Yahoo Finance, Nasdaq). Only queried when
  symbols are given. Turn off or reorder with NEWS_RSS_SOURCES
  (comma-separated, e.g. "yahoo", or "" for none).

A quiet symbol often has nothing inside the window, so a symbol query that
comes back empty is retried once over FALLBACK_HOURS and the payload carries
`widened_hours` so the UI can say so.

Results are cached per query for `ttl` seconds and the client fails open: if
every source fails the caller gets the last good payload (marked
`stale: True`) or an empty item list with the error string, never an
exception.
"""
from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

log = logging.getLogger(__name__)

NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
_SUMMARY_MAX = 240
FALLBACK_HOURS = 24 * 30
# RSS is one request per symbol per feed, so cap how many symbols fan out.
_RSS_MAX_SYMBOLS = 5
RSS_FEEDS: dict[str, tuple[str, str]] = {
    "yahoo": ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"),
    "nasdaq": ("Nasdaq", "https://www.nasdaq.com/feed/rssoutbound?symbol={symbol}"),
}
# Both hosts reject the default python-requests agent.
_RSS_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
_NASDAQ_TICKERS = "{http://nasdaq.com/reference/feeds/1.0}tickers"
_TAG_RE = re.compile(r"<[^>]+>")


def clean_text(s: object) -> str:
    """Strip HTML tags + entities (Benzinga summaries arrive with both)."""
    return _TAG_RE.sub("", html.unescape(str(s or ""))).strip()


def _first_image(images: object) -> Optional[str]:
    if not isinstance(images, list):
        return None
    for want in ("thumb", "small", "large"):
        for i in images:
            if isinstance(i, dict) and i.get("size") == want and i.get("url"):
                return i["url"]
    return None


def parse_item(a: dict) -> Optional[dict]:
    """Normalise one Alpaca news article; None when it has no headline."""
    headline = clean_text(a.get("headline"))
    if not headline:
        return None
    return {
        "id": a.get("id"),
        "headline": headline,
        "summary": clean_text(a.get("summary"))[:_SUMMARY_MAX],
        "url": a.get("url") or "",
        "source": (a.get("source") or "").title(),
        "symbols": [s for s in (a.get("symbols") or []) if isinstance(s, str)],
        "image": _first_image(a.get("images")),
        "created_at": a.get("created_at") or "",
        # Full article body (HTML) when the wire includes it. Rendered by the
        # dashboard inside a sandboxed iframe, never as trusted markup.
        "content": a.get("content") or "",
    }


def _epoch(created_at: str) -> float:
    try:
        return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


def parse_rss(xml_text: str, symbol: str, source: str) -> list[dict]:
    """Normalise an RSS 2.0 feed into the same item shape as parse_item."""
    items: list[dict] = []
    for node in ET.fromstring(xml_text).iter("item"):
        headline = clean_text(node.findtext("title"))
        url = (node.findtext("link") or "").strip()
        if not headline or not url:
            continue
        try:
            created = parsedate_to_datetime(node.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        tickers = [t.strip().upper() for t in (node.findtext(_NASDAQ_TICKERS) or "").split(",") if t.strip()]
        items.append({
            "id": f"{source}:{node.findtext('guid') or url}",
            "headline": headline,
            "summary": clean_text(node.findtext("description"))[:_SUMMARY_MAX],
            "url": url,
            "source": source,
            "symbols": [symbol] + [t for t in tickers if t != symbol],
            "image": None,
            "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "content": "",
        })
    return items


def _rss_sources_from_env() -> tuple[str, ...]:
    raw = os.environ.get("NEWS_RSS_SOURCES")
    if raw is None:
        return tuple(RSS_FEEDS)
    return tuple(n for n in (p.strip().lower() for p in raw.split(",")) if n in RSS_FEEDS)


def _default_get(url: str, *, headers: dict, params: dict, timeout: float):
    import requests
    return requests.get(url, headers=headers, params=params, timeout=timeout)


class NewsClient:
    def __init__(
        self,
        api_key: Optional[str],
        secret_key: Optional[str],
        ttl: float = 30.0,
        timeout: float = 8.0,
        *,
        get_fn: Optional[Callable] = None,
        session=None,
        rss_get_fn: Optional[Callable] = None,
        rss_sources: Optional[tuple[str, ...]] = None,
    ) -> None:
        self._headers = {
            "APCA-API-KEY-ID": api_key or "",
            "APCA-API-SECRET-KEY": secret_key or "",
        }
        self._ttl = ttl
        self._timeout = timeout
        if get_fn is not None:
            self._get = get_fn
        elif session is not None:
            self._get = session.get
        else:
            self._get = _default_get
        # An injected wire getter means an offline caller (tests): RSS stays off
        # unless it gets its own getter too.
        if rss_get_fn is not None:
            self._rss_get: Optional[Callable] = rss_get_fn
        elif get_fn is None and session is None:
            self._rss_get = _default_get
        else:
            self._rss_get = None
        self._rss_sources = _rss_sources_from_env() if rss_sources is None else tuple(rss_sources)
        self._cache: dict[tuple, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._headers["APCA-API-KEY-ID"] and self._headers["APCA-API-SECRET-KEY"])

    def fetch(self, symbols: Optional[list[str]] = None, limit: int = 50, hours: int = 24) -> dict:
        syms = tuple(sorted({s.strip().upper() for s in (symbols or []) if s and s.strip()}))
        limit = max(1, min(int(limit), 50))
        hours = max(1, int(hours))
        key = (syms, limit, hours)
        now = time.monotonic()

        with self._lock:
            hit = self._cache.get(key)
            if hit and (now - hit[0]) < self._ttl:
                return hit[1]

        fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        items, errors, answered = self._gather(syms, limit, hours)
        widened = None
        if syms and not items and answered and hours < FALLBACK_HOURS:
            items, _, _ = self._gather(syms, limit, FALLBACK_HOURS)
            widened = FALLBACK_HOURS if items else None

        if not answered:
            error = "; ".join(errors) or "no news source configured"
            log.warning("news fetch failed (%s): %s", ",".join(syms) or "market", error)
            with self._lock:
                hit = self._cache.get(key)
            if hit:
                return {**hit[1], "stale": True, "error": error}
            return {"fetched_at": fetched_at, "stale": True, "items": [], "error": error}

        result: dict = {"fetched_at": fetched_at, "stale": False, "items": items}
        if widened:
            result["widened_hours"] = widened
        with self._lock:
            self._cache[key] = (now, result)
        return result

    def _gather(self, syms: tuple, limit: int, hours: int) -> tuple[list[dict], list[str], bool]:
        """Every source for one window: (items, errors, did any source answer)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        jobs: list[Callable[[], list[dict]]] = []
        if self.configured:
            jobs.append(lambda: self._fetch_wire(syms, limit, cutoff))
        if self._rss_get is not None:
            for sym in syms[:_RSS_MAX_SYMBOLS]:
                for name in self._rss_sources:
                    jobs.append(lambda sym=sym, name=name: self._fetch_rss(name, sym, cutoff))
        if not jobs:
            return [], [], False

        def run(job: Callable[[], list[dict]]):
            try:
                return job(), None
            except Exception as exc:  # fail open per source
                return [], str(exc)

        if len(jobs) == 1:
            outcomes = [run(jobs[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
                outcomes = list(pool.map(run, jobs))

        errors = [err for _, err in outcomes if err]
        merged: list[dict] = []
        seen: set[str] = set()
        for got, _ in outcomes:                           # wire first: it has bodies + images
            for it in got:
                k = re.sub(r"[^a-z0-9]+", "", it["headline"].lower())
                if k in seen:
                    continue
                seen.add(k)
                merged.append(it)
        merged.sort(key=lambda it: _epoch(it["created_at"]), reverse=True)
        return merged[:limit], errors, len(errors) < len(jobs)

    def _fetch_wire(self, syms: tuple, limit: int, cutoff: datetime) -> list[dict]:
        params: dict = {
            "limit": limit,
            "exclude_contentless": "true",
            "include_content": "true",
            "sort": "desc",
            "start": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if syms:
            params["symbols"] = ",".join(syms)
        resp = self._get(NEWS_URL, headers=self._headers, params=params, timeout=self._timeout)
        status = getattr(resp, "status_code", 200)
        if status != 200:
            raise RuntimeError(f"news HTTP {status}")
        body = resp.json() or {}
        return [it for it in (parse_item(a) for a in body.get("news", []) if isinstance(a, dict)) if it]

    def _fetch_rss(self, name: str, symbol: str, cutoff: datetime) -> list[dict]:
        label, template = RSS_FEEDS[name]
        resp = self._rss_get(template.format(symbol=symbol), headers=_RSS_HEADERS, params={}, timeout=self._timeout)
        status = getattr(resp, "status_code", 200)
        if status != 200:
            raise RuntimeError(f"{name} HTTP {status}")
        floor = cutoff.timestamp()
        return [it for it in parse_rss(resp.text, symbol, label) if _epoch(it["created_at"]) >= floor]
