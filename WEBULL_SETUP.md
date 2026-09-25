# Webull feed for Edge Scanner

This variant uses the maintained Webull OpenAPI Python SDK for stock bars and snapshots.
It polls **closed one-minute bars** for a watchlist of at most 40 symbols.
It does not connect to Alpaca in `DATA_PROVIDER=webull` mode, including Alpaca's Benzinga news endpoint.

## Windows setup

1. Install `requirements.txt` into your Python environment, copy `.env.example` to `.env`, and set `WEBULL_APP_KEY` and `WEBULL_APP_SECRET` locally. Never commit `.env`.
2. Set `DATA_PROVIDER=webull` and create your own UTF-8 universe CSV at `data/webull_watchlist.csv` with your existing Edge Scanner universe columns and at most 40 symbols. The `symbol` column is required; using the same columns as `data/universe.csv` preserves universe filters. Use Nasdaq's public directory as the source of ticker identities if you rebuild the list. Do not run `scripts/build_universe.py` on the full Nasdaq universe with Webull.
3. Run `.venv\Scripts\python.exe scripts\run_live.py --feed webull --universe data\webull_watchlist.csv`. Browser: `http://127.0.0.1:7777`.

The Webull feed uses distinct source responses. Historical minute bars use unadjusted data and Webull daily bars may use different adjustments than Alpaca. Compare RVOL and historical thresholds on a known sample before trusting alerts. The 1200-bar endpoint limit is handled by chunked requests, but backfilling 20 days for 40 tickers is slow and may encounter provider entitlements or rate limits. Missing bars cause missing context; they are never manufactured.

**News gap:** the maintained Webull OpenAPI SDK version inspected has no stock-news method, and the connected Webull integration does not provide one. The dashboard's `NEWS_RSS_SOURCES=yahoo,nasdaq` continues to show per-symbol RSS headlines, clearly sourced to those publishers. Market-wide headlines remain empty. A Webull news endpoint and its terms/entitlement would be needed to replace RSS with Webull news. This repository never labels RSS as Webull news.

This is a scanner and does not place orders. The Webull credentials in ChatGPT are separate from those in your local Windows `.env`.
