"""Symbol sources for the universe builder (scanner/symbols.py)."""
from scanner.symbols import eligible_symbols, parse_nasdaq_directory

NASDAQ_LISTED = "\n".join([
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
    "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
    "QQQ|Invesco QQQ Trust, Series 1|G|N|N|100|Y|N",
    "ZXZZT|NASDAQ TEST STOCK|G|Y|N|100|N|N",
    "ARCC|Ares Capital Corporation - Closed End Fund|Q|N|N|100|N|N",
    "File Creation Time: 0918202618:01|||||||",
])
OTHER_LISTED = "\n".join([
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
    "A|Agilent Technologies, Inc. Common Stock|N|A|N|100|N|A",
    "BRK.B|Berkshire Hathaway Inc. Class B|N|BRK.B|N|100|N|BRK=B",
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",
    "NA|Nano Labs Ltd Class A|A|NA|N|100|N|NA",
    "File Creation Time: 0918202618:01||||||",
])


def test_parse_drops_test_issues_and_footer_and_reads_the_etf_flag():
    recs = parse_nasdaq_directory(NASDAQ_LISTED, OTHER_LISTED)
    syms = {r["symbol"]: r for r in recs}
    assert "ZXZZT" not in syms and not any(s.startswith("File") for s in syms)
    assert syms["QQQ"]["etf"] and syms["SPY"]["etf"] and not syms["AAPL"]["etf"]
    assert syms["A"]["exchange"] == "NYSE" and syms["NA"]["exchange"] == "NYSE American"


def test_eligible_symbols_applies_one_rule_to_every_source():
    recs = parse_nasdaq_directory(NASDAQ_LISTED, OTHER_LISTED)
    # ETF flag, fund/trust names and share classes (BRK.B) are all dropped;
    # NA is a real ticker and stays.
    assert eligible_symbols(recs) == ["AAPL", "A", "NA"]


def test_eligible_symbols_respects_tradable_and_dedupes():
    recs = [{"symbol": "AAPL", "name": "Apple", "tradable": True},
            {"symbol": "aapl", "name": "Apple", "tradable": True},
            {"symbol": "XYZ", "name": "Halted Co", "tradable": False},
            {"symbol": "TQQQ", "name": "ProShares UltraPro QQQ", "tradable": True}]
    assert eligible_symbols(recs) == ["AAPL"]
