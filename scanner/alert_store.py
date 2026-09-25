"""Persist session alerts to daily JSONL files so they survive restarts."""
import json
import logging
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_DEFAULT_DIR = Path("data/alerts")


class AlertStore:
    """Append-only store: one JSONL file per trading day under data/alerts/.

    On load, returns all alerts from the last `keep_days` calendar days,
    oldest first, so the in-memory buffer ends up in chronological order.
    On save, appends one JSON line per alert to today's file immediately.
    On cleanup (called at init), deletes files older than `keep_days`.
    """

    def __init__(self, store_dir: Path = _DEFAULT_DIR, keep_days: int = 5) -> None:
        self._dir      = Path(store_dir)
        self._keep_days = keep_days
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cleanup()

    # ── public API ────────────────────────────────────────────────────────────

    def save(self, alert: dict) -> None:
        """Append a single alert to today's file."""
        path = self._dir / f"{date.today().isoformat()}.jsonl"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert) + "\n")
        except OSError as exc:
            log.warning("AlertStore: failed to write alert: %s", exc)

    def load_recent(self) -> list[dict]:
        """Return all alerts from the last keep_days days, oldest first."""
        cutoff = date.today() - timedelta(days=self._keep_days - 1)
        alerts: list[dict] = []
        for path in sorted(self._dir.glob("*.jsonl")):
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_date < cutoff:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            alerts.append(json.loads(line))
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("AlertStore: failed to read %s: %s", path.name, exc)
        log.info("AlertStore: loaded %d alerts from last %d days", len(alerts), self._keep_days)
        return alerts

    # ── private ───────────────────────────────────────────────────────────────

    def _cleanup(self) -> None:
        cutoff = date.today() - timedelta(days=self._keep_days - 1)
        for path in self._dir.glob("*.jsonl"):
            try:
                if date.fromisoformat(path.stem) < cutoff:
                    path.unlink()
                    log.debug("AlertStore: removed old file %s", path.name)
            except (ValueError, OSError):
                pass
