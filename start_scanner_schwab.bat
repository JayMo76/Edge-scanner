@echo off
title Scanner Live (Schwab, port 7787)
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM A SECOND scanner on Charles Schwab data, to run beside start_scanner.bat.
REM Same universe, same setups, same history window. Only three things differ,
REM so the two never collide:
REM   --feed schwab        the data provider (start_scanner.bat uses .env, Alpaca by default)
REM   --port 7787          dashboard at http://localhost:7787/v2 (the first one keeps 7777)
REM   --alerts-dir ...     its own alert archive, so the two can be compared afterwards
REM Schwab is a separate provider, so this does not disturb the other scanner's stream.
REM Start it before the open: Schwab back-fills today's bars for the top 600 symbols only.
REM ---------------------------------------------------------------------------
set "UNIVERSE_ARG="
if exist "data\universe_all.csv" set "UNIVERSE_ARG=--universe data/universe_all.csv"

set "HISTORY_DAYS=380"

python scripts/run_live.py --feed schwab --port 7787 --alerts-dir data/alerts_schwab %UNIVERSE_ARG% --history-days %HISTORY_DAYS% %*

echo.
echo === Schwab scanner exited ===
pause
