# U.S. Liquid 1500 Scanner Update

Replace:

- `universe.py`
- `bulk_market_data.py`
- `universe_scanner.py`
- `universe_worker.py`
- `pages/1_Top_500_Scanner.py`

## What changed

The scanner now supports:

1. `US Liquid 1500`
   - Downloads Nasdaq Trader's current all-issues directory.
   - Filters ETFs, warrants, rights, units, preferred securities, funds,
     acquisition vehicles and obvious debt instruments.
   - Gets current snapshots in batches.
   - Ranks candidates by daily dollar volume.
   - Keeps the top 1,500 before downloading longer history.

2. `S&P 500`
   - Keeps the original option.
   - Fixes the raw-HTML bug with `io.StringIO`.

## Run locally

```powershell
streamlit run app.py
```

Open the scanner page and choose `US Liquid 1500`.

The first broad scan can take several minutes and may encounter Alpaca free-tier
rate limits. Start with 500 if necessary, then increase to 1,000 or 1,500.

## Railway worker

```text
UNIVERSE_NAME=US Liquid 1500
UNIVERSE_TARGET_SIZE=1500
UNIVERSE_MIN_PRICE=2
UNIVERSE_MIN_DOLLAR_VOLUME=2000000
UNIVERSE_BENCHMARK=SPY
UNIVERSE_RUN_FOREVER=true
UNIVERSE_INTERVAL_SECONDS=300
CDR_LOOKUP_TOP_N=25
```

Start command:

```text
python universe_worker.py
```

## Important

A five-minute full-history scan of 1,500 stocks is unnecessarily expensive.
The current worker is functional, but the next optimization should persist
daily indicator history and use only bulk snapshots for the five-minute cycle.
