#!/usr/bin/env python
"""Build two universes side by side and explain every difference.

Each side is PROVIDER:SYMBOL_LIST (see build_universe.py --provider and
--symbols-from). Both are built with the same thresholds, then compared:

    python scripts/compare_universes.py --a alpaca:alpaca --b alpaca:nasdaq
    python scripts/compare_universes.py --a alpaca:alpaca --b <provider>:nasdaq --preset all

Presets: default (the builder's defaults), wide (price $3, 300k shares,
$10M/day, ATR 1.5%), all (no thresholds: every eligible symbol with data).

Writes a Markdown report plus both diagnostics files under
data/universe_compare/ and prints the headline. Differences are classified:
  * list      the symbol is not in the other side's symbol list at all
  * data      both sides had it, but a metric put it on the other side of a
              threshold (reported with both values)
  * missing   the other side had no price or no history for it
A difference within 10% of a threshold on the side that dropped it is also
marked "near cutoff": that is noise between data sources, not a rule mismatch.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "data" / "universe_compare"

PRESETS = {
    "default": {"min_price": 15.0, "min_avg_vol": 5_000_000, "min_dollar_vol_m": 50.0, "min_atr_pct": 1.0},
    "wide":    {"min_price": 3.0,  "min_avg_vol": 300_000,   "min_dollar_vol_m": 10.0, "min_atr_pct": 1.5},
    "all":     {"min_price": 0.0,  "min_avg_vol": 0,         "min_dollar_vol_m": 0.0,  "min_atr_pct": 0.0},
}
_METRIC_FOR = {"price": ("price", "min_price", 1.0), "avg_vol": ("avg_vol_20d", "min_avg_vol", 1.0),
               "dollar_vol": ("avg_dollar_vol_20d", "min_dollar_vol_m", 1e6), "atr_pct": ("atr_pct", "min_atr_pct", 1.0)}


def build(spec: str, preset: dict, tag: str) -> Path:
    provider, _, source = spec.partition(":")
    diag = OUT_DIR / f"{tag}_diag.csv"
    cmd = [sys.executable, str(REPO / "scripts" / "build_universe.py"), "--provider", provider,
           "--out", str(OUT_DIR / f"{tag}.csv"), "--diagnostics", str(diag), "--log-level", "WARNING",
           "--min-price", str(preset["min_price"]), "--min-avg-vol", str(preset["min_avg_vol"]),
           "--min-dollar-vol-m", str(preset["min_dollar_vol_m"]), "--min-atr-pct", str(preset["min_atr_pct"])]
    if source:
        cmd += ["--symbols-from", source]
    print(f"building {spec} ...", flush=True)
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
    if not diag.exists():
        sys.exit(f"build {spec} failed:\n{(r.stdout + r.stderr)[-2000:]}")
    return diag


def _near(row: pd.Series, result: str, preset: dict) -> bool:
    if result not in _METRIC_FOR:
        return False
    col, key, scale = _METRIC_FOR[result]
    thr = preset[key] * scale
    val = row.get(col)
    return thr > 0 and pd.notna(val) and abs(float(val) - thr) / thr <= 0.10


def explain(sym: str, kept_side: pd.DataFrame, other: pd.DataFrame, preset: dict) -> tuple[str, str, bool]:
    """(kind, detail, near_cutoff) for a symbol kept on one side only."""
    if sym not in other.index:
        return "list", "not in the other symbol list", False
    o = other.loc[sym]
    res = o["result"]
    if res in ("no_price", "no_history"):
        return "missing", res.replace("_", " "), False
    col, key, scale = _METRIC_FOR.get(res, (None, None, 1.0))
    if col is None:
        return "data", res, False
    mine = kept_side.loc[sym].get(col)
    fmt = (lambda v: f"{v:,.0f}") if col in ("avg_vol_20d", "avg_dollar_vol_20d") else (lambda v: f"{v:,.2f}")
    detail = f"{res}: {fmt(float(o[col]))} there vs {fmt(float(mine))} here (threshold {fmt(preset[key] * scale)})"
    return "data", detail, _near(o, res, preset)


def compare(a_diag: Path, b_diag: Path, a_name: str, b_name: str, preset_name: str) -> str:
    preset = PRESETS[preset_name]
    a = pd.read_csv(a_diag, dtype={"symbol": str}, keep_default_na=False, na_values=[""]).drop_duplicates("symbol").set_index("symbol")
    b = pd.read_csv(b_diag, dtype={"symbol": str}, keep_default_na=False, na_values=[""]).drop_duplicates("symbol").set_index("symbol")
    ka, kb = set(a.index[a.result == "kept"]), set(b.index[b.result == "kept"])
    both = ka & kb
    union = ka | kb
    lines = [f"# Universe comparison: {a_name} vs {b_name} ({preset_name})", "",
             f"Built {date.today().isoformat()}. Thresholds: {preset}.", "",
             "| | symbols |", "|---|---|",
             f"| {a_name} symbol list (eligible) | {len(a):,} |", f"| {b_name} symbol list (eligible) | {len(b):,} |",
             f"| {a_name} universe | {len(ka):,} |", f"| {b_name} universe | {len(kb):,} |",
             f"| in both | {len(both):,} |",
             f"| overlap (in both / in either) | {len(both) / max(len(union), 1):.1%} |",
             f"| {a_name} covered by {b_name} | {len(both) / max(len(ka), 1):.1%} |", ""]

    common = sorted(set(a.index) & set(b.index))
    if common:
        ca, cb = a.loc[common], b.loc[common]
        rows = []
        for col, label in (("price", "last price"), ("avg_vol_20d", "20-day avg volume"),
                           ("avg_dollar_vol_20d", "20-day avg dollar volume"), ("atr_pct", "ATR %")):
            x, y = pd.to_numeric(ca[col], errors="coerce"), pd.to_numeric(cb[col], errors="coerce")
            ok = x.notna() & y.notna() & (x != 0)
            if not ok.any():
                continue
            ratio = (y[ok] / x[ok])
            rows.append(f"| {label} | {ok.sum():,} | {ratio.median():.4f} | {ratio.quantile(0.05):.4f} to {ratio.quantile(0.95):.4f} |")
        if rows:
            lines += [f"Metric agreement on symbols both lists share ({b_name} / {a_name}):", "",
                      "| metric | symbols | median ratio | 5th to 95th percentile |", "|---|---|---|---|", *rows, ""]

    for side, kept, other, other_name in ((a_name, ka - kb, b, b_name), (b_name, kb - ka, a, a_name)):
        src = a if side == a_name else b
        lines += [f"## In {side} only ({len(kept)})", ""]
        if not kept:
            lines += ["None.", ""]
            continue
        ex = [(s, *explain(s, src, other, preset)) for s in sorted(kept)]
        by_kind = pd.Series([k for _, k, _, _ in ex]).value_counts().to_dict()
        near = sum(1 for *_, n in ex if n)
        lines += [f"Why {other_name} dropped them: {by_kind}. Within 10% of a threshold: {near}.", "",
                  "| symbol | kind | detail | near cutoff |", "|---|---|---|---|"]
        lines += [f"| {s} | {k} | {d} | {'yes' if n else ''} |" for s, k, d, n in ex[:300]]
        if len(ex) > 300:
            lines.append(f"| ... | | {len(ex) - 300} more | |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--a", required=True, help="PROVIDER:SYMBOL_LIST, e.g. alpaca:alpaca")
    ap.add_argument("--b", required=True, help="PROVIDER:SYMBOL_LIST, e.g. alpaca:nasdaq")
    ap.add_argument("--preset", choices=PRESETS, default="default")
    ap.add_argument("--reuse", action="store_true", help="reuse today's diagnostics files if present")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = date.today().isoformat()
    tags = [f"{stamp}_{spec.replace(':', '-')}_{args.preset}" for spec in (args.a, args.b)]
    diags = []
    for spec, tag in zip((args.a, args.b), tags):
        d = OUT_DIR / f"{tag}_diag.csv"
        diags.append(d if (args.reuse and d.exists()) else build(spec, PRESETS[args.preset], tag))
    report = compare(diags[0], diags[1], args.a, args.b, args.preset)
    out = OUT_DIR / f"{stamp}_{args.a.replace(':', '-')}_vs_{args.b.replace(':', '-')}_{args.preset}.md"
    out.write_text(report + "\n", encoding="utf-8")
    print("\n".join(report.splitlines()[:16]))
    print(f"\nfull report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
