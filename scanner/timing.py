"""Per-bar timing instrumentation for capacity planning.

Answers one question: how many symbols can the base universe hold before
`_on_bar` stops finishing inside the one-minute bar cadence?

This matters more than it looks. `LiveScanner._on_bar` runs synchronously on
the Alpaca stream's event-loop thread (`scanner/data/alpaca.py`
`subscribe_minute_bars`), so work that overruns the cadence backs the websocket
up rather than merely delaying alerts. The binding number is therefore
"seconds of work per market minute", not "average microseconds per symbol" -
Alpaca delivers the whole universe's bars in a burst at each minute boundary,
so the per-minute total is what has to fit.

Disabled by default; `bar_timer.enable()` turns it on. When disabled the cost
is one boolean read per stage. When enabled it is a pair of `perf_counter_ns`
calls per stage, roughly 100 ns against a body measured in hundreds of
microseconds.

Usage in the hot path::

    t = bar_timer.on            # one attribute read, hoisted out of the stages
    if t: t0 = perf_counter_ns()
    ...work...
    if t: bar_timer.record("system", perf_counter_ns() - t0)

Read it back with `bar_timer.snapshot()` or `GET /api/v2/diag/timing`.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from time import perf_counter_ns
from typing import Optional

# Stage order is the order they run inside _on_bar, so a printed report reads
# top-to-bottom like the code does.
STAGES = ("state", "series", "system", "de", "custom", "profile", "total")


class BarTimer:
    """Accumulates per-stage nanoseconds, and per-market-minute totals.

    Not locked on the write path: `_on_bar` is called from a single thread
    (the stream's event loop, or the replay driver). The lock guards snapshot
    reads and reset only.
    """

    def __init__(self) -> None:
        self.on: bool = False
        self._lock = threading.Lock()
        self._ns: dict[str, int] = defaultdict(int)
        self._n: dict[str, int] = defaultdict(int)
        self._max_ns: dict[str, int] = defaultdict(int)
        # bar minute (ISO string) -> total ns of work across every symbol in it
        self._minute_ns: dict[str, int] = defaultdict(int)
        self._minute_syms: dict[str, int] = defaultdict(int)

    # ── control ──────────────────────────────────────────────────────────────

    def enable(self) -> None:
        self.on = True

    def disable(self) -> None:
        self.on = False

    def reset(self) -> None:
        with self._lock:
            self._ns.clear()
            self._n.clear()
            self._max_ns.clear()
            self._minute_ns.clear()
            self._minute_syms.clear()

    # ── hot path ─────────────────────────────────────────────────────────────

    def record(self, stage: str, ns: int) -> None:
        self._ns[stage] += ns
        self._n[stage] += 1
        if ns > self._max_ns[stage]:
            self._max_ns[stage] = ns

    def record_bar(self, minute: str, total_ns: int) -> None:
        """One symbol's complete `_on_bar` cost, attributed to its bar minute."""
        self._ns["total"] += total_ns
        self._n["total"] += 1
        if total_ns > self._max_ns["total"]:
            self._max_ns["total"] = total_ns
        self._minute_ns[minute] += total_ns
        self._minute_syms[minute] += 1

    # ── read back ────────────────────────────────────────────────────────────

    def snapshot(self, project_to: Optional[int] = None) -> dict:
        """Return the measured cost, and optionally project it to a wider universe.

        Args:
            project_to: hypothetical base-universe size. The projection assumes
                per-symbol work is independent, which it is: every symbol has
                its own SymbolState and SymbolSeries and nothing crosses between
                them inside _on_bar.
        """
        with self._lock:
            stages = {}
            for s in STAGES:
                n = self._n.get(s, 0)
                if not n:
                    continue
                total = self._ns.get(s, 0)
                stages[s] = {
                    "calls": n,
                    "total_ms": round(total / 1e6, 1),
                    "mean_us": round(total / n / 1e3, 1),
                    "max_us": round(self._max_ns.get(s, 0) / 1e3, 1),
                }

            minutes = sorted(self._minute_ns.items())
            per_minute = [ns / 1e9 for _, ns in minutes]
            syms = [self._minute_syms[m] for m, _ in minutes]
            worst = max(per_minute) if per_minute else 0.0
            mean_syms = (sum(syms) / len(syms)) if syms else 0

            out = {
                "stages": stages,
                "market_minutes": len(minutes),
                "mean_symbols_per_minute": round(mean_syms, 1),
                "sec_per_market_minute": {
                    "mean": round(sum(per_minute) / len(per_minute), 3) if per_minute else 0.0,
                    "p95": round(_pct(per_minute, 95), 3),
                    "worst": round(worst, 3),
                },
            }

            n_total = self._n.get("total", 0)
            if n_total:
                per_symbol_us = self._ns["total"] / n_total / 1e3
                out["per_symbol_us"] = round(per_symbol_us, 1)
                # Budget: the burst must drain well inside the 60 s cadence.
                # 20 s is the working ceiling, a third of the cadence, leaving
                # room for GC, the API process and a slow tail.
                out["capacity"] = {
                    "budget_sec": 20.0,
                    "max_symbols_at_budget": int(20.0 / (per_symbol_us / 1e6)),
                }
                if project_to:
                    projected = project_to * per_symbol_us / 1e6
                    out["capacity"]["projection"] = {
                        "symbols": project_to,
                        "sec_per_market_minute": round(projected, 2),
                        "fits": projected < 20.0,
                    }
            return out

    def report(self, project_to: Optional[int] = None) -> str:
        """Human-readable one-screen summary."""
        s = self.snapshot(project_to)
        if not s.get("stages"):
            return "bar timing: no samples recorded"
        lines = ["", "-" * 68, "  Per-bar timing", "-" * 68,
                 f"  {'stage':<10} {'calls':>9} {'total ms':>10} {'mean us':>9} {'max us':>9}"]
        for name, d in s["stages"].items():
            lines.append(f"  {name:<10} {d['calls']:>9,} {d['total_ms']:>10,.1f} "
                         f"{d['mean_us']:>9.1f} {d['max_us']:>9.1f}")
        cap = s.get("capacity", {})
        spm = s["sec_per_market_minute"]
        lines += [
            "-" * 68,
            f"  market minutes replayed : {s['market_minutes']:,}",
            f"  symbols per minute      : {s['mean_symbols_per_minute']:,.1f}",
            f"  sec of work per minute  : mean {spm['mean']:.3f}  "
            f"p95 {spm['p95']:.3f}  worst {spm['worst']:.3f}",
            f"  per-symbol cost         : {s.get('per_symbol_us', 0):.1f} us",
        ]
        if cap:
            lines.append(f"  ceiling @ {cap['budget_sec']:.0f}s budget    : "
                         f"{cap['max_symbols_at_budget']:,} symbols")
            proj = cap.get("projection")
            if proj:
                verdict = "FITS" if proj["fits"] else "OVER BUDGET"
                lines.append(f"  projected @ {proj['symbols']:,} symbols : "
                             f"{proj['sec_per_market_minute']:.2f}s/min  [{verdict}]")
        lines.append("-" * 68)
        return "\n".join(lines)


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


# Process-wide singleton, mirroring `scanner.settings.settings` / `gate_stats`.
bar_timer = BarTimer()

__all__ = ["bar_timer", "BarTimer", "STAGES", "perf_counter_ns"]
