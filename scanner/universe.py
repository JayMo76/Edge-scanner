"""Universe loader — read the pre-built universe CSV into a symbol list.

Build the universe file first with:
    python scripts/build_universe.py

Then load it:
    from scanner.universe import load_universe
    symbols = load_universe()          # default path data/universe.csv
    symbols = load_universe("my.csv")  # custom path
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_DEFAULT_UNIVERSE_PATH = Path("data/universe.csv")


def load_universe(path: str | Path = _DEFAULT_UNIVERSE_PATH) -> list[str]:
    """Load the universe symbol list from a CSV file.

    The CSV must contain a 'symbol' column.  Extra columns (in_sp500,
    in_nasdaq100, in_russell1000) are accepted but ignored.

    Args:
        path: path to the universe CSV (default: data/universe.csv)

    Returns:
        Sorted list of uppercase ticker symbols.

    Raises:
        FileNotFoundError: if the CSV does not exist.
        ValueError:        if the CSV is missing the 'symbol' column.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Universe file not found: {p}\n"
            "Build it first with:  python scripts/build_universe.py"
        )
    # Tickers are text: without this, pandas reads real symbols such as NA
    # (and NAN, NULL, N/A) as missing values and they drop out of the universe.
    df = pd.read_csv(p, dtype={"symbol": str}, keep_default_na=False, na_values=[""])
    if "symbol" not in df.columns:
        raise ValueError(
            f"Universe CSV is missing a 'symbol' column: {p}\n"
            "Expected columns: symbol[, in_sp500, in_nasdaq100, in_russell1000]"
        )
    symbols = (
        df["symbol"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .unique()
        .tolist()
    )
    return sorted(symbols)
