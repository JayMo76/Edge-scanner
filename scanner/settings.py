"""Runtime-editable parameters: the shared gates and stop lookback every build
has, plus any parameters an optional engine plugin contributes for its system
setups.

Every threshold the engine applies is declared once here (SCHEMA) with its
code default, label, unit and range. The engine reads live values through the
`settings` singleton (`from scanner.settings import settings as S; S.GATE_RVOL_MIN`)
instead of module constants, so a Save from the dashboard hot-applies on the
next bar without a restart.

Persistence (all gitignored under data/settings/):
    current.json      the live values (only keys that differ from defaults)
    presets/<n>.json  named parameter sets
    history.jsonl     one line per save/reset/preset-apply: who, when, what

Every alert emitted by the system-setup builders carries `config_hash` (8 hex
of the non-default values, "default" when nothing is changed) and
`modified: bool`, so a downstream consumer can separate signals produced under
edited rules from the shipped definition.

`gate_stats` counts, per (setup, gate), how many evaluations passed and failed
today; the dashboard shows it beside each gate so you can see which one is
doing the blocking before you touch it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
SETTINGS_DIR = Path("data/settings")
_ID_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,48}$")

_T = lambda h, m: h * 60 + m


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    default: float | int
    desc: str
    setups: tuple[str, ...]          # which setup cards show it; ("*",) = shared
    group: str                       # card section
    type: str = "float"              # float | int | time (minutes since midnight ET) | pct
    unit: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    gate: Optional[str] = None       # the gate-stats key this parameter drives, if any


# Settings every build has: the stop lookback and the gates the universe
# conditions read. Setups `()` = not tied to a setup card; ("*",) = shared.
_CORE_SCHEMA: list[Param] = [
    # ── gates used by universe conditions (scanner/gates.py) ───────────────
    Param("STOP_BARS", "Stop lookback (1-min bars)", 5, "Stop = low (long) / high (short) of the last N 1-min bars including the signal bar.", ("*",), "Stop & throttling", "int", "bars", 1, 60, 1),
    Param("GATE_RVOL_MIN", "Min RVOL", 1.00, "Relative volume at or above this (time-of-day RVOL vs the 20-day profile).", (), "Gates", "float", "x", 0, 10, 0.05),
    Param("GATE_VOID_MIN_PCT", "Min clear air (void)", 1.0, "Distance to the next 60-day level in the trade direction. Less than this and the gate blocks.", (), "Gates", "pct", "%", 0, 20, 0.1),
    Param("GATE_RRS_WARMUP_5M_BARS", "RRS warm-up", 12, "5-min bars a symbol must have before a missing 5-min RRS blocks the gate (before that the daily RRS is used).", (), "Gates", "int", "bars", 0, 78, 1),
    Param("GATE_MARKET_ALIGN_FROM", "Market align active from", _T(10, 0), "The SPY-regime alignment gate only applies from this time on.", (), "Time windows", "time"),
]

# Settings contributed by optional engine plugins (scanner/private/params.py
# when present). Imported here, after Param and _T exist, because the plugin
# module builds its Param list from them.
try:
    from scanner.private.params import PARAMS as _PLUGIN_SCHEMA
except ImportError:
    _PLUGIN_SCHEMA = []

SCHEMA: list[Param] = [*_PLUGIN_SCHEMA, *_CORE_SCHEMA]
_BY_KEY: dict[str, Param] = {p.key: p for p in SCHEMA}


def coerce(p: Param, raw: Any) -> float | int:
    """Validate one value against its Param; raises ValueError."""
    if isinstance(raw, bool):
        raise ValueError(f"{p.key}: boolean is not a number")
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{p.key}: not a number: {raw!r}")
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{p.key}: not finite")
    if p.type in ("int", "time"):
        if abs(v - round(v)) > 1e-9:
            raise ValueError(f"{p.key}: must be a whole number")
        v = int(round(v))
        if p.type == "time" and not (0 <= v < 24 * 60):
            raise ValueError(f"{p.key}: time must be 00:00-23:59")
    if p.min is not None and v < p.min:
        raise ValueError(f"{p.key}: below minimum {p.min}")
    if p.max is not None and v > p.max:
        raise ValueError(f"{p.key}: above maximum {p.max}")
    return v


class Settings:
    """Thread-safe live parameter store. Attribute access returns the live value."""

    def __init__(self, dir: Path = SETTINGS_DIR) -> None:
        object.__setattr__(self, "_dir", Path(dir))
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_values", {p.key: p.default for p in SCHEMA})
        object.__setattr__(self, "_hash", "default")
        self.load()

    # -- fast reads used by the engine ---------------------------------------
    def __getattr__(self, key: str):
        try:
            return object.__getattribute__(self, "_values")[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value: Any) -> None:
        raise AttributeError("use Settings.save()")

    # -- introspection -----------------------------------------------------------
    @property
    def dir(self) -> Path:
        return object.__getattribute__(self, "_dir")

    def values(self) -> dict[str, float | int]:
        with self._lock:
            return dict(self._values)

    @staticmethod
    def defaults() -> dict[str, float | int]:
        return {p.key: p.default for p in SCHEMA}

    def modified(self) -> dict[str, float | int]:
        with self._lock:
            return {k: v for k, v in self._values.items() if v != _BY_KEY[k].default}

    def is_modified(self) -> bool:
        return bool(self.modified())

    @property
    def hash(self) -> str:
        return object.__getattribute__(self, "_hash")

    @staticmethod
    def schema() -> list[dict]:
        return [{"key": p.key, "label": p.label, "default": p.default, "desc": p.desc, "setups": list(p.setups),
                 "group": p.group, "type": p.type, "unit": p.unit, "min": p.min, "max": p.max, "step": p.step, "gate": p.gate}
                for p in SCHEMA]

    # -- persistence -------------------------------------------------------------
    def _recompute_hash(self) -> None:
        mod = {k: v for k, v in self._values.items() if v != _BY_KEY[k].default}
        h = "default" if not mod else hashlib.sha1(json.dumps(mod, sort_keys=True).encode()).hexdigest()[:8]
        object.__setattr__(self, "_hash", h)

    def load(self) -> None:
        p = self.dir / "current.json"
        vals = {q.key: q.default for q in SCHEMA}
        try:
            if p.exists():
                doc = json.loads(p.read_text(encoding="utf-8"))
                for k, v in (doc.get("values") or {}).items():
                    if k in _BY_KEY:
                        try:
                            vals[k] = coerce(_BY_KEY[k], v)
                        except ValueError as exc:
                            log.warning("settings: ignoring %s", exc)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("settings: could not read %s: %s", p, exc)
        with self._lock:
            object.__setattr__(self, "_values", vals)
            self._recompute_hash()

    def _write_current(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        mod = {k: v for k, v in self._values.items() if v != _BY_KEY[k].default}
        doc = {"saved_at": datetime.now(_ET).isoformat(timespec="seconds"), "hash": self.hash, "values": mod}
        tmp = self.dir / f".current.{os.getpid()}.tmp"
        tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.dir / "current.json")

    def _append_history(self, source: str, note: str, changes: dict) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.dir / "history.jsonl", "a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps({"ts": datetime.now(_ET).isoformat(timespec="seconds"), "source": source,
                                    "note": note, "hash": self.hash, "changes": changes}) + "\n")
        except OSError as exc:
            log.warning("settings: history write failed: %s", exc)

    def save(self, values: dict[str, Any], *, source: str = "ui", note: str = "") -> dict:
        """Validate and hot-apply `values` (partial dict OK). Returns the change set."""
        errors: list[str] = []
        new: dict[str, float | int] = {}
        for k, v in (values or {}).items():
            p = _BY_KEY.get(k)
            if p is None:
                errors.append(f"unknown key: {k}")
                continue
            try:
                new[k] = coerce(p, v)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            raise ValueError("; ".join(errors))
        with self._lock:
            changes = {k: [self._values[k], v] for k, v in new.items() if self._values[k] != v}
            if not changes:
                return {}
            self._values.update(new)
            self._recompute_hash()
            self._write_current()
        self._append_history(source, note, changes)
        log.info("settings: %d value(s) changed (%s) -> %s", len(changes), source, self.hash)
        return changes

    def reset(self, *, keys: Optional[list[str]] = None, setup: Optional[str] = None, note: str = "") -> dict:
        targets = [p for p in SCHEMA if (keys is None or p.key in keys) and (setup is None or setup in p.setups or "*" in p.setups)]
        return self.save({p.key: p.default for p in targets}, source="reset", note=note or f"reset {setup or 'all'}")

    # -- presets -----------------------------------------------------------------
    @property
    def _presets_dir(self) -> Path:
        return self.dir / "presets"

    def list_presets(self) -> list[dict]:
        out = []
        if self._presets_dir.exists():
            for p in sorted(self._presets_dir.glob("*.json")):
                try:
                    doc = json.loads(p.read_text(encoding="utf-8"))
                    out.append({"name": p.stem, "saved_at": doc.get("saved_at"), "hash": doc.get("hash"),
                                "n_modified": len(doc.get("values") or {})})
                except (OSError, json.JSONDecodeError):
                    continue
        return out

    def save_preset(self, name: str) -> dict:
        if not _ID_RE.match(name or ""):
            raise ValueError("preset name: letters, digits, space, _ . - (max 48)")
        self._presets_dir.mkdir(parents=True, exist_ok=True)
        doc = {"saved_at": datetime.now(_ET).isoformat(timespec="seconds"), "hash": self.hash, "values": self.modified()}
        # Temp file + replace, like current.json: an interrupted write must not
        # truncate a preset that was fine a second ago.
        path = self._presets_dir / f"{name}.json"
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(doc, indent=2) + "\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
        return {"name": name, **doc}

    def apply_preset(self, name: str) -> dict:
        p = self._presets_dir / f"{name}.json"
        if not _ID_RE.match(name or "") or not p.exists():
            raise ValueError(f"no preset named {name!r}")
        doc = json.loads(p.read_text(encoding="utf-8"))
        full = {q.key: q.default for q in SCHEMA}
        full.update({k: v for k, v in (doc.get("values") or {}).items() if k in _BY_KEY})
        return self.save(full, source="preset", note=f"apply preset {name}")

    def delete_preset(self, name: str) -> bool:
        p = self._presets_dir / f"{name}.json"
        if not _ID_RE.match(name or "") or not p.exists():
            return False
        p.unlink()
        return True

    def history(self, limit: int = 100) -> list[dict]:
        p = self.dir / "history.jsonl"
        if not p.exists():
            return []
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        out.reverse()
        return out


class GateStats:
    """Pass/fail counters per (setup, gate) for the current session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, dict[str, list[int]]] = {}
        self._evals: dict[str, int] = {}
        self._fired: dict[str, int] = {}
        self._since = datetime.now(_ET).isoformat(timespec="seconds")

    def record(self, setup: str, gates, fired: bool) -> None:
        with self._lock:
            d = self._counts.setdefault(setup, {})
            for g in gates:
                c = d.setdefault(g.name, [0, 0])
                c[0 if g.passed else 1] += 1
            self._evals[setup] = self._evals.get(setup, 0) + 1
            if fired:
                self._fired[setup] = self._fired.get(setup, 0) + 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "since": self._since,
                "setups": {s: {"evals": self._evals.get(s, 0), "fired": self._fired.get(s, 0),
                               "gates": {g: {"pass": c[0], "fail": c[1]} for g, c in gd.items()}}
                           for s, gd in self._counts.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._counts.clear(); self._evals.clear(); self._fired.clear()
            self._since = datetime.now(_ET).isoformat(timespec="seconds")


settings = Settings()
gate_stats = GateStats()
