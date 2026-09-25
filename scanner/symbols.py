"""Where the universe builder gets its starting list of symbols.

Two sources, both returning the same record shape {symbol, name, exchange, etf}:

  alpaca   Alpaca's list of active, tradable US equities (needs Alpaca keys).
  nasdaq   Nasdaq Trader's public symbol directory: every security listed on
           Nasdaq, NYSE, NYSE American, NYSE Arca and Cboe BZX, refreshed daily,
           no account needed. Works with any market-data provider.

Both lists then go through the same eligibility filter (eligible_symbols), so
the only thing that differs between two universes built from them is which
securities each source knows about.
"""
from __future__ import annotations

import logging
import os
from typing import Iterable

import requests

log = logging.getLogger(__name__)

SOURCES = ("alpaca", "nasdaq")

_NASDAQ_URLS = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
)
_ALPACA_BASES = ("https://api.alpaca.markets", "https://paper-api.alpaca.markets")
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# Name fragments that indicate non-equity products (case-insensitive). Applied
# to every source, so a name-only source and a flagged source are held to the
# same rule.
ETF_NAME_FRAGMENTS = (
    "etf", " fund", "trust", "bull", "bear", "2x", "3x", "ultra",
    "inverse", "leveraged", "proshares", "direxion", "ishares",
    "vanguard etf", "spdr", "invesco qqq",
)

# otherlisted.txt exchange codes
_EXCHANGE = {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX", "V": "IEX"}


def parse_nasdaq_directory(nasdaq_listed: str, other_listed: str) -> list[dict]:
    """Parse the two pipe-delimited Nasdaq Trader files. Test issues and the
    trailing "File Creation Time" line are dropped."""
    out: list[dict] = []

    def rows(text: str):
        lines = [l for l in text.splitlines() if l.strip()]
        if not lines:
            return
        header = lines[0].split("|")
        for line in lines[1:]:
            if line.startswith("File Creation Time"):
                continue
            yield dict(zip(header, line.split("|")))

    for r in rows(nasdaq_listed):
        if r.get("Test Issue") == "Y":
            continue
        out.append({"symbol": r.get("Symbol", "").strip(), "name": r.get("Security Name", ""),
                    "exchange": "Nasdaq", "etf": r.get("ETF") == "Y"})
    for r in rows(other_listed):
        if r.get("Test Issue") == "Y":
            continue
        # ACT Symbol uses "." for share classes (BRK.B), same as Alpaca.
        out.append({"symbol": r.get("ACT Symbol", "").strip(), "name": r.get("Security Name", ""),
                    "exchange": _EXCHANGE.get(r.get("Exchange", ""), r.get("Exchange", "")),
                    "etf": r.get("ETF") == "Y"})
    return out


def fetch_nasdaq(get=requests.get) -> list[dict]:
    texts = []
    for url in _NASDAQ_URLS:
        resp = get(url, headers=_UA, timeout=30)
        resp.raise_for_status()
        texts.append(resp.text)
    recs = parse_nasdaq_directory(*texts)
    log.info("Nasdaq directory: %d listed securities", len(recs))
    return recs


def fetch_alpaca(get=requests.get) -> list[dict]:
    """Active US equities from Alpaca's trading API (live, then paper keys)."""
    headers = {"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
               "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]}
    for base in _ALPACA_BASES:
        resp = get(f"{base}/v2/assets", headers=headers,
                   params={"status": "active", "asset_class": "us_equity"}, timeout=30)
        if resp.status_code in (401, 403):
            continue
        resp.raise_for_status()
        recs = [{"symbol": a.get("symbol", ""), "name": a.get("name") or "", "exchange": a.get("exchange", ""),
                 "etf": False, "tradable": bool(a.get("tradable"))} for a in resp.json()]
        log.info("Alpaca assets (%s): %d active US equities", base, len(recs))
        return recs
    raise RuntimeError("Could not authenticate with Alpaca's trading API (tried live and paper). "
                       "Check ALPACA_API_KEY / ALPACA_SECRET_KEY in .env.")


def fetch(source: str) -> list[dict]:
    if source == "nasdaq":
        return fetch_nasdaq()
    if source == "alpaca":
        return fetch_alpaca()
    raise ValueError(f"unknown symbol source {source!r}; options: {', '.join(SOURCES)}")


def eligible_symbols(records: Iterable[dict]) -> list[str]:
    """Keep plain common-stock tickers: tradable, not flagged or named like an
    ETF/fund/leveraged product, symbol made of letters, digits and '-' only
    (which also drops share classes like BRK.B, warrants and units)."""
    kept, seen = [], set()
    for r in records:
        if r.get("tradable") is False or r.get("etf"):
            continue
        name = (r.get("name") or "").lower()
        if any(frag in name for frag in ETF_NAME_FRAGMENTS):
            continue
        sym = (r.get("symbol") or "").strip().upper()
        if not sym or sym in seen or not all(c.isalpha() or c.isdigit() or c == "-" for c in sym):
            continue
        seen.add(sym)
        kept.append(sym)
    return kept
