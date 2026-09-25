"""Unit tests for scanner.universe — load_universe()."""
import textwrap
from pathlib import Path

import pytest

from scanner.universe import load_universe


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_csv(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "universe.csv"
    p.write_text(textwrap.dedent(content).strip())
    return p


# ── FileNotFoundError ─────────────────────────────────────────────────────────

def test_load_universe_file_not_found():
    with pytest.raises(FileNotFoundError, match="Build it first"):
        load_universe("/nonexistent/path/that/does_not_exist.csv")


def test_load_universe_missing_file_message_contains_path(tmp_path):
    path = tmp_path / "missing.csv"
    with pytest.raises(FileNotFoundError) as exc_info:
        load_universe(path)
    assert "missing.csv" in str(exc_info.value)


# ── ValueError ────────────────────────────────────────────────────────────────

def test_load_universe_missing_symbol_column(tmp_path):
    p = _write_csv(tmp_path, "ticker,price\nAAPL,150\n")
    with pytest.raises(ValueError, match="missing a 'symbol' column"):
        load_universe(p)


# ── Happy-path loading ────────────────────────────────────────────────────────

def test_load_universe_returns_list(tmp_path):
    p = _write_csv(tmp_path, "symbol\nAAPL\nMSFT\nNVDA\n")
    result = load_universe(p)
    assert isinstance(result, list)
    assert set(result) == {"AAPL", "MSFT", "NVDA"}


def test_load_universe_sorted(tmp_path):
    p = _write_csv(tmp_path, "symbol\nNVDA\nAAPL\nMSFT\n")
    result = load_universe(p)
    assert result == sorted(result)


def test_load_universe_upcases(tmp_path):
    p = _write_csv(tmp_path, "symbol\naapl\nmsft\n")
    result = load_universe(p)
    assert "AAPL" in result
    assert "MSFT" in result


def test_load_universe_strips_whitespace(tmp_path):
    p = _write_csv(tmp_path, "symbol\n  AAPL  \nMSFT\n")
    result = load_universe(p)
    assert "AAPL" in result


def test_load_universe_drops_duplicates(tmp_path):
    p = _write_csv(tmp_path, "symbol\nAAPL\nAAPL\nMSFT\n")
    result = load_universe(p)
    assert result.count("AAPL") == 1


def test_load_universe_drops_na(tmp_path):
    p = _write_csv(tmp_path, "symbol\nAAPL\n\nMSFT\n")
    result = load_universe(p)
    assert "" not in result
    assert len(result) == 2


def test_load_universe_extra_columns_ignored(tmp_path):
    p = _write_csv(tmp_path, "symbol,in_sp500,in_nasdaq100,in_russell1000\nAAPL,True,True,True\n")
    result = load_universe(p)
    assert result == ["AAPL"]


def test_load_universe_path_as_string(tmp_path):
    p = _write_csv(tmp_path, "symbol\nAAPL\n")
    result = load_universe(str(p))
    assert result == ["AAPL"]


def test_tickers_that_look_like_missing_values_are_kept(tmp_path):
    """NA is a real ticker; pandas reads it as a missing value by default."""
    p = tmp_path / "u.csv"
    p.write_text("symbol,last_price" + chr(10) + chr(10).join(["AAPL,1", "NA,2", "NAN,3", "NULL,4", ",5"]) + chr(10), encoding="utf-8")
    assert load_universe(p) == ["AAPL", "NA", "NAN", "NULL"]
