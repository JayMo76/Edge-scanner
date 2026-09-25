#!/usr/bin/env sh
# macOS / Linux launcher. Same behaviour as start_scanner.bat:
#   - scans data/universe_all.csv when it exists, otherwise data/universe.csv
#     (built and refreshed weekly by scripts/build_universe.py)
#   - loads 380 calendar days of daily history (about 252 sessions)
# Extra flags are passed through:  ./start_scanner.sh --log-level INFO
cd "$(dirname "$0")" || exit 1

UNIVERSE_ARG=""
[ -f data/universe_all.csv ] && UNIVERSE_ARG="--universe data/universe_all.csv"

PY="${PYTHON:-python3}"
# shellcheck disable=SC2086
exec "$PY" scripts/run_live.py $UNIVERSE_ARG --history-days 380 "$@"
